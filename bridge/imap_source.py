"""
Multi-provider IMAP mail source — fetches emails via IMAP using app passwords.

Supports Gmail, iCloud, and any standard IMAP server.
No Full Disk Access or Mail.app required.
"""

import email as _email_module
import html as _html_module
import imaplib
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

log = logging.getLogger("bridge.imap_source")

# Well-known IMAP servers
IMAP_SERVERS = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "icloud.com": ("imap.mail.me.com", 993),
    "me.com": ("imap.mail.me.com", 993),
    "mac.com": ("imap.mail.me.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
}


def _server_for_email(email_addr: str) -> tuple[str, int]:
    """Resolve IMAP host/port from email domain, with fallback to Gmail."""
    domain = email_addr.split("@")[-1].lower()
    return IMAP_SERVERS.get(domain, ("imap.gmail.com", 993))


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_body(msg) -> tuple[str, str]:
    text_parts, html_parts = [], []
    walk = msg.walk() if msg.is_multipart() else [msg]
    for part in walk:
        ctype = part.get_content_type()
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_param("charset") or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if ctype == "text/plain":
            text_parts.append(decoded)
        elif ctype == "text/html":
            html_parts.append(decoded)

    text = "\n".join(text_parts)
    html = "\n".join(html_parts)

    if not text.strip() and html.strip():
        clean = re.sub(
            r"<(style|script)[^>]*>.*?</(style|script)>",
            " ", html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = _html_module.unescape(clean)
        text = " ".join(clean.split())

    return text[:6000], html[:6000]


class ImapAccount:
    def __init__(self, email: str, app_password: str,
                 imap_host: str | None = None, imap_port: int = 993):
        self.email = email
        self.app_password = app_password
        if imap_host:
            self.imap_host = imap_host
            self.imap_port = imap_port
        else:
            self.imap_host, self.imap_port = _server_for_email(email)


class ImapSource:
    """Multi-provider IMAP source — replaces GmailSource with generic IMAP."""

    def __init__(self, settings: dict, secrets_path: Path):
        self.settings = settings
        self.max_batch = int(settings["mail"].get("max_batch", 25))
        self.initial_lookback_days = int(
            settings["mail"].get("initial_lookback_days", 15))
        self.accounts: list[ImapAccount] = []
        self._load_accounts(secrets_path)

    def _load_accounts(self, secrets_path: Path) -> None:
        if not secrets_path.exists():
            log.error("IMAP secrets file not found: %s", secrets_path)
            return
        try:
            with open(secrets_path, "rb") as f:
                data = tomllib.load(f)
            for acct in data.get("accounts", []):
                addr = acct.get("email", "").strip()
                pw = acct.get("app_password", "").strip().replace(" ", "")
                host = acct.get("imap_host", "").strip() or None
                port = int(acct.get("imap_port", 993))
                if addr and pw:
                    self.accounts.append(ImapAccount(addr, pw, host, port))
                    log.info("IMAP account loaded: %s (%s:%d)",
                             addr, self.accounts[-1].imap_host,
                             self.accounts[-1].imap_port)
        except Exception as e:
            log.error("Failed to load IMAP secrets from %s: %s",
                      secrets_path, e)

    def can_access(self) -> bool:
        if not self.accounts:
            log.warning("No IMAP accounts configured")
            return False
        # Test connectivity for the first account only (quick check)
        acct = self.accounts[0]
        try:
            imap = imaplib.IMAP4_SSL(acct.imap_host, acct.imap_port)
            imap.login(acct.email, acct.app_password)
            imap.logout()
            return True
        except Exception as e:
            log.warning("IMAP connectivity check failed for %s (%s:%d): %s",
                        acct.email, acct.imap_host, acct.imap_port, e)
            return False

    def get_pending_messages(
        self, ack_token: str, limit: int = 25
    ) -> tuple[list[dict], str]:
        try:
            parsed = (
                json.loads(ack_token)
                if ack_token and ack_token != "0"
                else {}
            )
            ack_map: dict[str, int] = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            ack_map = {}

        all_results: list[dict] = []
        new_ack_map = dict(ack_map)
        per_acct_limit = max(1, limit // max(1, len(self.accounts)))

        for acct in self.accounts:
            last_uid = int(ack_map.get(acct.email, 0))
            try:
                msgs, new_uid = self._fetch_account(
                    acct, last_uid, per_acct_limit)
                all_results.extend(msgs)
                if new_uid > last_uid:
                    new_ack_map[acct.email] = new_uid
            except Exception as e:
                log.error("IMAP fetch failed for %s: %s", acct.email, e)

        all_results.sort(key=lambda m: m.get("date_received") or "")
        return all_results[:limit], json.dumps(new_ack_map)

    def _fetch_account(
        self, acct: ImapAccount, last_uid: int, limit: int
    ) -> tuple[list[dict], int]:
        imap = imaplib.IMAP4_SSL(acct.imap_host, acct.imap_port)
        try:
            imap.login(acct.email, acct.app_password)
            imap.select("INBOX", readonly=True)

            if last_uid > 0:
                status, data = imap.uid(
                    "SEARCH", None, f"UID {last_uid + 1}:*")
            else:
                cutoff = (datetime.now(tz=timezone.utc)
                          - timedelta(days=self.initial_lookback_days))
                since_str = cutoff.strftime("%d-%b-%Y")
                status, data = imap.uid(
                    "SEARCH", None, f"SINCE {since_str}")

            if status != "OK":
                log.warning("IMAP SEARCH failed for %s: %s",
                            acct.email, status)
                return [], last_uid

            uid_list = data[0].decode().split() if data[0] else []
            uid_list = [u for u in uid_list if int(u) > last_uid]
            uid_list = uid_list[:limit]

            if not uid_list:
                log.info("No new messages for %s", acct.email)
                return [], last_uid

            log.info("Fetching %d new message(s) for %s (%s)",
                     len(uid_list), acct.email, acct.imap_host)
            results: list[dict] = []
            max_uid = last_uid

            for uid_str in uid_list:
                uid = int(uid_str)
                max_uid = max(max_uid, uid)
                try:
                    msg_dict = self._fetch_message(
                        imap, acct.email, uid_str)
                    if msg_dict:
                        results.append(msg_dict)
                except Exception as e:
                    log.warning("Failed to fetch UID %s from %s: %s",
                                uid_str, acct.email, e)

            return results, max_uid

        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def _fetch_message(
        self, imap: imaplib.IMAP4_SSL, account_email: str, uid_str: str
    ) -> dict | None:
        status, data = imap.uid("FETCH", uid_str, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            return None

        raw = data[0][1] if isinstance(data[0], tuple) else None
        if not raw:
            return None

        msg = _email_module.message_from_bytes(raw)
        subject = _decode_header(msg.get("Subject", ""))
        from_raw = _decode_header(msg.get("From", ""))
        message_id = msg.get("Message-ID", "").strip()
        date_str = msg.get("Date", "")

        sender_email, sender_name = "", ""
        m = re.match(r"^(.*?)\s*<(.+?)>\s*$", from_raw.strip())
        if m:
            sender_name = m.group(1).strip().strip('"')
            sender_email = m.group(2).strip()
        else:
            sender_email = from_raw.strip()

        date_received = None
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            date_received = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass

        body_text, body_html = _extract_body(msg)
        sender = (f"{sender_name} <{sender_email}>"
                  if sender_name else sender_email)

        return {
            "bridge_id": f"imap-{account_email}-{uid_str}",
            "source_rowid": int(uid_str),
            "message_id": message_id or f"uid-{uid_str}",
            "mailbox": "INBOX",
            "mailbox_url": f"imap://{account_email}/INBOX",
            "sender": sender,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "subject": subject or "(No Subject)",
            "date_received": date_received,
            "date_sent": date_received,
            "snippet": body_text[:500],
            "body_text": body_text,
            "body_html": body_html,
            "body_text_truncated": len(body_text) >= 6000,
            "body_source": "imap_rfc822",
            "has_body": bool(body_text),
            "apple_category": None,
            "apple_high_impact": None,
            "apple_urgent": None,
            "is_read": False,
            "is_flagged": False,
            "attachments": [],
        }
