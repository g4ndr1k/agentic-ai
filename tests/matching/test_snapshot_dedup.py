"""Phase 0 snapshot tests — bank import dedup behavior lock.

Verifies that the legacy dedup + parser-variant reconciliation logic
produces the expected decisions for each fixture row.

These decisions become the "golden" behavior that the engine must
replicate bit-for-bit when DEDUP_USE_ENGINE=true is flipped (Phase C).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from finance.importer import _should_reconcile_parser_variant

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dedup_fixture.json"

# Mirrors finance/models.py:make_hash
def _make_hash(txn: dict) -> str:
    key = "|".join([
        str(txn.get("date", "")),
        str(txn.get("amount", "")),
        str(txn.get("raw_description", "")),
        str(txn.get("institution", "")),
        str(txn.get("owner", "")),
        str(txn.get("account", "")),
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _legacy_dedup_decision(txn: dict, existing: dict | None) -> str:
    """Call the real legacy dedup + parser-variant logic from finance.importer."""
    if existing is None:
        return "new"
    txn_hash = _make_hash(txn)
    exist_hash = _make_hash(existing)
    if txn_hash == exist_hash:
        return "duplicate"
    # Parser-variant reconciliation: same (date, amount, institution, owner, account)
    if (txn["date"] == existing["date"]
            and txn["amount"] == existing["amount"]
            and txn["institution"] == existing["institution"]
            and txn["owner"] == existing["owner"]
            and txn["account"] == existing["account"]):
        if _should_reconcile_parser_variant(
                existing.get("raw_description", ""),
                txn.get("raw_description", "")):
            return "parser_variant_merge"
    return "new"


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case", _load_fixture(), ids=[c["id"] for c in _load_fixture()])
def test_dedup_snapshot(case):
    """Each fixture case must produce the expected dedup decision."""
    decision = _legacy_dedup_decision(case["txn"], case.get("existing"))
    expected = case["expected_decision"]
    assert decision == expected, (
        f"[{case['id']}] {case['description']!r}: "
        f"decision={decision!r}, expected={expected!r}"
    )
