"""Per-domain engine kill switches.

Read on every classify call. Setting a domain to False routes through
the legacy adapter without a redeploy — faster than reverting code,
safer than removing flags.

Toggled via the admin endpoint (key-protected, audited).
"""
from __future__ import annotations

import os


def _env_bool(var: str, default: bool) -> bool:
    val = os.environ.get(var, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


# Domain enabled state — runtime mutable via admin endpoint.
# Defaults come from MATCHING_ENABLED_<DOMAIN> env var (1/0/true/false).
_DEFAULTS: dict[str, bool] = {
    "coretax":        _env_bool("MATCHING_ENABLED_CORETAX",        True),
    "parser":         _env_bool("MATCHING_ENABLED_PARSER",         True),
    "dedup":          _env_bool("MATCHING_ENABLED_DEDUP",          False),
    "categorization": _env_bool("MATCHING_ENABLED_CATEGORIZATION", False),
}

_RUNTIME_STATE: dict[str, bool] = dict(_DEFAULTS)


def is_enabled(domain_name: str) -> bool:
    """Return True if the engine is active for this domain."""
    return _RUNTIME_STATE.get(domain_name, False)


def set_enabled(domain_name: str, value: bool) -> None:
    """Enable or disable a domain at runtime. Audited by admin endpoint."""
    _RUNTIME_STATE[domain_name] = value


def status() -> dict[str, bool]:
    """Return a snapshot of all domain enable states."""
    return dict(_RUNTIME_STATE)
