"""Phase 0 snapshot tests — parser routing behavior lock.

These tests verify that the detection logic in parsers/router.py produces
the expected parser name for each fixture row. They are text-based (no PDFs)
so they run in CI without real bank statements.

The fixture is tests/matching/fixtures/parser_routing_fixture.json.

Adding a new parser: add an entry to the fixture and verify the test passes
BEFORE merging the parser. This ensures the fixture grows alongside the code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import all parsers' can_parse functions
from parsers import (
    permata_cc, permata_savings, permata_rdn, permata_usd_savings,
    bca_cc, bca_savings, bca_rdn,
    maybank_cc, maybank_consol,
    cimb_niaga_cc, cimb_niaga_consol,
    ipot_portfolio, ipot_statement,
    bni_sekuritas_legacy, bni_sekuritas,
)

try:
    from parsers import stockbit_sekuritas
    _HAS_STOCKBIT = True
except ImportError:
    _HAS_STOCKBIT = False


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "parser_routing_fixture.json"


def _detect_parser(page1_text: str, page2_text: str) -> str | None:
    """Mirror the detection priority in parsers.router.detect_and_parse, text-only."""
    combined = page1_text + "\n" + page2_text

    if permata_cc.can_parse(page1_text):
        return "permata_cc"
    if permata_rdn.can_parse(page1_text):
        return "permata_rdn"
    if permata_usd_savings.can_parse(page1_text):
        return "permata_usd_savings"
    if permata_savings.can_parse(page1_text):
        return "permata_savings"
    if bca_cc.can_parse(page1_text):
        return "bca_cc"
    if bca_rdn.can_parse(page1_text):
        return "bca_rdn"
    if bca_savings.can_parse(page1_text):
        return "bca_savings"
    if maybank_consol.can_parse(combined):
        return "maybank_consol"
    if maybank_cc.can_parse(page1_text):
        return "maybank_cc"
    if cimb_niaga_cc.can_parse(combined):
        return "cimb_niaga_cc"
    if cimb_niaga_consol.can_parse(page1_text):
        return "cimb_niaga_consol"
    if ipot_portfolio.can_parse(page1_text):
        return "ipot_portfolio"
    if ipot_statement.can_parse(page1_text):
        return "ipot_statement"
    if bni_sekuritas_legacy.can_parse(page1_text):
        return "bni_sekuritas_legacy"
    if bni_sekuritas.can_parse(page1_text):
        return "bni_sekuritas"
    if _HAS_STOCKBIT and stockbit_sekuritas.can_parse(page1_text):
        return "stockbit_sekuritas"
    return None


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case", _load_fixture(), ids=[c["id"] for c in _load_fixture()])
def test_parser_routing_snapshot(case):
    """Each fixture case must route to the expected parser (or None for unknown)."""
    detected = _detect_parser(case["page1_text"], case["page2_text"])
    expected = case["expected_parser"]
    assert detected == expected, (
        f"[{case['id']}] {case['description']!r}: "
        f"detected={detected!r}, expected={expected!r}"
    )


def test_fixture_coverage():
    """Every fixture entry has a unique id and non-empty description."""
    cases = _load_fixture()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "Fixture has duplicate IDs"
    for case in cases:
        assert case.get("description"), f"Missing description for {case['id']}"
