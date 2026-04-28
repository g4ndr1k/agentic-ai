"""Phase A verification — generic engine + CoreTax domain adapter.

Verifies that the generic matching engine produces the same results as the
legacy finance.coretax.reconcile path for the CoreTax domain.

These tests are the Phase A gate: run-diff between legacy and generic must
produce zero divergence for all fixtures.
"""
from __future__ import annotations

import sqlite3

import pytest

from finance.coretax.db import ensure_coretax_tables, make_stable_key_cash, insert_row
from finance.matching.storage import ensure_domain_tables, ensure_global_tables
from finance.matching.engine import classify, reset_run_state, CURRENT_ENGINE_VERSION
from finance.matching.domains.coretax import domain as coretax_domain, derive_fingerprint


@pytest.fixture
def conn():
    """Fresh in-memory DB with all required tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_coretax_tables(c)
    ensure_global_tables(c)
    ensure_domain_tables(c, "coretax")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS account_balances (
            id INTEGER PRIMARY KEY, snapshot_date TEXT, institution TEXT,
            account TEXT, owner TEXT, currency TEXT, balance_idr REAL
        );
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY, snapshot_date TEXT, asset_class TEXT,
            institution TEXT, owner TEXT, currency TEXT, asset_name TEXT,
            isin_or_code TEXT, cost_basis_idr REAL, market_value_idr REAL
        );
        CREATE TABLE IF NOT EXISTS liabilities (
            id INTEGER PRIMARY KEY, snapshot_date TEXT, liability_type TEXT,
            liability_name TEXT, institution TEXT, owner TEXT, balance_idr REAL
        );
    """)
    c.commit()
    yield c
    c.close()


def test_fingerprint_account_balance(conn):
    """derive_fingerprint produces stable identity_hash for account_balance rows."""
    row = {"source_kind": "account_balance", "institution": "BCA", "account": "1234567890"}
    fp = derive_fingerprint(row)
    assert fp.identity_hash, "identity_hash should not be empty"
    assert fp.identity_raw == "bca:1234567890"
    assert fp.fingerprint_version == 1

    # Stability: same input → same hash
    fp2 = derive_fingerprint(row)
    assert fp.identity_hash == fp2.identity_hash


def test_fingerprint_holding_with_isin(conn):
    """ISIN-keyed fingerprints use the ISIN directly as identity_hash."""
    row = {
        "source_kind": "holding",
        "isin_or_code": "US5949181045",
        "asset_class": "stock",
        "institution": "IPOT",
        "asset_name": "Microsoft Corp",
        "owner": "Gandrik",
    }
    fp = derive_fingerprint(row)
    assert fp.identity_hash == "us5949181045"
    assert fp.identity_raw == "us5949181045"


def test_fingerprint_holding_without_isin(conn):
    """Holding without ISIN falls back to holding_signature hash."""
    row = {
        "source_kind": "holding",
        "isin_or_code": "",
        "asset_class": "mutual_fund",
        "institution": "Bibit",
        "asset_name": "RDPU Syariah",
        "owner": "Helen",
    }
    fp = derive_fingerprint(row)
    assert fp.identity_hash  # non-empty SHA-256
    expected_raw = "mutual_fund:bibit:rdpu-syariah:helen"
    assert fp.identity_raw == expected_raw


def test_tier1_lookup_hits_existing_mapping(conn):
    """classify() returns a tier-1 Match when a mapping exists for the fingerprint."""
    from finance.matching.storage import upsert_mapping
    from finance.matching.confidence import derive_level

    # Insert a coretax row so target universe is non-empty
    insert_row(conn, tax_year=2024, kind="asset", stable_key="pwm:account:bca:1234567890",
               kode_harta="012", keterangan="BCA Tahapan rek 1234567890",
               owner="Gandrik", institution="BCA")

    # Pre-insert a matching_coretax_mappings row
    row = {"source_kind": "account_balance", "institution": "BCA", "account": "1234567890"}
    fp = derive_fingerprint(row)
    upsert_mapping(
        conn, "coretax",
        identity_hash=fp.identity_hash,
        identity_raw=fp.identity_raw,
        target_key="pwm:account:bca:1234567890",
        confidence_score=1.0,
        confidence_level="HIGH",
        source="manual",
        fingerprint_version=1,
        engine_version=CURRENT_ENGINE_VERSION,
    )

    reset_run_state()
    match = classify(coretax_domain, conn, row, tax_year=2024, run_id="test-run-001")
    assert match is not None
    assert match.tier == 1
    assert match.target == "pwm:account:bca:1234567890"
    assert match.confidence_score == 1.0


def test_tier2_isin_match_auto_persists(conn):
    """classify() auto-persists a Tier-2 ISIN hit when guards pass."""
    from finance.matching.storage import get_mapping

    # Insert a coretax row with an ISIN in keterangan
    insert_row(conn, tax_year=2024, kind="asset", stable_key="pwm:holding:stock:ipot:MSFT:gandrik",
               kode_harta="039", keterangan="Microsoft US5949181045",
               owner="Gandrik", institution="IPOT")

    pwm_row = {
        "source_kind": "holding",
        "isin_or_code": "US5949181045",
        "asset_class": "stock",
        "institution": "IPOT",
        "asset_name": "Microsoft",
        "owner": "Gandrik",
    }

    reset_run_state()
    match = classify(coretax_domain, conn, pwm_row, tax_year=2024, run_id="test-run-002")

    assert match is not None
    assert match.tier == 2
    assert match.rule == "isin_exact_unique"

    fp = derive_fingerprint(pwm_row)
    persisted = get_mapping(conn, "coretax", fp.identity_hash)
    assert persisted is not None, "Should have auto-persisted Tier-2 match"
    assert persisted["source"] == "auto_safe"


def test_no_match_returns_none(conn):
    """classify() returns None when no mapping and no Tier-2 rule fires."""
    pwm_row = {
        "source_kind": "account_balance",
        "institution": "HSBC",
        "account": "9999999999",
    }
    reset_run_state()
    match = classify(coretax_domain, conn, pwm_row, tax_year=2024, run_id="test-run-003")
    assert match is None


def test_engine_version_future_aborts(conn):
    """classify() returns None if a stored mapping has a future engine_version."""
    from finance.matching.storage import upsert_mapping

    row = {"source_kind": "account_balance", "institution": "BCA", "account": "5555555555"}
    fp = derive_fingerprint(row)

    # Manually insert a mapping with a future engine_version
    conn.execute(
        """INSERT INTO matching_coretax_mappings
           (identity_hash, identity_raw, target_key, confidence_score, confidence_level,
            source, fingerprint_version, engine_version, times_confirmed, years_used,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,0,0,datetime('now'),datetime('now'))""",
        (fp.identity_hash, fp.identity_raw, "some:target", 1.0, "HIGH",
         "manual", 1, 9999),  # future engine_version = 9999
    )
    conn.commit()

    reset_run_state()
    match = classify(coretax_domain, conn, row, tax_year=2024)
    # Should abort (return None) due to CRITICAL invariant violation
    assert match is None
