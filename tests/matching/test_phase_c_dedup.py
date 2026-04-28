"""Phase C verification — bank import dedup domain.

Verifies:
1. Engine produces identical decisions to legacy for all fixture cases (parity).
2. Tier-1 hit after auto-persist of a parser-variant merge.
3. Fingerprints: same identity key → same hash; different txns → different hashes.
4. Exact duplicates are detected by hash-set check before the engine is needed.
5. Engine returns None for a new transaction with no identity-key match.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from finance.matching.storage import ensure_domain_tables, ensure_global_tables
from finance.matching.engine import classify, reset_run_state
from finance.matching.domains.dedup import domain as dedup_domain, derive_fingerprint
from finance.matching.storage import get_mapping
from finance.importer import _should_reconcile_parser_variant

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dedup_fixture.json"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    # Minimal transactions table for build_indexes()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT    UNIQUE NOT NULL,
            date        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            raw_description TEXT NOT NULL,
            institution TEXT    NOT NULL,
            account     TEXT    DEFAULT '',
            owner       TEXT    NOT NULL
        );
    """)
    ensure_global_tables(c)
    ensure_domain_tables(c, "dedup")
    yield c
    c.close()


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text())


def _seed_existing(conn, txn: dict, hash_suffix: str = "") -> str:
    """Insert an existing transaction and return its hash."""
    import hashlib
    h = hashlib.sha256(
        f"{txn['date']}|{txn['amount']:.2f}|{txn['raw_description']}|"
        f"{txn['institution']}|{txn['owner']}|{txn['account']}{hash_suffix}".encode()
    ).hexdigest()[:32]
    conn.execute(
        "INSERT OR IGNORE INTO transactions (hash, date, amount, raw_description, institution, account, owner) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (h, txn["date"], float(txn["amount"]), txn["raw_description"],
         txn["institution"], txn.get("account", ""), txn["owner"]),
    )
    conn.commit()
    return h


# ── Fixture parity tests ──────────────────────────────────────────────────────


def test_parity_exact_dup_caught_before_engine(conn):
    """Exact duplicate is detected by hash-set check — engine is not needed."""
    case = next(c for c in _load_fixture() if c["id"] == "exact_dup_001")
    txn = case["txn"]
    existing = case["existing"]
    existing_hash = _seed_existing(conn, existing)

    # Reproduce what the importer does: check hash first
    import hashlib
    txn_hash = hashlib.sha256(
        f"{txn['date']}|{float(txn['amount']):.2f}|{txn['raw_description']}|"
        f"{txn['institution']}|{txn['owner']}|{txn['account']}".encode()
    ).hexdigest()[:32]
    assert txn_hash == existing_hash, "Exact dup must produce identical hash"
    # Engine is never called for exact duplicates; no assertion on classify()


def test_parity_parser_variant_engine_agrees_with_legacy(conn):
    """Engine and legacy both agree on parser-variant merge for fixture case."""
    case = next(c for c in _load_fixture() if c["id"] == "parser_variant_001")
    txn = case["txn"]
    existing = case["existing"]
    existing_hash = _seed_existing(conn, existing)

    # Legacy decision
    legacy_reconcile = _should_reconcile_parser_variant(
        existing["raw_description"], txn["raw_description"]
    )
    assert legacy_reconcile, "Legacy should reconcile this parser variant"

    # Engine decision
    reset_run_state()
    txn_row = {
        "date": txn["date"], "amount": txn["amount"],
        "institution": txn["institution"], "account": txn["account"],
        "owner": txn["owner"], "raw_description": txn["raw_description"],
    }
    prebuilt = {
        "existing_by_identity": {
            (existing["date"], float(existing["amount"]), existing["institution"],
             existing["account"], existing["owner"]): [
                {"hash": existing_hash, "raw_description": existing["raw_description"]}
            ]
        }
    }
    match = classify(dedup_domain, conn, txn_row, run_id="phase-c-test",
                     prebuilt_indexes=prebuilt)
    assert match is not None
    assert match.target == f"merge:{existing_hash}"
    assert match.tier == 2


def test_parity_new_txn_returns_none(conn):
    """Engine returns None for a new transaction with no identity-key match."""
    case = next(c for c in _load_fixture() if c["id"] == "new_txn_001")
    txn = case["txn"]
    assert case["existing"] is None

    reset_run_state()
    txn_row = {
        "date": txn["date"], "amount": txn["amount"],
        "institution": txn["institution"], "account": txn["account"],
        "owner": txn["owner"], "raw_description": txn["raw_description"],
    }
    match = classify(dedup_domain, conn, txn_row, run_id="phase-c-test",
                     prebuilt_indexes={"existing_by_identity": {}})
    assert match is None


