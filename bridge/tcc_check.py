"""
tcc_check.py — Pre-flight TCC (Privacy & Security) permission validation.

macOS TCC controls access to protected resources:
  - Full Disk Access (kTCCServiceSystemPolicyAppBundlesFiles)
  - Automation / Apple Events (kTCCServiceAppleEvents)

When the bridge runs inside an .app bundle, TCC identity is tied to
the bundle path (e.g. /Applications/AgenticAI.app), which stays stable
across Homebrew Python upgrades. Without the bundle, TCC is tied to
the Python binary path (/opt/homebrew/Cellar/python@3.14/.../python3.14),
which changes on every brew upgrade and invalidates the grant.

Usage:
    from bridge.tcc_check import check_fda, check_automation

    if not check_fda():
        log.error("Full Disk Access not granted — bridge cannot read Mail DB")

    if not check_automation():
        log.warning("Automation access not granted — AppleScript features disabled")
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("bridge.tcc")

# ── TCC service constants ──────────────────────────────────────────────────
# These match macOS's TCC database entries. The SQLite TCC database
# lives at /Library/Application Support/com.apple.TCC/TCC.db (system)
# and ~/Library/Application Support/com.apple.TCC/TCC.db (user).
# We DO NOT read the TCC database directly (that itself requires FDA).
# Instead, we probe the actual protected resource.

# ── FDA check ──────────────────────────────────────────────────────────────

def _get_executable_path() -> str:
    """Get the path TCC uses to identify this process."""
    # If running inside an .app bundle, TCC sees the bundle path
    exe = sys.executable
    # Check if we're inside an .app bundle (Contents/MacOS/...)
    parts = Path(exe).resolve().parts
    for i, part in enumerate(parts):
        if part.endswith(".app") and i + 2 < len(parts) \
                and parts[i + 1] == "Contents" and parts[i + 2] == "MacOS":
            # Return the .app bundle path — this is what TCC tracks
            return str(Path(*parts[:i + 1]))
    return exe


def check_fda() -> bool:
    """Check if Full Disk Access is granted to this process.

    Probes by attempting to read a known TCC-protected resource:
    ~/Library/Metadata/CoreSpotlight/index.spotlightV3 — this directory
    exists on all macOS systems and requires FDA to enumerate.

    Returns True if FDA is granted, False otherwise.
    """
    # Probe: try to list a TCC-protected directory
    # ~/Library/Metadata/CoreSpotlight/ requires FDA
    probe_dir = Path.home() / "Library" / "Metadata" / "CoreSpotlight"

    try:
        # os.listdir triggers the TCC check; if FDA is granted, it works.
        # If not, macOS raises PermissionError (not just OS-level perm,
        # but TCC denial).
        _ = os.listdir(probe_dir)
        return True
    except PermissionError:
        exe = _get_executable_path()
        logger.warning(
            "Full Disk Access DENIED for %s. "
            "Grant in: System Settings → Privacy & Security → Full Disk Access → add '%s'",
            exe, exe,
        )
        return False
    except FileNotFoundError:
        # Directory doesn't exist on this system — unlikely but not a TCC issue
        # Try alternative probe
        return _check_fda_alternative()
    except Exception as e:
        logger.debug("FDA probe unexpected error: %s", e)
        return _check_fda_alternative()


def _check_fda_alternative() -> bool:
    """Alternative FDA check using a different protected path."""
    # ~/Library/Containers also requires FDA
    probe_dir = Path.home() / "Library" / "Containers"
    try:
        _ = os.listdir(probe_dir)
        return True
    except PermissionError:
        exe = _get_executable_path()
        logger.warning(
            "Full Disk Access DENIED for %s. "
            "Grant in: System Settings → Privacy & Security → Full Disk Access",
            exe,
        )
        return False
    except Exception:
        return False


# ── Automation / Apple Events check ────────────────────────────────────────

def check_automation() -> bool:
    """Check if Automation (Apple Events) access is granted.

    Probes by attempting a basic AppleScript that talks to System Events.
    If automation permission is denied, this returns False.

    NOTE: The first call may trigger a macOS permission prompt.
    """
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                'tell application "System Events" to get name of first process',
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "MallocStackLogging": "0"},
        )
        if result.returncode == 0:
            return True
        # Exit code often means automation was denied
        logger.warning(
            "Automation access DENIED. "
            "Grant in: System Settings → Privacy & Security → Automation",
        )
        return False
    except FileNotFoundError:
        logger.warning("osascript not found — cannot check automation access")
        return False
    except Exception as e:
        logger.debug("Automation probe error: %s", e)
        return False


# ── Mail database access check ─────────────────────────────────────────────

def check_mail_access(mail_db_path: str | None = None) -> bool:
    """Check if we can read the Mail database (specific FDA requirement).

    This is the most critical access for the bridge.
    """
    if mail_db_path is None:
        mail_db_path = str(
            Path.home() / "Library" / "Messages" / "chat.db"
        )

    try:
        with open(mail_db_path, "rb") as f:
            _ = f.read(1)
        return True
    except PermissionError:
        exe = _get_executable_path()
        logger.error(
            "Mail database access DENIED. FDA required for %s. "
            "Grant in: System Settings → Privacy & Security → Full Disk Access → add '%s'",
            exe, exe,
        )
        return False
    except FileNotFoundError:
        logger.warning("Mail database not found at: %s", mail_db_path)
        return False
    except Exception as e:
        logger.debug("Mail access probe error: %s", e)
        return False


# ── Full pre-flight check ──────────────────────────────────────────────────

def preflight_check() -> dict:
    """Run all TCC pre-flight checks. Returns a dict of results.

    Use this at bridge startup to log the state of all permissions.
    """
    results = {
        "fda": check_fda(),
        "automation": check_automation(),
        "executable": _get_executable_path(),
    }

    all_ok = results["fda"] and results["automation"]
    results["all_ok"] = all_ok

    if all_ok:
        logger.info(
            "TCC pre-flight OK — FDA ✓ Automation ✓ (identity: %s)",
            results["executable"],
        )
    else:
        missing = []
        if not results["fda"]:
            missing.append("Full Disk Access")
        if not results["automation"]:
            missing.append("Automation")
        logger.error(
            "TCC pre-flight FAILED — missing: %s (identity: %s). "
            "Open: System Settings → Privacy & Security",
            ", ".join(missing),
            results["executable"],
        )

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    results = preflight_check()
    print()
    print(f"Executable identity : {results['executable']}")
    print(f"Full Disk Access    : {'✓ GRANTED' if results['fda'] else '✗ DENIED'}")
    print(f"Automation          : {'✓ GRANTED' if results['automation'] else '✗ DENIED'}")
    print(f"Overall             : {'✓ OK' if results['all_ok'] else '✗ FAIL'}")
    if not results["all_ok"]:
        print()
        print("Fix: System Settings → Privacy & Security → Full Disk Access")
        print("     Add the app shown above as 'Executable identity'")
