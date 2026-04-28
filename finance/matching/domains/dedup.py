"""Bank import dedup domain adapter.

Handles parser-variant reconciliation via the generic matching engine.

Exact duplicates (identical hash) are caught by the importer's O(1) set
check before classify() is ever called — that path needs no engine.

This domain handles the parser-variant case: two rows for the same
transaction from different parser versions produce different descriptions
but an identical (date, amount, institution, account, owner) identity key.
When the engine confirms a "merge", it auto-persists so the next import of
the same loose fingerprint skips the similarity check entirely (Tier-1 hit).

Fingerprint:
  identity_hash = sha256(date|round(amount,2)|institution|account|owner)
  — identical for all parser variants of the same transaction

Tier-2 rule:
  "dedup_parser_variant" — uses existing_by_identity index to find the
  single candidate, then delegates to _should_reconcile_parser_variant().
  Returns "merge:{existing_hash}" on match.
  single_shot_trustworthy = True (deterministic; identity-key query always
  returns the same candidate for the same transaction).

Flag: DEDUP_USE_ENGINE=true (default false)
"""
from __future__ import annotations

import os
from typing import Iterable

from finance.matching.fingerprint import Fingerprint, sha256_hex, norm
from finance.matching.rules import Rule, RuleResult

DOMAIN_NAME = "dedup"
FINGERPRINT_VERSION = 1
ENGINE_VERSION = 1

USE_ENGINE = os.environ.get("DEDUP_USE_ENGINE", "false").lower() == "true"


# ── Fingerprint derivation ────────────────────────────────────────────────────


def _loose_canonical(row: dict) -> str:
    date = (row.get("date") or "").strip()
    amount = round(float(row.get("amount", 0)), 2)
    institution = norm(row.get("institution", ""))
    account = (row.get("account") or "").strip()
    owner = norm(row.get("owner", ""))
    return f"{date}|{amount:.2f}|{institution}|{account}|{owner}"


def derive_fingerprint(row: dict) -> Fingerprint:
    """Derive a stable loose fingerprint for parser-variant detection.

    row must contain: date, amount, institution, account, owner.
    raw_description is stored in matching_features for diagnostics only —
    it is NOT part of the identity hash so parser variants share one hash.
    """
    canonical = _loose_canonical(row)
    return Fingerprint(
        identity_hash=sha256_hex(canonical),
        identity_raw=canonical[:300],
        matching_features={"raw_description": (row.get("raw_description") or "")[:200]},
        fingerprint_version=FINGERPRINT_VERSION,
    )


# ── Tier-2 rule ───────────────────────────────────────────────────────────────


def _dedup_parser_variant_rule(source_row: dict, indexes: dict) -> RuleResult:
    """Return "merge:{existing_hash}" if source_row is a parser variant of an existing txn."""
    from finance.importer import _should_reconcile_parser_variant  # lazy to avoid circular import

    identity_key = (
        (source_row.get("date") or "").strip(),
        round(float(source_row.get("amount", 0)), 2),
        (source_row.get("institution") or "").strip(),
        (source_row.get("account") or "").strip(),
        (source_row.get("owner") or "").strip(),
    )
    candidates = indexes.get("existing_by_identity", {}).get(identity_key, [])

    if len(candidates) != 1:
        return RuleResult(
            fired=False, target_key=None, score=0.0,
            reason=f"identity key has {len(candidates)} existing matches (need exactly 1)",
            rule_name="dedup_parser_variant", tier=2, single_shot_trustworthy=True,
        )

    existing = candidates[0]
    if _should_reconcile_parser_variant(
        existing.get("raw_description", ""), source_row.get("raw_description", "")
    ):
        return RuleResult(
            fired=True,
            target_key=f"merge:{existing['hash']}",
            score=1.0,
            reason=f"parser-variant of existing txn {existing['hash'][:12]}…",
            rule_name="dedup_parser_variant",
            tier=2,
            single_shot_trustworthy=True,
        )

    return RuleResult(
        fired=False, target_key=None, score=0.0,
        reason="identity-key match found but descriptions not reconcilable as parser variants",
        rule_name="dedup_parser_variant", tier=2, single_shot_trustworthy=True,
    )


_PARSER_VARIANT_RULE = Rule(
    name="dedup_parser_variant",
    tier=2,
    base_score=1.0,
    single_shot_trustworthy=True,
    fn=_dedup_parser_variant_rule,
)


# ── Domain class ──────────────────────────────────────────────────────────────


class DedupDomain:
    name = DOMAIN_NAME
    table_prefix = f"matching_{DOMAIN_NAME}"
    engine_version = ENGINE_VERSION
    fingerprint_version = FINGERPRINT_VERSION

    def normalize(self, row: dict) -> dict:
        return row

    def derive(self, row: dict) -> Fingerprint:
        return derive_fingerprint(row)

    def target_universe(self, conn, **kwargs) -> Iterable[str]:
        return []  # targets are dynamic: "merge:{existing_hash}"

    def build_indexes(self, conn, **kwargs) -> dict:
        """Return existing-by-identity index for Tier-2 rule.

        Accepts optional prebuilt_indexes kwarg from the importer to avoid
        reloading all transactions from the DB on every classify() call.
        """
        if "prebuilt_indexes" in kwargs:
            return kwargs["prebuilt_indexes"]

        rows = conn.execute(
            "SELECT hash, date, amount, raw_description, institution, account, owner "
            "FROM transactions"
        ).fetchall()
        by_identity: dict = {}
        for row in rows:
            key = (
                (row["date"] or "").strip(),
                round(float(row["amount"]), 2),
                (row["institution"] or "").strip(),
                (row["account"] or "").strip(),
                (row["owner"] or "").strip(),
            )
            by_identity.setdefault(key, []).append(dict(row))
        return {"existing_by_identity": by_identity}

    def rules(self) -> list[Rule]:
        return [_PARSER_VARIANT_RULE]

    def resolve_conflict(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["score"])

    def idempotency_key(self, row: dict) -> str:
        return derive_fingerprint(row).identity_hash

    def on_persist(self, mapping: dict) -> None:
        pass


domain = DedupDomain()
