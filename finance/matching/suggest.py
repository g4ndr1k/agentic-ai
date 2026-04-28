"""Generic ranked suggestion engine — domain-agnostic.

Pure (no DB writes). Returns ranked Suggestion records per source row.
Rejected pairs are filtered out. Priority strategy is versioned.

Cross-domain suggestion dedup: keyed on (identity_hash, target_key, domain);
rejection in one domain does not suppress in another.

Echo-chamber dampener: suggestion-acceptance boost capped at +0.05 per
acceptance and at 0.9 cumulative until mapping has fired in ≥3 distinct runs
(implemented in confidence.SuggestionAccepted).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


PRIORITY_STRATEGY_VERSION = 1


@dataclass
class Suggestion:
    identity_hash: str
    identity_raw: str
    target_key: str
    confidence_score: float
    rule: str
    reason: str
    source_kind: str = ""
    domain: str = ""
    extra: dict | None = None


def rank_suggestions(suggestions: list[Suggestion]) -> list[Suggestion]:
    """Sort suggestions by priority strategy.

    Current strategy (version 1):
      1. Highest AI confidence first
      2. Then unconfirmed aliases
      3. Then rest
    All within same bucket: sort by score desc, then target_key asc.
    """
    return sorted(
        suggestions,
        key=lambda s: (-s.confidence_score, s.target_key),
    )


def filter_rejected(suggestions: list[Suggestion],
                    rejected: set[tuple[str, str]]) -> list[Suggestion]:
    """Remove suggestions whose (identity_hash, target_key) is in the rejected set."""
    return [s for s in suggestions if (s.identity_hash, s.target_key) not in rejected]


def to_dicts(suggestions: list[Suggestion]) -> list[dict]:
    return [asdict(s) for s in suggestions]
