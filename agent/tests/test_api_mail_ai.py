from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.app import api_mail, config_manager
from agent.app.ai_worker import MailAiClassification
from agent.app.state import AgentState


def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text(
        """
[mail]
source = "gmail"

[mail.ai]
enabled = false
provider = "ollama"
base_url = "http://host.docker.internal:11434"
model = "gemma3:4b"
temperature = 0.1
timeout_seconds = 45
max_body_chars = 12000
urgency_threshold = 8
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    monkeypatch.setenv("FINANCE_API_KEY", "secret")
    monkeypatch.setattr(config_manager, "SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(config_manager, "BACKUP_DIR", str(tmp_path / "backups"))
    AgentState(str(db_path))
    app = FastAPI()
    app.include_router(api_mail.router, prefix="/api/mail")
    return TestClient(app), db_path, settings_path


def test_get_put_ai_settings_validates_and_preserves_toml(tmp_path, monkeypatch):
    client, _, settings_path = _client(tmp_path, monkeypatch)
    headers = {"X-Api-Key": "secret"}

    got = client.get("/api/mail/ai/settings", headers=headers)
    assert got.status_code == 200
    assert got.json()["model"] == "gemma3:4b"

    updated = client.put(
        "/api/mail/ai/settings",
        headers=headers,
        json={"enabled": True, "temperature": 0.2, "urgency_threshold": 9},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is True
    assert updated.json()["temperature"] == 0.2
    assert "[mail.ai]" in settings_path.read_text(encoding="utf-8")

    invalid = client.put(
        "/api/mail/ai/settings",
        headers=headers,
        json={"provider": "webhook"},
    )
    assert invalid.status_code == 400


def test_ai_test_returns_parsed_json_for_mocked_ollama(tmp_path, monkeypatch):
    client, _, _ = _client(tmp_path, monkeypatch)

    def fake_classify(item, settings):
        assert item["sender"] == "alerts@example.com"
        return MailAiClassification(
            category="payment_due",
            urgency_score=8,
            confidence=0.95,
            summary="A payment is due tomorrow.",
            needs_reply=False,
            reason="Payment due reminder",
        )

    monkeypatch.setattr(api_mail, "classify_with_ollama", fake_classify)
    response = client.post(
        "/api/mail/ai/test",
        headers={"X-Api-Key": "secret"},
        json={
            "sender": "alerts@example.com",
            "subject": "Payment due reminder",
            "body": "Your payment is due tomorrow.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["category"] == "payment_due"
    assert response.json()["urgency_score"] == 8


def test_manual_reprocess_creates_pending_queue_row(tmp_path, monkeypatch):
    client, db_path, _ = _client(tmp_path, monkeypatch)
    state = AgentState(str(db_path))
    first = state.enqueue_ai_work({
        "bridge_id": "imap-acct-INBOX-1",
        "message_key": "mkey1",
        "imap_account": "acct",
        "imap_folder": "INBOX",
        "imap_uid": 1,
        "imap_uidvalidity": 9,
        "sender_email": "billing@example.com",
        "subject": "Payment due",
        "body_text": "Your payment is due tomorrow.",
    })

    response = client.post(
        "/api/mail/messages/mkey%3Amkey1/reprocess",
        headers={"X-Api-Key": "secret"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["queue_id"] != first