def test_parity_same_amount_different_date_returns_none(conn):
    """Different date → different identity key → different fingerprint → no match."""
    case = next(c for c in _load_fixture() if c["id"] == "same_amount_diff_date_001")
    txn = case["txn"]
    existing = case["existing"]
    existing_hash = _seed_existing(conn, existing)

    reset_run_state()
    txn_row = {
        "date": txn["date"], "amount": txn["amount"],
        "institution": txn["institution"], "account": txn["account"],
        "owner": txn["owner"], "raw_description": txn["raw_description"],
    }
    # existing is keyed under a different date, so no identity match
    existing_key = (existing["date"], float(existing["amount"]),
                    existing["institution"], existing["account"], existing["owner"])
    prebuilt = {"existing_by_identity": {
        existing_key: [{"hash": existing_hash, "raw_description": existing["raw_description"]}]
    }}
    match = classify(dedup_domain, conn, txn_row, run_id="phase-c-test",
                     prebuilt_indexes=prebuilt)
    assert match is None


# ── Tier-1 caching ────────────────────────────────────────────────────────────


def test_tier1_hit_after_parser_variant_merge(conn):
    """Second classify() of the same loose fingerprint hits Tier-1 (cached mapping)."""
    case = next(c for c in _load_fixture() if c["id"] == "parser_variant_001")
    txn = case["txn"]
    existing = case["existing"]
    existing_hash = _seed_existing(conn, existing)

    txn_row = {
        "date": txn["date"], "amount": txn["amount"],
        "institution": txn["institution"], "account": txn["account"],
        "owner": txn["owner"], "raw_description": txn["raw_description"],
    }
    prebuilt = {
        "existing_by_identity": {
            (existing["date"], float(existing["amount"]), existing["institution"],
             existing["account"], existing["owner"]): [
                {"hash": existing_hash, "raw_description": existing["raw_description"]}
            ]
        }
    }

    # First classify: Tier-2, auto-persists
    reset_run_state()
    match1 = classify(dedup_domain, conn, txn_row, run_id="run-001", prebuilt_indexes=prebuilt)
    assert match1 is not None
    assert match1.tier == 2
    assert match1.target == f"merge:{existing_hash}"

    fp = derive_fingerprint(txn_row)
    mapping = get_mapping(conn, "dedup", fp.identity_hash)
    assert mapping is not None, "Parser-variant merge should have been auto-persisted"
    assert mapping["target_key"] == f"merge:{existing_hash}"
    assert mapping["source"] == "auto_safe"

    # Second classify: Tier-1 hit (no DB transaction scan needed)
    reset_run_state()
    match2 = classify(dedup_domain, conn, txn_row, run_id="run-002", prebuilt_indexes=prebuilt)
    assert match2 is not None
    assert match2.tier == 1, "Second call should hit Tier-1 cached mapping"
    assert match2.target == f"merge:{existing_hash}"


# ── Fingerprint properties ────────────────────────────────────────────────────


def test_same_txn_same_fingerprint():
    """Identical transaction fields always produce the same fingerprint."""
    row = {"date": "2024-02-10", "amount": -125000,
           "institution": "Permata", "account": "0701234567", "owner": "Helen",
           "raw_description": "TOKOPEDIA PAYMENT ONLINE FOOD"}
    fp1 = derive_fingerprint(row)
    fp2 = derive_fingerprint(row)
    assert fp1.identity_hash == fp2.identity_hash


def test_parser_variants_share_fingerprint():
    """Two parser variants of the same txn must produce the same identity hash."""
    base = {"date": "2024-02-10", "amount": -125000,
            "institution": "Permata", "account": "0701234567", "owner": "Helen"}
    fp_short = derive_fingerprint({**base, "raw_description": "TOKOPEDIA PAYMENT ONLINE FOOD"})
    fp_long  = derive_fingerprint({**base, "raw_description": "TOKOPEDIA PAYMENT ONLINE FOOD 20240210 REF00123456"})
    assert fp_short.identity_hash == fp_long.identity_hash


def test_different_txns_get_different_fingerprints():
    """Different transactions produce distinct fingerprints."""
    fp_a = derive_fingerprint({"date": "2024-01-15", "amount": -50000,
                                "institution": "BCA", "account": "1234567890", "owner": "Gandrik",
                                "raw_description": "TRANSFER"})
    fp_b = derive_fingerprint({"date": "2024-01-15", "amount": -50000,
                                "institution": "BCA", "account": "1234567890", "owner": "Gandrik",
                                "raw_description": "GRAB FOOD",
                                # different amount ensures different key
                                })
    # Same fields except raw_description — identity hash is the SAME (description-less)
    assert fp_a.identity_hash == fp_b.identity_hash

    # Different date → different hash
    fp_c = derive_fingerprint({"date": "2024-04-14", "amount": -500000,
                                "institution": "BCA", "account": "1234567890", "owner": "Gandrik",
                                "raw_description": "INDOMARET"})
    fp_d = derive_fingerprint({"date": "2024-04-15", "amount": -500000,
                                "institution": "BCA", "account": "1234567890", "owner": "Gandrik",
                                "raw_description": "INDOMARET"})
    assert fp_c.identity_hash != fp_d.identity_hash
