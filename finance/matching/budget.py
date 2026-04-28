"""Learning budget constants — rate caps for auto-persist across all domains.

These are central constants so all domains tune together in code review.
Per-domain overrides are supported from day one (different volume profiles).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    per_run: int      # max auto-persisted mappings per domain per run
    per_day: int      # max per UTC day
    per_30d: int      # rolling 30-day max; triggers learning pause if hit
    per_rule_share: float  # single rule may not exceed this fraction of 7-day auto-persists

    # Drift detection z-score thresholds
    drift_warn_z: float = 3.0    # surface WARNING invariant
    drift_defensive_z: float = 4.0  # raise auto-persist threshold 0.95 → 0.98 for 7d
    drift_pause_z: float = 5.0   # pause auto-persist for the domain

    # Tier-2 auto-persist numeric floor (score must meet this, not just "HIGH" level)
    tier2_score_floor: float = 0.95

    # Cooldown: fingerprint must have been seen at least this many hours ago
    cooldown_hours: int = 24

    # Minimum observation count before auto-persist (unless rule is "single-shot trustworthy")
    min_observation_count: int = 2


DEFAULT_BUDGET = Budget(
    per_run=50,
    per_day=200,
    per_30d=2000,
    per_rule_share=0.60,
)

# Domains with non-default profiles
DOMAIN_BUDGETS: dict[str, Budget] = {
    "categorization": Budget(
        per_run=200,
        per_day=500,
        per_30d=5000,
        per_rule_share=0.60,
    ),
    "parser": Budget(
        per_run=10,
        per_day=20,
        per_30d=100,
        per_rule_share=0.60,
    ),
}


def get(domain_name: str) -> Budget:
    """Return budget for a domain, falling back to DEFAULT_BUDGET."""
    return DOMAIN_BUDGETS.get(domain_name, DEFAULT_BUDGET)
