"""Domain protocol — interface every matching domain must implement.

Domains are NOT required to subclass DomainBase, but they must expose the
same attributes and methods. Protocol-style duck typing is used so domains
written before this class existed can conform incrementally.
"""
from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from finance.matching.fingerprint import Fingerprint
from finance.matching.rules import Rule, RuleResult


@runtime_checkable
class Domain(Protocol):
    """The interface that every matching domain must satisfy."""

    name: str             # "coretax" | "dedup" | "categorization" | "parser"
    table_prefix: str     # "matching_coretax" | "matching_dedup" | ...
    engine_version: int   # bump when rule semantics change
    fingerprint_version: int  # bump when canonicalization changes

    def normalize(self, row: dict) -> dict:
        """Explicit, versioned normalization step. Engine never normalizes."""
        ...

    def derive(self, row: dict) -> Fingerprint:
        """Return a Fingerprint for the source row."""
        ...

    def target_universe(self, conn, **kwargs) -> Iterable[Any]:
        """Return all valid targets for this domain."""
        ...

    def rules(self) -> list[Rule]:
        """Return the ordered rule catalog."""
        ...

    def resolve_conflict(self, candidates: list[dict]) -> dict | None:
        """Pick a winner from multiple candidates; return None to punt to queue.

        Must be deterministic. The chosen winner AND losing candidates with
        scores AND rationale must be logged by the caller.
        """
        ...

    def idempotency_key(self, row: dict) -> str:
        """Stable per-row key for dedup of repeated classify() calls."""
        ...

    def on_persist(self, mapping: dict) -> None:
        """Domain-specific side effects after a mapping is persisted."""
        ...
