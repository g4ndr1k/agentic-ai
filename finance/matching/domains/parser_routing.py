"""Parser routing domain adapter.

Maps the legacy parsers.router can_parse() cascade onto the generic engine.

Fingerprint:
  identity_hash = sha256(producer | creator | norm(page1_text)[:1000])
  — stable for a given PDF template; different months from the same bank
  template produce the same hash, so future imports hit Tier-1.

Tier-2 rule:
  A single composite rule ("parser_priority_cascade") applies all can_parse()
  calls in the exact legacy priority order and returns the first match.
  Score = 1.0 (deterministic, binary outcome). No conflict resolution needed.
  single_shot_trustworthy = True — one successful parse is sufficient to
  auto-persist the signature; no cooldown observation count required.

Future (Phase B.9): a separate "ambiguity scanner" rule can run all can_parse()
calls in parallel to detect PDFs where >1 parser fires, surfacing a chooser UI.
This is additive and doesn't change the composite rule.

Flag: PARSER_USE_ENGINE=true (default false)
"""
from __future__ import annotations

import os
from typing import Iterable

from finance.matching.fingerprint import Fingerprint, sha256_hex, norm
from finance.matching.rules import Rule, RuleResult

DOMAIN_NAME = "parser"
FINGERPRINT_VERSION = 1
ENGINE_VERSION = 1

USE_ENGINE = os.environ.get("PARSER_USE_ENGINE", "false").lower() == "true"


# ── Parser priority catalog ───────────────────────────────────────────────────
# Order matches parsers/router.py exactly.
# (module_name, uses_combined) where uses_combined=True means page1+page2 text.

def _build_priority() -> list[tuple[str, bool]]:
    """Return ordered list of (parser_name, uses_combined)."""
    from parsers import (
        permata_cc, permata_rdn, permata_usd_savings, permata_savings,
        bca_cc, bca_rdn, bca_savings,
        maybank_consol, maybank_cc,
        cimb_niaga_cc, cimb_niaga_consol,
        ipot_portfolio, ipot_statement,
        bni_sekuritas_legacy, bni_sekuritas,
    )
    entries: list[tuple[str, object, bool]] = [
        ("permata_cc",          permata_cc,          False),
        ("permata_rdn",         permata_rdn,          False),
        ("permata_usd_savings", permata_usd_savings,  False),
        ("permata_savings",     permata_savings,      False),
        ("bca_cc",              bca_cc,               False),
        ("bca_rdn",             bca_rdn,              False),
        ("bca_savings",         bca_savings,          False),
        ("maybank_consol",      maybank_consol,       True),
        ("maybank_cc",          maybank_cc,           False),
        ("cimb_niaga_cc",       cimb_niaga_cc,        True),
        ("cimb_niaga_consol",   cimb_niaga_consol,    False),
        ("ipot_portfolio",      ipot_portfolio,        False),
        ("ipot_statement",      ipot_statement,        False),
        ("bni_sekuritas_legacy",bni_sekuritas_legacy,  False),
        ("bni_sekuritas",       bni_sekuritas,         False),
    ]
    try:
        from parsers import stockbit_sekuritas
        entries.append(("stockbit_sekuritas", stockbit_sekuritas, False))
    except ImportError:
        pass
    return entries


# ── Fingerprint derivation ────────────────────────────────────────────────────


def derive_fingerprint(row: dict) -> Fingerprint:
    """Derive a stable PDF signature fingerprint.

    row must contain: page1_text, page2_text (optional), producer, creator.
    """
    producer = norm(row.get("producer", ""))
    creator = norm(row.get("creator", ""))
    page1_head = norm(row.get("page1_text", ""))[:1000]
    raw = f"{producer}|{creator}|{page1_head}"
    return Fingerprint(
        identity_hash=sha256_hex(raw),
        identity_raw=raw[:300],   # truncate for storage
        matching_features={"producer": producer, "creator": creator},
        fingerprint_version=FINGERPRINT_VERSION,
    )


# ── Tier-2 composite rule ─────────────────────────────────────────────────────


def _parser_priority_cascade(source_row: dict, indexes: dict) -> RuleResult:
    """Apply all can_parse() calls in legacy priority order; return first match.

    This single composite rule exactly replicates the legacy router's
    first-match-wins behavior. Score = 1.0 (deterministic).
    """
    page1 = source_row.get("page1_text", "")
    combined = page1 + "\n" + source_row.get("page2_text", "")

    for name, module, uses_combined in _build_priority():
        text = combined if uses_combined else page1
        if module.can_parse(text):
            return RuleResult(
                fired=True,
                target_key=name,
                score=1.0,
                reason=f"{name}.can_parse() matched",
                rule_name="parser_priority_cascade",
                tier=2,
                single_shot_trustworthy=True,
            )
    return RuleResult(
        fired=False,
        target_key=None,
        score=0.0,
        reason="no parser can_parse() matched",
        rule_name="parser_priority_cascade",
        tier=2,
        single_shot_trustworthy=True,
    )


_COMPOSITE_RULE = Rule(
    name="parser_priority_cascade",
    tier=2,
    base_score=1.0,
    single_shot_trustworthy=True,
    fn=_parser_priority_cascade,
)


# ── Domain class ──────────────────────────────────────────────────────────────


class ParserRoutingDomain:
    name = DOMAIN_NAME
    table_prefix = f"matching_{DOMAIN_NAME}"
    engine_version = ENGINE_VERSION
    fingerprint_version = FINGERPRINT_VERSION

    def normalize(self, row: dict) -> dict:
        return row

    def derive(self, row: dict) -> Fingerprint:
        return derive_fingerprint(row)

    def target_universe(self, conn, **kwargs) -> Iterable[str]:
        return [name for name, _, _ in _build_priority()]

    def rules(self) -> list[Rule]:
        return [_COMPOSITE_RULE]

    def resolve_conflict(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["score"])

    def idempotency_key(self, row: dict) -> str:
        return derive_fingerprint(row).identity_hash

    def on_persist(self, mapping: dict) -> None:
        pass


domain = ParserRoutingDomain()
