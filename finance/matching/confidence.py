"""Generic confidence dynamics — typed-event API, domain-agnostic.

Single source of truth for updating mapping confidence_score and
deriving confidence_level. Never set confidence_score directly on a
mapping — always go through apply() with a typed event.

Thresholds:
  >= 0.85  →  HIGH
  >= 0.50  →  MEDIUM
  else     →  LOW
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Union


HIGH_THRESHOLD = 0.85
MEDIUM_THRESHOLD = 0.50
CONFIRM_FLOOR = 0.95

# Boost applied per RunUsed event (capped per plan §echo-chamber dampener)
RUN_USED_BOOST = 0.05
# Boost cap from suggestion-acceptance until mapping has ≥3 distinct run hits
SUGGESTION_BOOST_CAP_BEFORE_MATURITY = 0.9
SUGGESTION_BOOST_PER_ACCEPT = 0.05

RUN_UNUSED_DECAY = 0.10
STALE_YEAR_THRESHOLD = 2   # unused for ≥2 runs spanning ≥1 year → UNUSED bucket


# ── Events ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Confirmed:
    """User manually confirmed a mapping."""
    pass


@dataclass(frozen=True)
class RunUsed:
    """Mapping fired successfully in a reconcile / import run."""
    run_key: str  # tax_year for coretax; run_id for others


@dataclass(frozen=True)
class RunUnused:
    """Mapping was not used in a run.
    Decay only applies if fingerprint is still in the domain's universe."""
    run_key: str
    fingerprint_still_present: bool = True


@dataclass(frozen=True)
class SuggestionAccepted:
    """User accepted a suggestion — nudges score upward, capped until mature."""
    pass


@dataclass(frozen=True)
class TargetDeleted:
    """Target row was deleted or superseded."""
    pass


Event = Union[Confirmed, RunUsed, RunUnused, SuggestionAccepted, TargetDeleted]


# ── Public API ───────────────────────────────────────────────────────────────


def derive_level(score: float) -> str:
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def apply(event: Event, mapping: dict) -> dict:
    """Apply a typed event to a mapping dict.

    Returns a dict of fields to update; caller persists them.
    Fields: confidence_score, confidence_level, times_confirmed,
            years_used, last_used_at, updated_at.
    """
    now = _utcnow()
    score = float(mapping.get("confidence_score", 1.0))
    times_confirmed = int(mapping.get("times_confirmed", 0))
    years_used = int(mapping.get("years_used", 0))
    last_used_at = mapping.get("last_used_at")

    if isinstance(event, Confirmed):
        times_confirmed += 1
        score = max(score, CONFIRM_FLOOR)

    elif isinstance(event, RunUsed):
        years_used += 1
        score = min(1.0, score + RUN_USED_BOOST)
        last_used_at = now

    elif isinstance(event, RunUnused):
        if event.fingerprint_still_present:
            score = max(0.0, score - RUN_UNUSED_DECAY)

    elif isinstance(event, SuggestionAccepted):
        # Cap boost at SUGGESTION_BOOST_CAP_BEFORE_MATURITY until 3 distinct runs
        cap = SUGGESTION_BOOST_CAP_BEFORE_MATURITY if years_used < 3 else 1.0
        score = min(cap, score + SUGGESTION_BOOST_PER_ACCEPT)

    elif isinstance(event, TargetDeleted):
        score = 0.15  # immediately LOW

    else:
        raise ValueError(f"Unknown event type: {type(event)}")

    return {
        "confidence_score": round(score, 4),
        "confidence_level": derive_level(score),
        "times_confirmed": times_confirmed,
        "years_used": years_used,
        "last_used_at": last_used_at,
        "updated_at": now,
    }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
