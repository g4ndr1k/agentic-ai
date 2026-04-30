from __future__ import annotations

import logging
import threading
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("agent.ai_worker")


class MailAiClassification(BaseModel):
    category: Literal[
        "transaction_alert",
        "bill_statement",
        "security_alert",
        "bank_clarification",
        "payment_due",
        "needs_reply",
        "newsletter",
        "promotion",
        "personal",
        "work",
        "spam_or_noise",
        "other",
    ]
    urgency_score: int = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=500)
    needs_reply: bool = False
    reason: str = Field(default="", max_length=500)


DEFAULT_AI_SETTINGS = {
    "enabled": False,
    "provider": "ollama",
    "base_url": "http://host.docker.internal:11434",
    "model": "gemma3:4b",
    "temperature": 0.1,
    "timeout_seconds": 45,
    "max_body_chars": 12000,
    "urgency_threshold": 8,
}


SYSTEM_PROMPT = """You classify emails into structured JSON only.
Classify based on content, sender, subject, and metadata.
Prefer conservative urgency. Never invent transaction amounts, dates, senders, or obligations.
Summarize in one concise sentence.
Classify obvious marketing/newsletters as low urgency.
Set needs_reply=true only when the email clearly requires a response from the user."""


def normalize_ai_settings(settings: dict | None) -> dict:
    cfg = dict(DEFAULT_AI_SETTINGS)
    cfg.update(settings or {})
    cfg["enabled"] = bool(cfg.get("enabled", False))
    cfg["provider"] = str(cfg.get("provider") or "ollama")
    cfg["base_url"] = str(cfg.get("base_url") or DEFAULT_AI_SETTINGS["base_url"]).rstrip("/")
    cfg["model"] = str(cfg.get("model") or DEFAULT_AI_SETTINGS["model"])
    cfg["temperature"] = float(cfg.get("temperature", 0.1))
    cfg["timeout_seconds"] = int(cfg.get("timeout_seconds", 45))
    cfg["max_body_chars"] = int(cfg.get("max_body_chars", 12000))
    cfg["urgency_threshold"] = int(cfg.get("urgency_threshold", 8))
    return cfg


def build_user_prompt(item: dict, max_body_chars: int) -> str:
    body = str(item.get("body_text") or "")[:max_body_chars]
    return "\n".join([
        f"Sender: {item.get('sender') or '(unknown)'}",
        f"Subject: {item.get('subject') or '(no subject)'}",
        f"Received: {item.get('received_at') or '(unknown)'}",
        f"Account: {item.get('account_id') or '(unknown)'}",
        "",
        "Body:",
        body or "(body unavailable)",
    ])


def _schema_format() -> dict:
    schema = MailAiClassification.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def classify_with_ollama(
        item: dict, settings: dict,
        client: httpx.Client | None = None) -> MailAiClassification:
    cfg = normalize_ai_settings(settings)
    if cfg["provider"] != "ollama":
        raise ValueError("Only provider='ollama' is supported")
    payload = {
        "model": cfg["model"],
        "stream": False,
        "format": _schema_format(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(item, cfg["max_body_chars"]),
            },
        ],
        "options": {"temperature": cfg["temperature"]},
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=cfg["timeout_seconds"])
    try:
        resp = http.post(f"{cfg['base_url']}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if isinstance(content, dict):
            parsed = content
        else:
            parsed = MailAiClassification.model_validate_json(content)
            return parsed
        return MailAiClassification.model_validate(parsed)
    finally:
        if owns_client:
            http.close()


class AiQueueWorker:
    def __init__(self, state, settings_getter, stop_event: threading.Event):
        self.state = state
        self.settings_getter = settings_getter
        self.stop_event = stop_event

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                cfg = normalize_ai_settings(
                    self.settings_getter().get("mail", {}).get("ai", {}))
                if not cfg["enabled"]:
                    self.stop_event.wait(5)
                    continue
                item = self.state.claim_next_ai_item()
                if item is None:
                    self.stop_event.wait(5)
                    continue
                try:
                    result = classify_with_ollama(item, cfg)
                    self.state.complete_ai_item(
                        item["id"], result.model_dump())
                except ValidationError as exc:
                    self.state.fail_ai_item(
                        item["id"], str(exc), retryable=False)
                    logger.warning("AI validation failed queue_id=%s: %s",
                                   item["id"], exc)
                except Exception as exc:
                    self.state.fail_ai_item(item["id"], str(exc), retryable=True)
                    logger.warning("AI enrichment failed queue_id=%s: %s",
                                   item["id"], exc)
            except Exception:
                logger.exception("AI worker loop error")
                self.stop_event.wait(10)


def start_ai_worker(state, settings_getter, stop_event: threading.Event):
    worker = AiQueueWorker(state, settings_getter, stop_event)
    thread = threading.Thread(
        target=worker.run_forever,
        name="mail-ai-worker",
        daemon=True,
    )
    thread.start()
    return thread
