"""Expense categorization domain adapter.

Wraps the existing 4-layer Categorizer as a Tier-2 engine rule.

Fingerprint:
  identity_hash = sha256(normalize_alias_key(raw_description))
  — volatile tokens (numbers, dates, codes) are stripped, so recurring
  descriptions from the same merchant hash to the same value each month.

Target encoding:
  "merchant||category"  (double-pipe to avoid conflicts with single pipes
  that appear in some merchant names; split on first "||" only).

Tier-2 rule:
  "categorization_cascade" — delegates to Categorizer._categorize_legacy()
  (not the engine-aware categorize() to prevent recursion).
  Trustworthiness: Layer 1/2 results → single_shot_trustworthy=True;
                   Layer 3 (Ollama) → single_shot_trustworthy=False.
  Layer 4 (review queue) → rule returns fired=False so it reaches the
  suggestion queue rather than being silently skipped.

Shadow mode (CATEGORIZATION_USE_ENGINE=shadow):
  Both paths run; any disagreement between Tier-1 mapping and the legacy
  result is written to category_shadow_diff. Legacy result is returned
  unchanged. No effect on import output.

Engine true mode (CATEGORIZATION_USE_ENGINE=true):
  Tier-1 hit → return cached (merchant, category) without running legacy.
  Miss → legacy runs as Tier-2; Layer 1/2 results are auto-persisted.
"""
from __future__ import annotations

import os
from typing import Iterable

from finance.matching.fingerprint import Fingerprint, sha256_hex
from finance.matching.rules import Rule, RuleResult

DOMAIN_NAME = "categorization"
FINGERPRINT_VERSION = 1
ENGINE_VERSION = 1

USE_ENGINE = os.environ.get("CATEGORIZATION_USE_ENGINE", "false").lower()
# Values: "false" | "shadow" | "true"


# ── Fingerprint derivation ────────────────────────────────────────────────────


def derive_fingerprint(row: dict) -> Fingerprint:
    """Derive a stable fingerprint from the normalized raw description.

    row must contain: raw_description (required), owner, account (optional).
    """
    from finance.categorizer import normalize_alias_key
    desc = (row.get("raw_description") or "").strip()
    canonical = normalize_alias_key(desc) or desc  # fallback: keep original if all-numeric
    owner = (row.get("owner") or "").strip()
    account = (row.get("account") or "").strip()
    # Include owner+account so owner-specific aliases hash differently.
    # Generic aliases (no owner filter) still get a common hash per description.
    full_key = f"{canonical}|{owner}|{account}"
    return Fingerprint(
        identity_hash=sha256_hex(full_key),
        identity_raw=full_key[:300],
        matching_features={"raw_description": desc[:200], "owner": owner},
        fingerprint_version=FINGERPRINT_VERSION,
    )


def target_to_parts(target_key: str) -> tuple[str, str]:
    """Split "merchant||category" into (merchant, category)."""
    parts = target_key.split("||", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


# ── Tier-2 rule ───────────────────────────────────────────────────────────────


def _categorization_cascade_rule(source_row: dict, indexes: dict) -> RuleResult:
    """Run the legacy 4-layer categorizer; return the result as a RuleResult.

    Calls _categorize_legacy() directly to avoid recursion through the
    engine-aware categorize() entry point.
    """
    categorizer = indexes.get("categorizer")
    if categorizer is None:
        return RuleResult(
            fired=False, target_key=None, score=0.0,
            reason="no categorizer instance in indexes",
            rule_name="categorization_cascade", tier=2, single_shot_trustworthy=False,
        )

    desc = source_row.get("raw_description", "")
    owner = source_row.get("owner", "")
    account = source_row.get("account", "")

    result = categorizer._categorize_legacy(desc, owner=owner, account=account)

    # Layer 4 → review queue, no auto-persist
    if result.layer == 4 or (result.merchant is None and result.category is None):
        return RuleResult(
            fired=False, target_key=None, score=0.0,
            reason="layer 4 (review queue) — no auto-persist",
            rule_name="categorization_cascade", tier=2, single_shot_trustworthy=False,
        )

    target_key = f"{result.merchant or ''}||{result.category or ''}"
    # Layer 1/2 (alias/regex) are deterministic → auto-persist on first sight.
    # Layer 3 (Ollama) is non-deterministic → require observation count cooldown.
    trustworthy = result.layer in (1, 2)
    score = 1.0 if trustworthy else 0.80

    return RuleResult(
        fired=True,
        target_key=target_key,
        score=score,
        reason=f"layer{result.layer}:{result.confidence} → {target_key!r}",
        rule_name="categorization_cascade",
        tier=2,
        single_shot_trustworthy=trustworthy,
    )


_CASCADE_RULE = Rule(
    name="categorization_cascade",
    tier=2,
    base_score=1.0,
    single_shot_trustworthy=False,  # overridden per-result by the fn
    fn=_categorization_cascade_rule,
)


# ── Domain class ──────────────────────────────────────────────────────────────


class CategorizationDomain:
    name = DOMAIN_NAME
    table_prefix = f"matching_{DOMAIN_NAME}"
    engine_version = ENGINE_VERSION
    fingerprint_version = FINGERPRINT_VERSION

    def normalize(self, row: dict) -> dict:
        return row

    def derive(self, row: dict) -> Fingerprint:
        return derive_fingerprint(row)

    def target_universe(self, conn, **kwargs) -> Iterable[str]:
        return []  # dynamic: "merchant||category" pairs

    def build_indexes(self, conn, **kwargs) -> dict:
        """Pass the categorizer instance from ctx to the Tier-2 rule."""
        return {"categorizer": kwargs.get("categorizer")}

    def rules(self) -> list[Rule]:
        return [_CASCADE_RULE]

    def resolve_conflict(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["score"])

    def idempotency_key(self, row: dict) -> str:
        return derive_fingerprint(row).identity_hash

    def on_persist(self, mapping: dict) -> None:
        pass


domain = CategorizationDomain()
