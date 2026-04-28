"""Phase D verification — expense categorization domain.

Verifies:
1. Fingerprint stability: same description → same hash; volatile tokens stripped.
2. Owner/account differentiation: owner-specific rules hash differently.
3. Tier-2 rule wraps Categorizer correctly (layer 1/2 → trustworthy, layer 4 → fired=False).
4. Engine true mode: Tier-1 hit returns cached result without running legacy.
5. Shadow mode: Tier-1 mapping disagreement is logged to category_shadow_diff.
6. No shadow diff when Tier-1 agrees with legacy.
7. Auto-persist after layer 1 Tier-2 result.
"""
from __future__ import annotations

import sqlite3
import pytest

from finance.matching.storage import ensure_domain_tables, ensure_global_tables
from finance.matching.engine import classify, reset_run_state
from finance.matching.domains.categorization import (
    domain as cat_domain,
    derive_fingerprint,
    target_to_parts,
)
from finance.matching.storage import get_mapping, upsert_mapping
from finance.categorizer import Categorizer, CategorizationResult


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_global_tables(c)
    ensure_domain_tables(c, "categorization")
    yield c
    c.close()


@pytest.fixture
def cat():
    """Categorizer with a few synthetic aliases, no Ollama."""
    aliases = [
        {"alias": "STARBUCKS", "merchant": "Starbucks", "category": "Dining Out",
         "match_type": "contains", "owner_filter": "", "account_filter": ""},
        {"alias": "NETFLIX", "merchant": "Netflix", "category": "Subscriptions",
         "match_type": "contains", "owner_filter": "", "account_filter": ""},
        {"alias": "TRANSFER KE", "merchant": "Transfer", "category": "Transfer",
         "match_type": "contains", "owner_filter": "", "account_filter": ""},
        # Owner-specific alias
        {"alias": "TARIKAN ATM", "merchant": "Cash (Helen)", "category": "Household",
         "match_type": "contains", "owner_filter": "Helen", "account_filter": "5500346622"},
        {"alias": "TARIKAN ATM", "merchant": "Cash Withdrawal", "category": "Cash Withdrawal",
         "match_type": "contains", "owner_filter": "", "account_filter": ""},
    ]
    return Categorizer(aliases, categories=["Dining Out", "Subscriptions", "Transfer",
                                             "Household", "Cash Withdrawal", "Other"])


# ── Fingerprint tests ─────────────────────────────────────────────────────────


def test_fingerprint_stability():
    """Same description always hashes to the same value."""
    row = {"raw_description": "STARBUCKS SENAYAN CITY", "owner": "Gandrik", "account": "1234"}
    fp1 = derive_fingerprint(row)
    fp2 = derive_fingerprint(row)
    assert fp1.identity_hash == fp2.identity_hash


def test_fingerprint_volatile_tokens_stripped():
    """Volatile numeric tokens are stripped — same merchant, different dates hash the same."""
    row_a = {"raw_description": "NETFLIX COM 20240101", "owner": "Gandrik", "account": "1234"}
    row_b = {"raw_description": "NETFLIX COM 20240201", "owner": "Gandrik", "account": "1234"}
    fp_a = derive_fingerprint(row_a)
    fp_b = derive_fingerprint(row_b)
    # normalize_alias_key strips numbers, so both normalize to "NETFLIX COM"
    assert fp_a.identity_hash == fp_b.identity_hash


def test_fingerprint_owner_differentiates():
    """Same description but different owner → different hash (owner-specific aliases)."""
    row_a = {"raw_description": "TARIKAN ATM 100000", "owner": "Helen", "account": "5500346622"}
    row_b = {"raw_description": "TARIKAN ATM 100000", "owner": "Gandrik", "account": "9876543210"}
    fp_a = derive_fingerprint(row_a)
    fp_b = derive_fingerprint(row_b)
    assert fp_a.identity_hash != fp_b.identity_hash


def test_fingerprint_different_merchants_differ():
    """Starbucks and Netflix produce different fingerprints."""
    fp_a = derive_fingerprint({"raw_description": "STARBUCKS GRAND INDONESIA",
                                "owner": "Gandrik", "account": "1234"})
    fp_b = derive_fingerprint({"raw_description": "NETFLIX COM",
                                "owner": "Gandrik", "account": "1234"})
    assert fp_a.identity_hash != fp_b.identity_hash


# ── Tier-2 rule ───────────────────────────────────────────────────────────────


def test_tier2_layer1_result_is_trustworthy(conn, cat):
    """Layer 1 alias match → rule fires, score=1.0, single_shot_trustworthy=True."""
    reset_run_state()
    source = {"raw_description": "STARBUCKS SENAYAN CITY", "owner": "Gandrik", "account": "1234"}
    match = classify(cat_domain, conn, source, run_id="test", categorizer=cat)
    assert match is not None
    assert match.tier == 2
    merchant, category = target_to_parts(match.target)
    assert merchant == "Starbucks"
    assert category == "Dining Out"
    assert match.confidence_score == 1.0


def test_tier2_layer4_returns_none(conn):
    """Layer 4 (no alias, no Ollama) → classify() returns None (review queue)."""
    reset_run_state()
    empty_cat = Categorizer([], categories=["Other"])
    source = {"raw_description": "COMPLETELY UNKNOWN MERCHANT XYZ", "owner": "", "account": ""}
    match = classify(cat_domain, conn, source, run_id="test", categorizer=empty_cat)
    assert match is None


# ── Auto-persist and Tier-1 caching ──────────────────────────────────────────


