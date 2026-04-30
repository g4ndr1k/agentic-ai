import sqlite3
import sys
from pathlib import Path

from agent.app.ai_worker import MailAiClassification
from agent.app.state import AgentState

agent_root = Path(__file__).resolve().parents[1]
if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))
from app.orchestrator import Orchestrator


def _message(**overrides):
    msg = {
        "bridge_id": "imap-acct-INBOX-1",
        "message_id": "<m1@example.test>",
        "message_key": "mkey1",
        "fallback_message_key": "fkey1",
        "imap_account": "acct",
        "imap_folder": "INBOX",
        "imap_uid": 1,
        "imap_uidvalidity": 9,
        "sender_email": "billing@example.com",
        "subject": "Payment due",
        "date_received": "2026-04-29T01:00:00+00:00",
        "body_text": "Your payment is due tomorrow.",
    }
    msg.update(overrides)
    return msg


def _classification():
    return MailAiClassification(
        category="payment_due",
        urgency_score=7,
        confidence=0.9,
        summary="A payment is due tomorrow.",
        needs_reply=False,
        reason="Due reminder",
    ).model_dump()


def test_valid_ai_json_is_persisted_as_completed(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    queue_id = state.enqueue_ai_work(_message())
    item = state.claim_next_ai_item()

    assert item["id"] == queue_id
    state.complete_ai_item(queue_id, _classification())

    with state._connect() as conn:
        row = conn.execute(
            "SELECT status FROM mail_ai_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
        saved = conn.execute(
            "SELECT category, urgency_score, confidence, raw_json "
            "FROM mail_ai_classifications WHERE queue_id = ?",
            (queue_id,),
        ).fetchone()
    assert row[0] == "completed"
    assert saved[0] == "payment_due"
    assert saved[1] == 7
    assert saved[2] == 0.9
    assert "payment_due" in saved[3]


def test_ai_completion_does_not_invoke_imap_mutation_helpers(tmp_path, monkeypatch):
    from agent.app import imap_source

    state = AgentState(str(tmp_path / "agent.db"))
    queue_id = state.enqueue_ai_work(_message())
    calls = []
    monkeypatch.setattr(
        imap_source,
        "move_message_by_uid",
        lambda *args, **kwargs: calls.append(("move", args, kwargs)),
    )
    monkeypatch.setattr(
        imap_source,
        "store_flags_by_uid",
        lambda *args, **kwargs: calls.append(("store", args, kwargs)),
    )

    state.complete_ai_item(queue_id, _classification())

    assert calls == []


def test_invalid_schema_violation_becomes_failed_with_last_error(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    queue_id = state.enqueue_ai_work(_message())
    state.claim_next_ai_item()
    try:
        MailAiClassification.model_validate({
            "category": "payment_due",
            "urgency_score": 99,
            "confidence": 0.9,
            "summary": "Bad urgency",
        })
    except Exception as exc:
        state.fail_ai_item(queue_id, str(exc), retryable=False)

    with state._connect() as conn:
        row = conn.execute(
            "SELECT status, attempts, last_error FROM mail_ai_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
    assert row[0] == "failed"
    assert row[1] == 1
    assert "urgency_score" in row[2]


def test_attempts_increment_on_failure(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    queue_id = state.enqueue_ai_work(_message())
    state.fail_ai_item(queue_id, "ollama down", retryable=True)
    state.fail_ai_item(queue_id, "ollama still down", retryable=False)

    with state._connect() as conn:
        row = conn.execute(
            "SELECT status, attempts, last_error FROM mail_ai_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
    assert row == ("failed", 2, "ollama still down")


def test_manual_reprocess_bypasses_unique_constraint(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    first = state.enqueue_ai_work(_message())
    source = state.find_ai_reprocess_source("mkey1")
    second = state.enqueue_manual_ai_reprocess(source)

    assert second != first
    with state._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM mail_ai_queue WHERE message_id = ?",
            ("mkey:mkey1",),
        ).fetchone()[0]
    assert count == 2


def test_claim_commits_before_external_ollama_call(tmp_path):
    db_path = tmp_path / "agent.db"
    state = AgentState(str(db_path))
    queue_id = state.enqueue_ai_work(_message())
    item = state.claim_next_ai_item()
    assert item["id"] == queue_id

    probe = sqlite3.connect(str(db_path), timeout=1.0)
    try:
        probe.execute("INSERT INTO agent_flags (key, value) VALUES (?, ?)",
                      ("tx_probe", "ok"))
        probe.commit()
    finally:
        probe.close()


def test_orchestrator_enqueues_only_when_ai_enabled_and_not_skipped(tmp_path):
    state = AgentState(str(tmp_path / "agent.db"))
    orch = object.__new__(Orchestrator)
    orch.state = state
    orch.settings = {"mail": {"ai": {"enabled": False, "max_body_chars": 12000}}}

    class RuleEval:
        would_skip_ai = False

    orch._enqueue_ai_if_enabled(_message(), RuleEval())
    with state._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mail_ai_queue").fetchone()[0] == 0

    orch.settings["mail"]["ai"]["enabled"] = True
    orch._enqueue_ai_if_enabled(_message(), RuleEval())
    with state._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mail_ai_queue").fetchone()[0] == 1

    class SkipEval:
        would_skip_ai = True

    orch._enqueue_ai_if_enabled(_message(imap_uid=2), SkipEval())
    with state._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mail_ai_queue").fetchone()[0] == 1
