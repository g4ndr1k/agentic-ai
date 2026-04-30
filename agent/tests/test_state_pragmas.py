import sqlite3

from agent.app.state import AgentState


def test_state_connections_apply_required_pragmas(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    with state._connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_phase4b_schema_is_idempotent(tmp_path):
    db_path = tmp_path / "agent.db"
    AgentState(str(db_path))
    AgentState(str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        queue_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(mail_ai_queue)").fetchall()
        }
        assert {
            "bridge_id",
            "sender",
            "subject",
            "received_at",
            "body_text",
            "manual_nonce",
        }.issubset(queue_cols)
    finally:
        conn.close()
