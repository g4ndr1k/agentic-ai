"""Rule catalog primitives — domain-agnostic.

A Rule is a callable that takes a source row + target universe and returns
RuleResult. Domains register rule lists; the engine iterates them in tier order.

score = base_score + learned_adjustment  (learned_adjustment starts at 0)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class RuleResult:
    fired: bool
    target_key: str | None    # domain-specific target identifier; None if not fired
    score: float              # 0.0 – 1.0
    reason: str               # human-readable, shown in trace / UI tooltip
    rule_name: str            # e.g. "isin_exact_unique"
    tier: int                 # 1 = deterministic mapping lookup, 2 = safe heuristic
    single_shot_trustworthy: bool = False  # True → min_observation_count = 1 for auto-persist


@dataclass
class Rule:
    name: str
    tier: int
    base_score: float
    single_shot_trustworthy: bool = False
    # Callable: (source_row, indexes) → RuleResult
    fn: Callable[..., RuleResult] = field(repr=False, default=None)  # type: ignore[assignment]

    def apply(self, source_row: dict, indexes: dict) -> RuleResult:
        return self.fn(source_row, indexes)
