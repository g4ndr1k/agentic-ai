"""
secret_manager.py — macOS Keychain integration for secret storage.

Replaces plaintext files in secrets/ with encrypted Keychain entries.

CLI:
    python3 -m bridge.secret_manager init           # Migrate file-based secrets → Keychain
    python3 -m bridge.secret_manager get <key>      # Retrieve a secret
    python3 -m bridge.secret_manager set <key>      # Store a secret (interactive prompt)
    python3 -m bridge.secret_manager set <key> -v <value>  # Store a secret (via --value flag)
    python3 -m bridge.secret_manager delete <key>   # Remove a secret
    python3 -m bridge.secret_manager list           # List stored key names

Config (config/settings.toml):
    [auth]
    token_source = "keychain"          # "file" (default) or "keychain"
    keychain_service = "agentic-ai-bridge"

    [pdf]
    bank_passwords_source = "keychain" # "file" or "keychain"

Keychain structure:
    Type:    generic-password  (not internet-password — these aren't URL-based)
    Service: agentic-ai-bridge (or custom)
    Account: key name (bridge_token, banks_toml, banks.maybank, FINANCE_API_KEY, etc.)

Integration helpers (used by bridge/config.py and bridge/auth.py):
    resolve_token(settings)     — get bridge token from Keychain or file
    resolve_bank_password(bank, settings) — get bank PDF password from Keychain or file
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib          # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib   # pip install tomli (3.7–3.10)
    except ModuleNotFoundError:
        tomllib = None

# ── Project root (relative to this file) ───────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SERVICE = "agentic-ai-bridge"

# ── Suppress macOS MallocStackLogging noise in child processes ────────────
# Without this, every subprocess.run() to `security` prints:
#   python3(…) MallocStackLogging: can't turn off malloc stack logging …
_SUBPROCESS_ENV = {**os.environ, "MallocStackLogging": "0"}


# ═══════════════════════════════════════════════════════════════════════════
# Keychain operations (using `security` CLI — generic-password items)
# ═══════════════════════════════════════════════════════════════════════════

def get_from_keychain(service: str, account: str) -> str | None:
    """Retrieve a secret from macOS Keychain.

    Uses 'security find-generic-password' which is appropriate for
    non-URL-based secrets (API keys, tokens, passwords).

    NOTE: The macOS `security` CLI hex-encodes values that contain
    newlines or non-ASCII bytes (e.g. JSON files, TOML content).
    This function auto-detects hex encoding and decodes transparently.

    Returns None if not found or on error.
    """
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", service,
                "-a", account,
                "-w",          # output password only
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=_SUBPROCESS_ENV,
        )
        if result.returncode == 0 and result.stdout.strip():
            value = result.stdout.strip()
            # Auto-detect hex encoding: if the value is all hex chars and
            # decodes to valid UTF-8, it was hex-encoded by `security`.
            if _is_hex_encoded(value):
                try:
                    value = bytes.fromhex(value).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    pass  # not actually hex-encoded, return as-is
            return value
    except FileNotFoundError:
        print("Error: 'security' CLI not found — this tool requires macOS.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Error: Keychain lookup timed out.", file=sys.stderr)
    except Exception as e:
        print(f"Keychain lookup error: {e}", file=sys.stderr)
    return None


def _is_hex_encoded(s: str) -> bool:
    """Check if a string looks like hex-encoded data.

    The `security` CLI hex-encodes values containing newlines. A hex-encoded
    string will be all hex digits and have even length. We also check that
    decoding produces valid UTF-8 to avoid false positives on short hex-like
    tokens (e.g. API keys that happen to be hex).
    """
    if len(s) < 4 or len(s) % 2 != 0:
        return False
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False


def set_in_keychain(service: str, account: str, password: str) -> bool:
    """Store a secret in macOS Keychain.

    Deletes any existing entry first (upsert semantics).
    Returns True on success.

    NOTE: The password is passed via -w on the command line, which briefly
    exposes it in `ps` output. This is the standard approach with the
    `security` CLI and the exposure window is sub-second. The significant
    security improvement is removing secrets from plaintext files on disk.
    """
    try:
        # Delete existing (ignore error if not present)
        subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", account],
            capture_output=True,
            timeout=5,
            env=_SUBPROCESS_ENV,
        )
        # Add new entry
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", service,        # service name
                "-a", account,        # account name
                "-w", password,       # password data
                "-U",                 # update if exists (belt-and-suspenders)
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=_SUBPROCESS_ENV,
        )
        if result.returncode != 0:
            print(f"Keychain store failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except FileNotFoundError:
        print("Error: 'security' CLI not found — this tool requires macOS.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Keychain store error: {e}", file=sys.stderr)
        return False


def delete_from_keychain(service: str, account: str) -> bool:
    """Delete a secret from macOS Keychain. Returns True if deleted or not found."""
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", account],
            capture_output=True,
            text=True,
            timeout=5,
            env=_SUBPROCESS_ENV,
        )
        # exit 44 = item not found, which is fine for delete
        return result.returncode in (0, 44)
    except Exception:
        return False


def list_keychain_keys(service: str) -> list[str]:
    """List account names stored under a given service in Keychain.

    For generic-password items, the service name appears as attribute
    0x00000007 in 'security dump-keychain' output, followed by 0x00000008
    and then "acct"<blob>="the_key_name".
    """
    try:
        result = subprocess.run(
            ["security", "dump-keychain"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_SUBPROCESS_ENV,
        )
        keys = []
        in_service = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            # Generic-password service is attribute 0x00000007
            # Format: 0x00000007 <blob>="agentic-ai-bridge"
            if f'<blob>="{service}"' in stripped and '0x00000007' in stripped:
                in_service = True
            elif in_service and '"acct"<blob>=' in stripped:
                # Extract account: "acct"<blob>="bridge_token"
                start = stripped.find('="') + 2
                end = stripped.rfind('"')
                if start > 1 and end > start:
                    keys.append(stripped[start:end])
                in_service = False
            elif in_service and stripped.startswith("keychain:"):
                in_service = False
        return sorted(set(keys))
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Integration helpers — used by bridge/config.py and bridge/auth.py
# ═══════════════════════════════════════════════════════════════════════════

def _load_settings() -> dict:
    """Load settings.toml from the project root."""
    settings_path = _PROJECT_ROOT / "config" / "settings.toml"
    if not settings_path.exists():
        return {}
    if tomllib is None:
        raise RuntimeError("tomllib (Python 3.11+) or tomli package required to read settings.toml")
    with open(settings_path, "rb") as f:
        return tomllib.load(f)


def _keychain_service(settings: dict | None = None) -> str:
    """Get the Keychain service name from settings, or use default."""
    if settings is None:
        settings = _load_settings()
    return settings.get("auth", {}).get("keychain_service", _DEFAULT_SERVICE)


def resolve_token(settings: dict | None = None) -> str | None:
    """Resolve the bridge token from Keychain or file, based on settings.

    If auth.token_source == "keychain", reads from Keychain.
    Otherwise falls back to the file specified in auth.token_file.
    """
    if settings is None:
        settings = _load_settings()

    auth = settings.get("auth", {})
    source = auth.get("token_source", "file")

    if source == "keychain":
        service = _keychain_service(settings)
        token = get_from_keychain(service, "bridge_token")
        if token:
            return token
        # Fallback to file if Keychain miss
        print("Warning: token_source=keychain but Keychain empty, falling back to file", file=sys.stderr)

    # File-based fallback
    token_file = auth.get("token_file", "")
    if token_file:
        path = Path(token_file).expanduser()
        if path.exists():
            return path.read_text().strip()

    return None


def resolve_bank_password(bank_name: str, settings: dict | None = None) -> str:
    """Resolve a bank PDF password from Keychain or file, based on settings.

    Keychain lookup order:
      1. banks.<bank_name>  (e.g. banks.maybank) — per-bank key
      2. banks_toml         — full banks.toml content, parsed for the key

    File fallback:
      Reads the TOML file at pdf.bank_passwords_file.
    """
    if settings is None:
        settings = _load_settings()

    pdf = settings.get("pdf", {})
    source = pdf.get("bank_passwords_source", "file")
    key = (bank_name or "").lower().replace(" ", "_")

    if source == "keychain":
        service = _keychain_service(settings)
        # Try per-bank key first
        password = get_from_keychain(service, f"banks.{key}")
        if password:
            return password
        # Try full banks_toml content
        banks_toml = get_from_keychain(service, "banks_toml")
        if banks_toml:
            try:
                data = tomllib.loads(banks_toml)
                return data.get("passwords", {}).get(key, "")
            except Exception:
                pass
        # Fallback to file
        print(f"Warning: bank_passwords_source=keychain but Keychain empty for '{key}', "
              f"falling back to file", file=sys.stderr)

    # File-based fallback
    passwords_file = pdf.get("bank_passwords_file", "")
    if passwords_file:
        path = Path(passwords_file).expanduser()
        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                return data.get("passwords", {}).get(key, "")
            except Exception:
                pass

    return ""


def resolve_env_key(env_name: str, settings: dict | None = None) -> str:
    """Resolve an environment-variable-style key from Keychain, falling back to os.environ.

    Use this for API keys that were previously stored in .env files.
    Checks Keychain first (if auth.token_source = "keychain"), then os.environ.

    Example:
        api_key = resolve_env_key("FINANCE_API_KEY")
    """
    if settings is None:
        settings = _load_settings()

    auth = settings.get("auth", {})
    source = auth.get("token_source", "file")

    if source == "keychain":
        service = _keychain_service(settings)
        val = get_from_keychain(service, env_name)
        if val:
            return val

    # Fallback to environment variable
    import os
    return os.environ.get(env_name, "")


# ═══════════════════════════════════════════════════════════════════════════
# Init — migrate file-based secrets → Keychain
# ═══════════════════════════════════════════════════════════════════════════

def init_keychain_secrets(service: str = _DEFAULT_SERVICE):
    """Migrate existing file-based secrets to macOS Keychain.

    Reads from the project's secrets/ directory and .env file,
    storing each value as a generic-password Keychain entry.
    """
    print(f"Initializing Keychain under service: {service}")
    print(f"Project root: {_PROJECT_ROOT}")
    print()

    migrated = 0
    skipped = 0

    # ── 1. Bridge token ────────────────────────────────────────────────────
    token_path = _PROJECT_ROOT / "secrets" / "bridge.token"
    if token_path.exists():
        token = token_path.read_text().strip()
        if token:
            if set_in_keychain(service, "bridge_token", token):
                print(f"  ✓ bridge_token")
                migrated += 1
            else:
                print(f"  ✗ bridge_token (failed)")
                skipped += 1
        else:
            print("  - bridge.token is empty, skipping")
            skipped += 1
    else:
        print(f"  - bridge.token not found at {token_path}, skipping")
        skipped += 1

    # ── 2. Bank passwords (banks.toml) ─────────────────────────────────────
    banks_path = _PROJECT_ROOT / "secrets" / "banks.toml"
    if banks_path.exists():
        banks_content = banks_path.read_text()
        if banks_content.strip():
            # Store the full TOML content (for fallback parsing)
            if set_in_keychain(service, "banks_toml", banks_content):
                print(f"  ✓ banks_toml (full content)")
                migrated += 1
            else:
                print(f"  ✗ banks_toml (failed)")
                skipped += 1

            # Also store each bank password as a separate key
            try:
                with open(banks_path, "rb") as f:
                    data = tomllib.load(f)
                for bank, pwd in data.get("passwords", {}).items():
                    key = f"banks.{bank}"
                    if set_in_keychain(service, key, pwd):
                        print(f"  ✓ {key}")
                        migrated += 1
                    else:
                        print(f"  ✗ {key} (failed)")
                        skipped += 1
            except Exception as e:
                print(f"  ✗ Failed to parse banks.toml: {e}")
                skipped += 1
        else:
            print("  - banks.toml is empty, skipping")
            skipped += 1
    else:
        print(f"  - banks.toml not found at {banks_path}, skipping")
        skipped += 1

    # ── 3. Google credentials (as JSON blob) ───────────────────────────────
    google_cred = _PROJECT_ROOT / "secrets" / "google_credentials.json"
    if google_cred.exists():
        content = google_cred.read_text().strip()
        if content:
            if set_in_keychain(service, "google_credentials_json", content):
                print(f"  ✓ google_credentials_json")
                migrated += 1
            else:
                print(f"  ✗ google_credentials_json (failed)")
                skipped += 1

    google_sa = _PROJECT_ROOT / "secrets" / "google_service_account.json"
    if google_sa.exists():
        content = google_sa.read_text().strip()
        if content:
            if set_in_keychain(service, "google_service_account_json", content):
                print(f"  ✓ google_service_account_json")
                migrated += 1
            else:
                print(f"  ✗ google_service_account_json (failed)")
                skipped += 1

    google_tok = _PROJECT_ROOT / "secrets" / "google_token.json"
    if google_tok.exists():
        content = google_tok.read_text().strip()
        if content:
            if set_in_keychain(service, "google_token_json", content):
                print(f"  ✓ google_token_json")
                migrated += 1
            else:
                print(f"  ✗ google_token_json (failed)")
                skipped += 1

    # ── 4. .env file (API keys etc.) ───────────────────────────────────────
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val:
                    if set_in_keychain(service, key, val):
                        print(f"  ✓ {key}")
                        migrated += 1
                    else:
                        print(f"  ✗ {key} (failed)")
                        skipped += 1
    else:
        print("  - .env not found, skipping")

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print(f"Done: {migrated} migrated, {skipped} skipped/failed.")
    if migrated > 0:
        print()
        print("Next steps:")
        print("  1. Verify:  python3 -m bridge.secret_manager list")
        print("  2. Enable Keychain in config/settings.toml:")
        print('       [auth]')
        print('       token_source = "keychain"')
        print('       keychain_service = "agentic-ai-bridge"')
        print('       [pdf]')
        print('       bank_passwords_source = "keychain"')
        print("  3. Test:    python3 -m bridge.secret_manager get bridge_token")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="macOS Keychain secret manager for agentic-ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  init              Migrate secrets from files to Keychain
  get <key>         Retrieve a secret value
  set <key>         Store a secret (prompts for value, or use --value)
  delete <key>      Remove a secret from Keychain
  list              List stored key names

Examples:
  python3 -m bridge.secret_manager init
  python3 -m bridge.secret_manager get bridge_token
  python3 -m bridge.secret_manager set FINANCE_API_KEY
  python3 -m bridge.secret_manager set banks.maybank -v "090672"
  python3 -m bridge.secret_manager list
  python3 -m bridge.secret_manager delete old_key
""",
    )
    parser.add_argument(
        "command",
        choices=["init", "get", "set", "delete", "list"],
        help="Action to perform",
    )
    parser.add_argument(
        "key",
        nargs="?",
        help="Secret key name (required for get/set/delete)",
    )
    parser.add_argument(
        "--service", "-s",
        default=_DEFAULT_SERVICE,
        help=f"Keychain service name (default: {_DEFAULT_SERVICE})",
    )
    parser.add_argument(
        "--value", "-v",
        help="Secret value for 'set' command (if omitted, prompts interactively)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON (for get/list commands)",
    )

    args = parser.parse_args()

    # ── Validate ───────────────────────────────────────────────────────────
    if args.command in ("get", "set", "delete") and not args.key:
        parser.error(f"'{args.command}' requires a <key> argument")

    # ── Dispatch ───────────────────────────────────────────────────────────
    if args.command == "init":
        init_keychain_secrets(args.service)

    elif args.command == "get":
        val = get_from_keychain(args.service, args.key)
        if val is not None:
            if args.json:
                print(json.dumps({"key": args.key, "found": True, "length": len(val)}))
            else:
                print(val)
        else:
            if args.json:
                print(json.dumps({"key": args.key, "found": False}))
            else:
                print(f"Secret '{args.key}' not found in Keychain (service: {args.service})", file=sys.stderr)
            sys.exit(1)

    elif args.command == "set":
        value = args.value
        if value is None:
            # Interactive prompt — don't echo the input
            import getpass
            value = getpass.getpass(f"Enter value for '{args.key}': ")
            if not value:
                confirm = input("Value is empty. Store empty value? [y/N] ")
                if confirm.lower() != "y":
                    print("Aborted.", file=sys.stderr)
                    sys.exit(1)

        if set_in_keychain(args.service, args.key, value):
            if args.json:
                print(json.dumps({"key": args.key, "stored": True}))
            else:
                print(f"✓ Stored '{args.key}' in Keychain (service: {args.service})")
        else:
            if args.json:
                print(json.dumps({"key": args.key, "stored": False}))
            else:
                print(f"✗ Failed to store '{args.key}'", file=sys.stderr)
            sys.exit(1)

    elif args.command == "delete":
        if delete_from_keychain(args.service, args.key):
            if args.json:
                print(json.dumps({"key": args.key, "deleted": True}))
            else:
                print(f"✓ Deleted '{args.key}' from Keychain (service: {args.service})")
        else:
            if args.json:
                print(json.dumps({"key": args.key, "deleted": False}))
            else:
                print(f"✗ Failed to delete '{args.key}'", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        keys = list_keychain_keys(args.service)
        if args.json:
            print(json.dumps({"service": args.service, "keys": keys, "count": len(keys)}))
        elif keys:
            print(f"Keychain keys for service '{args.service}' ({len(keys)}):")
            for k in keys:
                print(f"  {k}")
        else:
            print(f"No keys found for service '{args.service}'.")
            print("Run 'python3 -m bridge.secret_manager init' to migrate secrets.")


if __name__ == "__main__":
    main()
