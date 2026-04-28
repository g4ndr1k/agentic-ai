"""Phase B verification — parser routing domain.

Verifies:
1. The composite Tier-2 rule replicates legacy can_parse() priority exactly
   for all fixture cases (run-diff = 0 requirement from the plan).
2. Tier-1 mapping lookup hits after an auto-persisted Tier-2 match.
3. Unknown PDFs return None from classify() (no UnknownStatementError).
4. The partial signals collector works for diagnostics.
5. Engine + legacy produce identical parser names for all fixture cases.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from finance.matching.storage import ensure_domain_tables, ensure_global_tables
from finance.matching.engine import classify, reset_run_state
from finance.matching.domains.parser_routing import domain as parser_domain, derive_fingerprint
from finance.matching.storage import get_mapping

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "parser_routing_fixture.json"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_global_tables(c)
    ensure_domain_tables(c, "parser")
    yield c
    c.close()


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())


def _source_row(case: dict) -> dict:
    return {
        "page1_text": case["page1_text"],
        "page2_text": case["page2_text"],
        "producer": "",
        "creator": "",
    }


# ── Parity with legacy snapshot ───────────────────────────────────────────────


@pytest.mark.parametrize("case", _load_fixture(), ids=[c["id"] for c in _load_fixture()])
def test_engine_matches_legacy_snapshot(case, conn):
    """Engine + legacy cascade must agree on detected parser (or both None)."""
    reset_run_state()
    source = _source_row(case)
    match = classify(parser_domain, conn, source, run_id="phase-b-test")
    engine_result = match.target if match else None
    expected = case["expected_parser"]
    assert engine_result == expected, (
        f"[{case['id']}] {case['description']!r}: "
        f"engine={engine_result!r}, expected={expected!r}"
    )


# ── Tier-1 caching after first Tier-2 match ───────────────────────────────────


def test_tier1_hit_after_auto_persist(conn):
    """Second classify() of the same PDF signature hits Tier-1 (cached mapping)."""
    reset_run_state()
    bca_case = next(c for c in _load_fixture() if c["id"] == "bca_savings_001")
    source = _source_row(bca_case)
    fp = derive_fingerprint(source)

    # First call: Tier-2 run, should auto-persist
    match1 = classify(parser_domain, conn, source, run_id="run-001")
    assert match1 is not None
    assert match1.tier == 2
    assert match1.target == "bca_savings"

    # Verify mapping was auto-persisted
    mapping = get_mapping(conn, "parser", fp.identity_hash)
    assert mapping is not None, "Tier-2 match should have been auto-persisted"
    assert mapping["target_key"] == "bca_savings"
    assert mapping["source"] == "auto_safe"

    # Second call: same source row → Tier-1 hit
    match2 = classify(parser_domain, conn, source, run_id="run-002")
    assert match2 is not None
    assert match2.tier == 1, "Second call should hit Tier-1 cached mapping"
    assert match2.target == "bca_savings"


def test_unknown_pdf_returns_none(conn):
    """classify() returns None for an unrecognized PDF — no exception."""
    reset_run_state()
    source = {
        "page1_text": "Some Random Bank Account Statement 2024",
        "page2_text": "",
        "producer": "",
        "creator": "",
    }
    match = classify(parser_domain, conn, source, run_id="run-unknown")
    assert match is None


def test_different_pdfs_get_different_fingerprints():
    """Two distinct PDF text bodies produce different fingerprints."""
    bca = derive_fingerprint({"page1_text": "Bank Central Asia\nTAHAPAN BCA",
                               "page2_text": "", "producer": "", "creator": ""})
    permata = derive_fingerprint({"page1_text": "Permata\nRekening Tagihan\nCredit Card Billing",
                                   "page2_text": "", "producer": "", "creator": ""})
    assert bca.identity_hash != permata.identity_hash


def test_metadata_differentiates_fingerprint():
    """Same page text but different PDF metadata → different fingerprints."""
    base = {"page1_text": "BNI Sekuritas\nCLIENT STATEMENT", "page2_text": ""}
    fp_a = derive_fingerprint({**base, "producer": "Adobe PDF 11", "creator": "BNI App v1"})
    fp_b = derive_fingerprint({**base, "producer": "Adobe PDF 11", "creator": "BNI App v2"})
    assert fp_a.identity_hash != fp_b.identity_hash


# ── Partial signals helper ────────────────────────────────────────────────────


def test_partial_signals_for_unknown_pdf():
    """_collect_partial_signals returns empty list for an unrecognized PDF."""
    from parsers.router import _collect_partial_signals
    signals = _collect_partial_signals(
        "Completely unrecognized text with no bank keywords",
        "Completely unrecognized text with no bank keywords",
    )
    assert signals == []


def test_partial_signals_for_known_pdf():
    """_collect_partial_signals detects the matching parser name."""
    from parsers.router import _collect_partial_signals
    signals = _collect_partial_signals(
        "Permata\nRekening Tagihan\nCredit Card Billing",
        "Permata\nRekening Tagihan\nCredit Card Billing",
    )
    assert "permata_cc" in signals
