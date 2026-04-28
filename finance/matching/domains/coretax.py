"""CoreTax domain adapter — wraps the coretax matching engine.

When CORETAX_USE_GENERIC_ENGINE=true, the coretax reconcile/suggest/mapping
surface delegates through this adapter to the generic engine.

When the flag is false (default), finance.coretax.* modules continue to be
used directly — this file is not imported.

This adapter presents the same external surface as the legacy coretax modules
so callers (finance.coretax.reconcile, finance/api.py, etc.) are unchanged.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from finance.matching.fingerprint import Fingerprint, sha256_hex, norm
from finance.matching.rules import Rule, RuleResult
from finance.matching.suggest import Suggestion


# ── Feature flag ─────────────────────────────────────────────────────────────

USE_GENERIC_ENGINE = os.environ.get("CORETAX_USE_GENERIC_ENGINE", "false").lower() == "true"

DOMAIN_NAME = "coretax"
FINGERPRINT_VERSION = 1
ENGINE_VERSION = 1


# ── Fingerprint derivation (mirrors finance.coretax.fingerprint) ─────────────


def _fp_norm(text: str) -> str:
    return norm(text)


def derive_fingerprint(row: dict) -> Fingerprint:
    """Derive a Fingerprint from a PWM source row."""
    kind = row.get("source_kind")
    if kind == "account_balance":
        inst = _fp_norm(row.get("institution", ""))
        acct = _fp_norm(row.get("account", ""))
        raw = f"{inst}:{acct}"
        return Fingerprint(
            identity_hash=sha256_hex(raw),
            identity_raw=raw,
            matching_features={"institution": inst, "account": acct},
            fingerprint_version=FINGERPRINT_VERSION,
        )
    if kind == "holding":
        isin = _fp_norm(row.get("isin_or_code", ""))
        if isin:
            return Fingerprint(
                identity_hash=isin,
                identity_raw=isin,
                matching_features={"isin": isin},
                fingerprint_version=FINGERPRINT_VERSION,
            )
        asset_class = _fp_norm(row.get("asset_class", ""))
        inst = _fp_norm(row.get("institution", ""))
        asset_name = _fp_norm(row.get("asset_name", ""))
        owner = _fp_norm(row.get("owner", ""))
        raw = f"{asset_class}:{inst}:{asset_name}:{owner}"
        return Fingerprint(
            identity_hash=sha256_hex(raw),
            identity_raw=raw,
            matching_features={"asset_class": asset_class, "institution": inst,
                               "asset_name": asset_name, "owner": owner},
            fingerprint_version=FINGERPRINT_VERSION,
        )
    if kind == "liability":
        liab_type = _fp_norm(row.get("liability_type", ""))
        liab_name = _fp_norm(row.get("liability_name", ""))
        owner = _fp_norm(row.get("owner", ""))
        raw = f"{liab_type}:{liab_name}:{owner}"
        return Fingerprint(
            identity_hash=sha256_hex(raw),
            identity_raw=raw,
            matching_features={"liability_type": liab_type, "liability_name": liab_name,
                               "owner": owner},
            fingerprint_version=FINGERPRINT_VERSION,
        )
    raise ValueError(f"Unknown source_kind: {kind!r}")


# ── CoreTax domain class ─────────────────────────────────────────────────────


class CoreTaxDomain:
    name = DOMAIN_NAME
    table_prefix = f"matching_{DOMAIN_NAME}"
    engine_version = ENGINE_VERSION
    fingerprint_version = FINGERPRINT_VERSION

    def normalize(self, row: dict) -> dict:
        return row  # PWM rows are already normalized at load time

    def derive(self, row: dict) -> Fingerprint:
        return derive_fingerprint(row)

    def target_universe(self, conn, tax_year: int = None, **kwargs) -> Iterable[dict]:
        from finance.coretax.db import get_rows_for_year
        if tax_year is None:
            return []
        return get_rows_for_year(conn, tax_year)

    def rules(self) -> list[Rule]:
        return _CORETAX_RULES

    def resolve_conflict(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None
        sorted_cands = sorted(candidates, key=lambda c: (-c["score"], c["target_key"]))
        if len(sorted_cands) >= 2:
            margin = sorted_cands[0]["score"] - sorted_cands[1]["score"]
            if margin < 0.10:
                return None  # ambiguous → suggestion queue
        return sorted_cands[0]

    def idempotency_key(self, row: dict) -> str:
        fp = self.derive(self.normalize(row))
        return fp.identity_hash

    def build_indexes(self, conn, tax_year: int = None, **kwargs) -> dict:
        from finance.coretax.db import get_rows_for_year
        from finance.coretax.utils import extract_account_number, extract_isin
        if tax_year is None:
            return {}
        rows = get_rows_for_year(conn, tax_year)
        isin_index: dict[str, list[dict]] = {}
        account_index: dict[str, list[dict]] = {}
        kode_index: dict[str, list[dict]] = {}
        for r in rows:
            kode = r.get("kode_harta") or ""
            kode_index.setdefault(kode, []).append(r)
            for field in ("keterangan", "notes_internal"):
                text = r.get(field) or ""
                isin = extract_isin(text)
                if isin:
                    isin_index.setdefault(isin, []).append(r)
                    break
            if kode == "012":
                acct = extract_account_number(r.get("keterangan"))
                if acct:
                    account_index.setdefault(acct, []).append(r)
        return {"isin_index": isin_index, "account_index": account_index,
                "kode_index": kode_index, "rows": rows}

    def on_persist(self, mapping: dict) -> None:
        pass  # no domain-specific side effects in Phase A


# ── Tier-2 rules ─────────────────────────────────────────────────────────────


def _rule_isin_exact_unique(source_row: dict, indexes: dict) -> RuleResult:
    isin_index = indexes.get("isin_index", {})
    isin = (source_row.get("isin_or_code") or "").strip()
    if not isin:
        return RuleResult(fired=False, target_key=None, score=0.0,
                          reason="no ISIN", rule_name="isin_exact_unique", tier=2,
                          single_shot_trustworthy=True)
    matches = isin_index.get(isin, [])
    if len(matches) == 1:
        return RuleResult(fired=True, target_key=matches[0]["stable_key"], score=1.0,
                          reason=f"ISIN {isin} matches exactly one CoreTax row",
                          rule_name="isin_exact_unique", tier=2,
                          single_shot_trustworthy=True)
    return RuleResult(fired=False, target_key=None, score=0.0,
                      reason=f"ISIN {isin} matched {len(matches)} rows",
                      rule_name="isin_exact_unique", tier=2, single_shot_trustworthy=True)


def _rule_account_number_exact_unique(source_row: dict, indexes: dict) -> RuleResult:
    account_index = indexes.get("account_index", {})
    acct = (source_row.get("account") or "").strip()
    if not acct:
        return RuleResult(fired=False, target_key=None, score=0.0,
                          reason="no account number", rule_name="account_number_exact_unique",
                          tier=2, single_shot_trustworthy=True)
    matches = account_index.get(acct, [])
    if len(matches) == 1:
        return RuleResult(fired=True, target_key=matches[0]["stable_key"], score=1.0,
                          reason=f"Account {acct} matches exactly one kode-012 row",
                          rule_name="account_number_exact_unique", tier=2,
                          single_shot_trustworthy=True)
    return RuleResult(fired=False, target_key=None, score=0.0,
                      reason=f"Account {acct} matched {len(matches)} rows",
                      rule_name="account_number_exact_unique", tier=2,
                      single_shot_trustworthy=True)


_CORETAX_RULES: list[Rule] = [
    Rule(
        name="isin_exact_unique",
        tier=2,
        base_score=1.0,
        single_shot_trustworthy=True,
        fn=_rule_isin_exact_unique,
    ),
    Rule(
        name="account_number_exact_unique",
        tier=2,
        base_score=1.0,
        single_shot_trustworthy=True,
        fn=_rule_account_number_exact_unique,
    ),
]


# ── Singleton ─────────────────────────────────────────────────────────────────

domain = CoreTaxDomain()


# ── Suggestion generation (mirrors finance.coretax.suggest) ──────────────────


def suggest_for_unmapped(conn, tax_year: int, unmapped: list[dict],
                         rejected: set[tuple[str, str, str]] | None = None) -> list[dict]:
    """Generate ranked suggestions for unmapped PWM items using the generic engine.

    Mirrors the interface of finance.coretax.suggest.suggest_mappings_for_unmapped.
    The rejected set uses (match_kind, match_value, target_stable_key) for
    backward compat; internally mapped to (identity_hash, target_key).
    """
    from finance.matching.suggest import Suggestion, rank_suggestions, filter_rejected
    from finance.matching.storage import get_rejected_pairs

    rejected_pairs = get_rejected_pairs(conn, DOMAIN_NAME)

    indexes = domain.build_indexes(conn, tax_year=tax_year)
    suggestions_out: list[dict] = []

    for item in unmapped:
        fp = derive_fingerprint({**item.get("payload", {}),
                                 "source_kind": item.get("source_kind", "")})
        suggestions: list[Suggestion] = []

        for rule in domain.rules():
            result = rule.apply(item.get("payload", {}), indexes)
            if not result.fired or result.target_key is None:
                continue
            if (fp.identity_hash, result.target_key) in rejected_pairs:
                continue
            suggestions.append(Suggestion(
                identity_hash=fp.identity_hash,
                identity_raw=fp.identity_raw,
                target_key=result.target_key,
                confidence_score=result.score,
                rule=result.rule_name,
                reason=result.reason,
                source_kind=item.get("source_kind", ""),
                domain=DOMAIN_NAME,
            ))

        # Also apply signature-based lower-confidence rules from the legacy suggest module
        kode_index = indexes.get("kode_index", {})
        kode_owner_index: dict = {}
        for r in indexes.get("rows", []):
            kode = r.get("kode_harta") or ""
            owner = (r.get("owner") or "").strip().lower()
            kode_owner_index.setdefault((kode, owner), []).append(r)

        from finance.coretax.suggest import _suggest_signature
        from finance.coretax.taxonomy import infer_kode_harta
        source_kind = item.get("source_kind", "")
        payload = item.get("payload", {})
        if fp.identity_raw and ":" in fp.identity_raw:
            sig_suggestions = _suggest_signature(
                fp.identity_hash, fp.identity_hash, fp.identity_raw,
                source_kind, payload, kode_index, kode_owner_index,
                {r["stable_key"]: r for r in indexes.get("rows", [])},
            )
            for s in sig_suggestions:
                if (fp.identity_hash, s.target_stable_key) in rejected_pairs:
                    continue
                suggestions.append(Suggestion(
                    identity_hash=fp.identity_hash,
                    identity_raw=fp.identity_raw,
                    target_key=s.target_stable_key,
                    confidence_score=s.confidence_score,
                    rule=s.rule,
                    reason=s.reason,
                    source_kind=source_kind,
                    domain=DOMAIN_NAME,
                ))

        ranked = rank_suggestions(suggestions)
        for s in ranked:
            d = {
                "target_stable_key": s.target_key,
                "confidence_score": s.confidence_score,
                "rule": s.rule,
                "reason": s.reason,
                "match_kind": item.get("match_kind", ""),
                "match_value": item.get("match_value", ""),
                "pwm_label": item.get("pwm_label", ""),
                "source_kind": s.source_kind,
                "fingerprint_raw": fp.identity_raw,
                # Enrich with target kode
                "target_kode_harta": _target_kode(s.target_key, indexes),
            }
            suggestions_out.append(d)

    return suggestions_out


def _target_kode(target_key: str, indexes: dict) -> str:
    for r in indexes.get("rows", []):
        if r["stable_key"] == target_key:
            return r.get("kode_harta", "")
    return ""
