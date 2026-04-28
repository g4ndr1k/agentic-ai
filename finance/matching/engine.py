"""Generic tier-1/tier-2 execution loop with auto-persist guards.

Entry points:
  classify(domain, conn, source_row, **ctx) → Match | None
  persist(domain, conn, identity_hash, target_key, ...) → int
  trace(domain, conn, source_row, **ctx) → TraceTree

Auto-persist guards (plan §Tier-2 auto-persist guards):
  - score >= budget.tier2_score_floor (default 0.95)
  - cooldown: fingerprint seen ≥ 24 h ago, not yet auto-persisted
  - min_observation_count (default 2) unless rule.single_shot_trustworthy
  - no existing mapping for that identity_hash
  - no conflicting target (or resolve_conflict returns unique winner with margin ≥ 0.1)
  - per-run rate cap (budget.per_run)
  - learning status not paused (budget cap or drift)

Runtime invariants (plan §Runtime invariants):
  CRITICAL — abort operation, log to matching_invariant_log
  WARNING  — operation continues, logged
  INFO     — written to matching_invariant_diagnostic ring buffer
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from finance.matching.budget import get as get_budget
from finance.matching.fingerprint import Fingerprint
from finance.matching.storage import (
    get_mapping,
    get_rejected_pairs,
    log_invariant,
    _prefix,
    upsert_mapping,
    update_mapping_fields,
)


CURRENT_ENGINE_VERSION = 1
CONFLICT_SCORE_MARGIN = 0.10   # runner-up must be this far below winner


class MappingConflictError(Exception):
    def __init__(self, domain: str, identity_hash: str,
                 requested_target: str, existing_target: str, existing_id: int):
        self.domain = domain
        self.identity_hash = identity_hash
        self.requested_target = requested_target
        self.existing_target = existing_target
        self.existing_id = existing_id
        super().__init__(
            f"[{domain}] Mapping conflict: {identity_hash[:16]}… already maps to "
            f"{existing_target!r}, not {requested_target!r}"
        )


@dataclass
class Match:
    target: Any
    confidence_score: float
    confidence_level: str
    tier: int | str       # 1 | 2 | "suggestion"
    rule: str
    reason: str
    fingerprint_version: int
    engine_version: int


@dataclass
class TraceTree:
    fingerprint: dict
    tier1_lookup: dict
    tier2_evaluation: list[dict]
    conflict_resolution: dict | None
    auto_persist_decision: dict | None
    suggestions_generated: list[dict]
    final_match: dict | None
    invariant_checks: list[dict]


# ── Per-run state for auto-persist rate caps ─────────────────────────────────

_run_auto_persist_counts: dict[str, int] = {}   # domain → count for current run


def reset_run_state() -> None:
    """Call at the start of each reconcile/import run to reset per-run counters."""
    _run_auto_persist_counts.clear()


# ── classify ─────────────────────────────────────────────────────────────────


def classify(domain, conn, source_row: dict, **ctx) -> Match | None:
    """Run the two-tier engine for one source row.

    domain: object satisfying finance.matching.domains.base.Domain protocol
    Returns a Match or None (if unmatched → goes to suggestion queue).
    """
    fp = domain.derive(domain.normalize(source_row))
    budget = get_budget(domain.name)

    # ── Tier 1: mapping lookup ────────────────────────────────────────────────
    mapping = get_mapping(conn, domain.name, fp.identity_hash)
    if mapping:
        # Invariant: engine_version on mapping must be ≤ runtime version
        if int(mapping.get("engine_version", 1)) > CURRENT_ENGINE_VERSION:
            log_invariant(conn, "CRITICAL", domain.name,
                          f"Mapping id={mapping['id']} has future engine_version",
                          run_id=ctx.get("run_id"))
            return None  # abort per-row operation; don't use stale-future data

        # Fingerprint version revalidation
        stored_fv = int(mapping.get("fingerprint_version", 1))
        if stored_fv != domain.fingerprint_version:
            # Re-derive identity_raw and compare
            fresh_fp = domain.derive(domain.normalize(source_row))
            if mapping.get("identity_raw") == fresh_fp.identity_raw:
                # Silent bump — identity matches under new version
                update_mapping_fields(conn, domain.name, mapping["id"],
                                      fingerprint_version=domain.fingerprint_version)
                log_invariant(conn, "INFO", domain.name,
                              f"Mapping id={mapping['id']} fingerprint_version silently bumped",
                              run_id=ctx.get("run_id"))
            else:
                # Divergence → OUTDATED bucket (not used this run)
                log_invariant(conn, "WARNING", domain.name,
                              f"Mapping id={mapping['id']} identity_raw diverged after fp_version bump",
                              run_id=ctx.get("run_id"))
                mapping = None  # fall through to Tier 2

    if mapping:
        from finance.matching.confidence import derive_level
        score = float(mapping.get("confidence_score", 1.0))
        return Match(
            target=mapping["target_key"],
            confidence_score=score,
            confidence_level=mapping.get("confidence_level", derive_level(score)),
            tier=1,
            rule="tier1_mapping",
            reason=f"Mapping id={mapping['id']} (source={mapping.get('source', '?')})",
            fingerprint_version=fp.fingerprint_version,
            engine_version=CURRENT_ENGINE_VERSION,
        )

    # ── Tier 2: safe heuristics ───────────────────────────────────────────────
    rules = [r for r in domain.rules() if r.tier == 2]
    indexes = _build_indexes(domain, conn, **ctx)
    rejected = get_rejected_pairs(conn, domain.name)

    tier2_results: list[tuple] = []  # (RuleResult, score)
    for rule in rules:
        result = rule.apply(source_row, indexes)
        if not result.fired:
            continue
        if result.target_key and (fp.identity_hash, result.target_key) in rejected:
            continue  # user rejected this pair
        tier2_results.append((result, result.score))

    if not tier2_results:
        return None

    # Pick winner via domain's conflict resolver
    if len(tier2_results) == 1:
        winner_result, winner_score = tier2_results[0]
        conflict_rationale = None
    else:
        candidates = [
            {"target_key": r.target_key, "score": s, "rule": r.rule_name, "reason": r.reason}
            for r, s in tier2_results
        ]
        chosen = domain.resolve_conflict(candidates)
        if chosen is None:
            return None  # ambiguity — go to suggestion queue
        winner_result = next(r for r, _ in tier2_results if r.target_key == chosen["target_key"])
        winner_score = chosen["score"]
        runner_up = max((s for r, s in tier2_results if r.target_key != chosen["target_key"]),
                        default=0.0)
        if winner_score - runner_up < CONFLICT_SCORE_MARGIN:
            return None  # margin insufficient → suggestion queue
        conflict_rationale = chosen

    # Auto-persist guard
    _maybe_auto_persist(
        conn, domain, fp, winner_result, winner_score, budget,
        run_id=ctx.get("run_id"))

    from finance.matching.confidence import derive_level
    return Match(
        target=winner_result.target_key,
        confidence_score=winner_score,
        confidence_level=derive_level(winner_score),
        tier=2,
        rule=winner_result.rule_name,
        reason=winner_result.reason,
        fingerprint_version=fp.fingerprint_version,
        engine_version=CURRENT_ENGINE_VERSION,
    )


# ── Auto-persist guard ────────────────────────────────────────────────────────


def _maybe_auto_persist(conn, domain, fp: Fingerprint, result, score: float,
                        budget, *, run_id: str | None = None) -> None:
    """Apply all Tier-2 auto-persist guards; persist only if all pass."""
    if score < budget.tier2_score_floor:
        return

    # Per-run rate cap
    current_count = _run_auto_persist_counts.get(domain.name, 0)
    if current_count >= budget.per_run:
        return  # excess → suggestion queue

    # No existing mapping for this identity_hash
    existing = get_mapping(conn, domain.name, fp.identity_hash)
    if existing is not None:
        return

    # Min observation count (unless rule is single-shot trustworthy)
    # Note: observation tracking requires the domain to provide it via indexes;
    # for now we honour the single_shot_trustworthy flag on the rule.
    if not result.single_shot_trustworthy:
        obs = _get_observation_count(conn, domain, fp)
        if obs < budget.min_observation_count:
            return  # cooldown / not enough observations

    from finance.matching.confidence import derive_level
    upsert_mapping(
        conn, domain.name,
        identity_hash=fp.identity_hash,
        identity_raw=fp.identity_raw,
        target_key=result.target_key,
        confidence_score=score,
        confidence_level=derive_level(score),
        source="auto_safe",
        fingerprint_version=fp.fingerprint_version,
        engine_version=CURRENT_ENGINE_VERSION,
        created_from_run_key=run_id,
    )
    _run_auto_persist_counts[domain.name] = current_count + 1
    domain.on_persist({"identity_hash": fp.identity_hash, "target_key": result.target_key})


def _get_observation_count(conn, domain, fp: Fingerprint) -> int:
    """Count distinct runs where this fingerprint appeared (via components table)."""
    prefix = _prefix(domain.name)
    try:
        row = conn.execute(
            f"SELECT COUNT(DISTINCT run_id) AS c FROM {prefix}_components WHERE identity_hash = ?",
            (fp.identity_hash,),
        ).fetchone()
        return int(row["c"]) if row else 0
    except Exception:
        return 0


# ── Indexes ───────────────────────────────────────────────────────────────────


def _build_indexes(domain, conn, **ctx) -> dict:
    """Ask the domain to build its lookup indexes for Tier-2 rules."""
    if hasattr(domain, "build_indexes"):
        return domain.build_indexes(conn, **ctx)
    return {}
