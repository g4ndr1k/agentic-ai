"""Safety checks for generic matching storage helpers."""
from __future__ import annotations

import sqlite3

import pytest

from finance.matching.storage import (
    ensure_domain_tables,
    get_mapping,
    upsert_mapping,
    update_mapping_fields,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_domain_name_must_be_safe_identifier(conn):
    """Dynamic table-name helpers reject unsafe domain strings."""
    with pytest.raises(ValueError):
        ensure_domain_tables(conn, "parser; DROP TABLE transactions; --")

    with pytest.raises(ValueError):
        get_mapping(conn, "parser UNION SELECT", "abc")


def test_update_field_names_must_be_safe_identifiers(conn):
    """Dynamic column-name updates reject unsafe field strings."""
    ensure_domain_tables(conn, "parser")

    with pytest.raises(ValueError):
        update_mapping_fields(conn, "parser", 1, **{"source = 'manual' --": "x"})


def test_update_mapping_fields_reports_missing_rows(conn):
    """Callers can distinguish successful updates from missing mapping ids."""
    ensure_domain_tables(conn, "parser")

    assert update_mapping_fields(conn, "parser", 999, source="manual") is False

    mapping_id = upsert_mapping(
        conn,
        "parser",
        identity_hash="abc",
        identity_raw="abc",
        target_key="bca_savings",
        confidence_score=1.0,
        confidence_level="HIGH",
        source="manual",
        fingerprint_version=1,
        engine_version=1,
    )
    assert update_mapping_fields(conn, "parser", mapping_id, source="auto_safe") is True
