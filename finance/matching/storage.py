"""Generic storage — per-domain mapping/component/rejected-suggestion CRUD.

Engine owns the schema shape; domains just provide a table prefix.
Domain-specific columns live in a separate matching_<domain>_metadata table;
engine tables stay strictly typed.

Per-domain tables (engine schema, closed):
  matching_<domain>_mappings
  matching_<domain>_components
  matching_<domain>_rejected_suggestions

Category shadow diff (Phase 0, special):
  category_shadow_diff

Invariant log and drift metrics (engine-wide, no domain prefix):
  matching_invariant_log
  matching_invariant_diagnostic
  matching_drift_metrics
  matching_trace_archive
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _validate_identifier(value: str, *, label: str = "identifier") -> str:
    """Return a SQL identifier after validating it is safe to interpolate.

    SQLite parameters cannot bind table or column names, so every dynamic
    identifier must pass through this narrow allow-list before formatting SQL.
    """
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _prefix(domain: str) -> str:
    return f"matching_{_validate_identifier(domain, label='domain')}"


# ── Schema templates ─────────────────────────────────────────────────────────


def _mappings_ddl(prefix: str) -> str:
    prefix = _validate_identifier(prefix, label="table prefix")
    return f"""
CREATE TABLE IF NOT EXISTS {prefix}_mappings (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_hash           TEXT NOT NULL,
    identity_raw            TEXT,
    target_key              TEXT NOT NULL,
    confidence_score        REAL NOT NULL DEFAULT 1.0,
    confidence_level        TEXT NOT NULL DEFAULT 'HIGH',
    source                  TEXT NOT NULL DEFAULT 'manual',
    fingerprint_version     INTEGER NOT NULL DEFAULT 1,
    engine_version          INTEGER NOT NULL DEFAULT 1,
    times_confirmed         INTEGER NOT NULL DEFAULT 0,
    years_used              INTEGER NOT NULL DEFAULT 0,
    last_used_at            TEXT,
    created_from_run_key    TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE(identity_hash)
);
CREATE INDEX IF NOT EXISTS idx_{prefix}_mappings_target
    ON {prefix}_mappings(target_key);
"""


def _components_ddl(prefix: str) -> str:
    prefix = _validate_identifier(prefix, label="table prefix")
    return f"""