def test_tier1_hit_after_layer1_auto_persist(conn, cat):
    """Layer 1 result is auto-persisted; second classify() hits Tier-1."""
    reset_run_state()
    source = {"raw_description": "NETFLIX COM", "owner": "Gandrik", "account": "1234"}

    # First call: Tier-2 run, auto-persists layer 1 result
    match1 = classify(cat_domain, conn, source, run_id="run-001", categorizer=cat)
    assert match1 is not None
    assert match1.tier == 2
    assert match1.target == "Netflix||Subscriptions"

    fp = derive_fingerprint(source)
    mapping = get_mapping(conn, "categorization", fp.identity_hash)
    assert mapping is not None, "Layer 1 result should be auto-persisted"
    assert mapping["target_key"] == "Netflix||Subscriptions"
    assert mapping["source"] == "auto_safe"

    # Second call: Tier-1 hit (no categorizer call needed)
    reset_run_state()
    match2 = classify(cat_domain, conn, source, run_id="run-002", categorizer=cat)
    assert match2 is not None
    assert match2.tier == 1
    assert match2.target == "Netflix||Subscriptions"


def test_target_to_parts_round_trip():
    """target_to_parts correctly splits "merchant||category" strings."""
    assert target_to_parts("Starbucks||Dining Out") == ("Starbucks", "Dining Out")
    assert target_to_parts("Cash (Helen)||Household") == ("Cash (Helen)", "Household")
    assert target_to_parts("||Transfer") == ("", "Transfer")


# ── Engine true mode via Categorizer ─────────────────────────────────────────


def test_categorize_engine_true_tier1_shortcut(conn, cat, monkeypatch):
    """Categorizer.categorize() with engine=true returns Tier-1 cached result."""
    monkeypatch.setenv("CATEGORIZATION_USE_ENGINE", "true")
    import finance.categorizer as cat_mod
    cat_mod.CATEGORIZATION_USE_ENGINE = "true"

    # Seed a Tier-1 mapping manually
    fp = derive_fingerprint({"raw_description": "STARBUCKS SENAYAN CITY",
                              "owner": "Gandrik", "account": "1234"})
    upsert_mapping(
        conn, "categorization",
        identity_hash=fp.identity_hash,
        identity_raw=fp.identity_raw,
        target_key="Starbucks||Dining Out",
        confidence_score=1.0,
        confidence_level="HIGH",
        source="manual",
        fingerprint_version=1,
        engine_version=1,
    )

    result = cat.categorize("STARBUCKS SENAYAN CITY", owner="Gandrik",
                             account="1234", conn=conn)
    assert result.merchant == "Starbucks"
    assert result.category == "Dining Out"
    assert result.layer == 1

    # Reset env
    cat_mod.CATEGORIZATION_USE_ENGINE = "false"


# ── Shadow mode ───────────────────────────────────────────────────────────────


def test_shadow_diff_logged_on_disagreement(conn, cat, monkeypatch):
    """Shadow mode logs a diff when Tier-1 mapping disagrees with legacy result."""
    import finance.categorizer as cat_mod
    cat_mod.CATEGORIZATION_USE_ENGINE = "shadow"

    # Seed a Tier-1 mapping that disagrees with what the alias returns
    fp = derive_fingerprint({"raw_description": "STARBUCKS SENAYAN CITY",
                              "owner": "Gandrik", "account": "1234"})
    upsert_mapping(
        conn, "categorization",
        identity_hash=fp.identity_hash,
        identity_raw=fp.identity_raw,
        target_key="OldMerchant||Shopping",  # deliberately wrong
        confidence_score=1.0,
        confidence_level="HIGH",
        source="manual",
        fingerprint_version=1,
        engine_version=1,
    )

    result = cat.categorize("STARBUCKS SENAYAN CITY", owner="Gandrik",
                             account="1234", conn=conn)
    # Legacy result is returned unchanged
    assert result.merchant == "Starbucks"
    assert result.category == "Dining Out"

    # Diff should have been logged
    row = conn.execute(
        "SELECT * FROM category_shadow_diff WHERE raw_description = ?",
        ("STARBUCKS SENAYAN CITY",),
    ).fetchone()
    assert row is not None, "Shadow diff should have been written"
    assert row["legacy_merchant"] == "Starbucks"
    assert row["legacy_category"] == "Dining Out"
    assert row["engine_merchant"] == "OldMerchant"
    assert row["engine_category"] == "Shopping"
    assert "diff" in row["diff_class"]

    cat_mod.CATEGORIZATION_USE_ENGINE = "false"


def test_shadow_no_diff_when_agreement(conn, cat, monkeypatch):
    """Shadow mode writes nothing when Tier-1 agrees with legacy."""
    import finance.categorizer as cat_mod
    cat_mod.CATEGORIZATION_USE_ENGINE = "shadow"

    fp = derive_fingerprint({"raw_description": "NETFLIX COM",
                              "owner": "Gandrik", "account": "1234"})
    upsert_mapping(
        conn, "categorization",
        identity_hash=fp.identity_hash,
        identity_raw=fp.identity_raw,
        target_key="Netflix||Subscriptions",  # matches legacy
        confidence_score=1.0,
        confidence_level="HIGH",
        source="manual",
        fingerprint_version=1,
        engine_version=1,
    )

    cat.categorize("NETFLIX COM", owner="Gandrik", account="1234", conn=conn)

    count = conn.execute(
        "SELECT COUNT(*) FROM category_shadow_diff"
    ).fetchone()[0]
    assert count == 0, "No diff should be logged when engine agrees with legacy"

    cat_mod.CATEGORIZATION_USE_ENGINE = "false"