CREATE TABLE IF NOT EXISTS {prefix}_components (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                    TEXT NOT NULL,
    target_key                TEXT NOT NULL,
    identity_hash             TEXT NOT NULL,
    identity_raw              TEXT,
    source_kind               TEXT NOT NULL,
    component_label           TEXT NOT NULL,
    confidence_level          TEXT NOT NULL,
    extra_json                TEXT,
    is_current                INTEGER NOT NULL DEFAULT 1,
    created_at                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{prefix}_comp_target
    ON {prefix}_components(target_key, is_current);
CREATE INDEX IF NOT EXISTS idx_{prefix}_comp_run
    ON {prefix}_components(run_id);
"""


def _rejected_ddl(prefix: str) -> str:
    prefix = _validate_identifier(prefix, label="table prefix")
    return f"""
CREATE TABLE IF NOT EXISTS {prefix}_rejected_suggestions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_hash               TEXT NOT NULL,
    rejected_target_key         TEXT NOT NULL,
    rule                        TEXT NOT NULL,
    rejected_at                 TEXT NOT NULL,
    note                        TEXT,
    UNIQUE(identity_hash, rejected_target_key)
);
"""


ENGINE_GLOBAL_DDL = """
CREATE TABLE IF NOT EXISTS matching_invariant_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    severity    TEXT NOT NULL,
    domain      TEXT NOT NULL,
    rule        TEXT,
    run_id      TEXT,
    message     TEXT NOT NULL,
    extra_json  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matching_invariant_diagnostic (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matching_drift_metrics (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain                      TEXT NOT NULL,
    metric_date                 TEXT NOT NULL,
    tier1_to_tier2_ratio        REAL,
    unmatched_rate              REAL,
    auto_persist_rate           REAL,
    fingerprint_uniqueness_ratio REAL,
    UNIQUE(domain, metric_date)
);

CREATE TABLE IF NOT EXISTS matching_trace_archive (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    source_id   TEXT,
    trace_json  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_archive_run
    ON matching_trace_archive(domain, run_id);

CREATE TABLE IF NOT EXISTS category_shadow_diff (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id      INTEGER,
    raw_description     TEXT,
    legacy_merchant     TEXT,
    legacy_category     TEXT,
    engine_merchant     TEXT,
    engine_category     TEXT,
    diff_class          TEXT,
    release_tag         TEXT,
    run_id              TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_diff_run
    ON category_shadow_diff(run_id);
"""


def ensure_domain_tables(conn, domain_name: str) -> None:
    """Create all tables for a domain. Idempotent."""
    prefix = _prefix(domain_name)
    conn.executescript(
        _mappings_ddl(prefix)
        + _components_ddl(prefix)
        + _rejected_ddl(prefix)
    )
    conn.executescript(ENGINE_GLOBAL_DDL)
    conn.commit()


def ensure_global_tables(conn) -> None:
    """Create engine-global tables only (no domain prefix). Idempotent."""
    conn.executescript(ENGINE_GLOBAL_DDL)
    conn.commit()


# ── Mapping CRUD ─────────────────────────────────────────────────────────────


def get_mapping(conn, domain: str, identity_hash: str) -> dict | None:
    prefix = _prefix(domain)
    row = conn.execute(
        f"SELECT * FROM {prefix}_mappings WHERE identity_hash = ?",
        (identity_hash,),
    ).fetchone()
    return dict(row) if row else None


def list_mappings(conn, domain: str, limit: int = 100, cursor: str | None = None) -> dict:
    prefix = _prefix(domain)
    limit = min(max(limit, 1), 1000)
    offset = 0
    if cursor:
        try:
            offset = int(json.loads(base64.b64decode(cursor)).get("offset", 0))
        except Exception:
            pass
    rows = conn.execute(
        f"SELECT * FROM {prefix}_mappings ORDER BY id LIMIT ? OFFSET ?",
        (limit + 1, offset),
    ).fetchall()
    has_next = len(rows) > limit
    rows = rows[:limit]
    total = conn.execute(f"SELECT COUNT(*) AS c FROM {prefix}_mappings").fetchone()["c"]
    next_cursor = None
    if has_next:
        next_cursor = base64.b64encode(json.dumps({"offset": offset + limit}).encode()).decode()
    return {"items": [dict(r) for r in rows], "next_cursor": next_cursor, "total": total}


def upsert_mapping(conn, domain: str, *, identity_hash: str, identity_raw: str,
                   target_key: str, confidence_score: float, confidence_level: str,
                   source: str, fingerprint_version: int, engine_version: int,
                   created_from_run_key: str | None = None,
                   raise_on_conflict: bool = False) -> int:
    """Insert or update a mapping. Returns mapping id."""
    from finance.matching.storage import _utcnow
    now = _utcnow()
    prefix = _prefix(domain)
    existing = conn.execute(
        f"SELECT id, target_key FROM {prefix}_mappings WHERE identity_hash = ?",
        (identity_hash,),
    ).fetchone()
    if existing:
        if raise_on_conflict and existing["target_key"] != target_key:
            from finance.matching.engine import MappingConflictError
            raise MappingConflictError(
                domain=domain, identity_hash=identity_hash,
                requested_target=target_key, existing_target=existing["target_key"],
                existing_id=existing["id"],
            )
        conn.execute(
            f"""UPDATE {prefix}_mappings SET
                target_key=?, confidence_score=?, confidence_level=?,
                source=?, fingerprint_version=?, engine_version=?,
                identity_raw=?, updated_at=?
                WHERE id=?""",
            (target_key, confidence_score, confidence_level,
             source, fingerprint_version, engine_version,
             identity_raw, now, existing["id"]),
        )
        conn.commit()
        return existing["id"]
    cur = conn.execute(
        f"""INSERT INTO {prefix}_mappings
            (identity_hash, identity_raw, target_key, confidence_score, confidence_level,
             source, fingerprint_version, engine_version, times_confirmed, years_used,
             created_from_run_key, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?)""",
        (identity_hash, identity_raw, target_key, confidence_score, confidence_level,
         source, fingerprint_version, engine_version,
         created_from_run_key, now, now),
    )
    conn.commit()
    return cur.lastrowid


def delete_mapping(conn, domain: str, mapping_id: int) -> bool:
    prefix = _prefix(domain)
    cur = conn.execute(f"DELETE FROM {prefix}_mappings WHERE id = ?", (mapping_id,))
    conn.commit()
    return cur.rowcount > 0


def update_mapping_fields(conn, domain: str, mapping_id: int, **fields) -> bool:
    if not fields:
        return False
    prefix = _prefix(domain)
    for name in fields:
        _validate_identifier(name, label="column")
    fields["updated_at"] = _utcnow()
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    fields["_id"] = mapping_id
    cur = conn.execute(f"UPDATE {prefix}_mappings SET {sets} WHERE id = :_id", fields)
    conn.commit()
    return cur.rowcount > 0


# ── Rejected suggestions ─────────────────────────────────────────────────────


def insert_rejected(conn, domain: str, identity_hash: str,
                    rejected_target_key: str, rule: str,
                    note: str | None = None) -> int:
    prefix = _prefix(domain)
    now = _utcnow()
    cur = conn.execute(
        f"""INSERT OR IGNORE INTO {prefix}_rejected_suggestions
            (identity_hash, rejected_target_key, rule, rejected_at, note)
            VALUES (?,?,?,?,?)""",
        (identity_hash, rejected_target_key, rule, now, note),
    )
    conn.commit()
    return cur.lastrowid


def get_rejected_pairs(conn, domain: str) -> set[tuple[str, str]]:
    prefix = _prefix(domain)
    rows = conn.execute(
        f"SELECT identity_hash, rejected_target_key FROM {prefix}_rejected_suggestions"
    ).fetchall()
    return {(r["identity_hash"], r["rejected_target_key"]) for r in rows}


def delete_rejected(conn, domain: str, suggestion_id: int) -> bool:
    prefix = _prefix(domain)
    cur = conn.execute(
        f"DELETE FROM {prefix}_rejected_suggestions WHERE id = ?", (suggestion_id,))
    conn.commit()
    return cur.rowcount > 0


# ── Invariant log ────────────────────────────────────────────────────────────


def log_invariant(conn, severity: str, domain: str, message: str,
                  rule: str | None = None, run_id: str | None = None,
                  extra: dict | None = None) -> int:
    now = _utcnow()
    cur = conn.execute(
        """INSERT INTO matching_invariant_log
           (severity, domain, rule, run_id, message, extra_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (severity, domain, rule, run_id, message,
         json.dumps(extra) if extra else None, now),
    )
    conn.commit()
    return cur.lastrowid


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
