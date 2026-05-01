import json
from pathlib import Path

import pytest

from scripts import mail_rule_ai_golden_probe as probe


FIXTURE = Path("agent/tests/fixtures/rule_ai_golden_prompts.json")


def _case(**overrides):
    item = {
        "id": "bca_suspicious_transaction",
        "prompt": "If BCA emails me about suspicious transaction, notify me.",
        "mode": "alert_rule",
        "expected_domain": "bca.co.id",
        "expected_safety_status": "safe_local_alert_draft",
        "expected_action_type": "mark_pending_alert",
        "expected_target": "imessage",
        "expected_keywords_any": ["suspicious", "mencurigakan", "transaction", "transaksi"],
    }
    item.update(overrides)
    return item


def _valid_response(**overrides):
    payload = {
        "intent_summary": "Notify me for BCA suspicious transaction emails",
        "confidence": 0.89,
        "status": "draft",
        "saveable": True,
        "safety_status": "safe_local_alert_draft",
        "requires_user_confirmation": True,
        "rule": {
            "name": "BCA suspicious transaction alert",
            "account_id": None,
            "match_type": "ALL",
            "conditions": [
                {"field": "from_domain", "operator": "contains", "value": "bca.co.id"},
                {"field": "subject", "operator": "contains", "value": "suspicious transaction"},
            ],
            "actions": [
                {
                    "action_type": "mark_pending_alert",
                    "target": "imessage",
                    "value_json": {"template": "BCA suspicious transaction email detected."},
                    "stop_processing": False,
                }
            ],
        },
        "explanation": ["This rule matches BCA suspicious transaction emails."],
        "warnings": [
            "This is a draft only.",
            "This does not mutate Gmail.",
        ],
    }
    payload.update(overrides)
    return payload


def test_fixture_loads_correctly():
    cases = probe.load_fixture(FIXTURE)
    assert len(cases) == 10
    assert {case["id"] for case in cases} == {
        "bca_suspicious_transaction",
        "cimb_credit_card_confirmation",
        "maybank_security_alert",
        "permata_kartu_kredit_confirmation",
        "klikbca_login_security",
        "mandiri_otp",
        "bni_failed_transaction",
        "bri_payment_due",
        "ocbc_suspicious_login",
        "jenius_account_security",
    }
    assert all(case["mode"] == "alert_rule" for case in cases)


def test_valid_response_passes():
    result = probe.validate_probe_response(_case(), _valid_response(), 200)
    assert result.passed is True
    assert result.errors == []


def test_unsupported_response_fails():
    result = probe.validate_probe_response(
        _case(),
        {
            "status": "unsupported",
            "saveable": False,
            "safety_status": "llm_draft_failed",
            "rule": None,
            "warnings": ["No rule was saved."],
        },
        200,
    )
    assert result.passed is False
    assert "status_not_draft:unsupported" in result.errors
    assert "saveable_not_true" in result.errors
    assert "missing_rule" in result.errors


def test_wrong_domain_fails():
    payload = _valid_response(rule={
        **_valid_response()["rule"],
        "conditions": [
            {"field": "from_domain", "operator": "contains", "value": "example.com"},
            {"field": "subject", "operator": "contains", "value": "suspicious transaction"},
        ],
    })
    result = probe.validate_probe_response(_case(), payload, 200)
    assert result.passed is False
    assert "missing_expected_domain:bca.co.id" in result.errors


def test_missing_content_condition_fails():
    payload = _valid_response(rule={
        **_valid_response()["rule"],
        "conditions": [
            {"field": "from_domain", "operator": "contains", "value": "bca.co.id"},
        ],
    })
    result = probe.validate_probe_response(_case(), payload, 200)
    assert result.passed is False
    assert "missing_content_condition" in result.errors


def test_wrong_action_fails():
    payload = _valid_response(rule={
        **_valid_response()["rule"],
        "actions": [
            {
                "action_type": "mark_pending_alert",
                "target": "dashboard",
                "value_json": {"template": "x"},
                "stop_processing": False,
            }
        ],
    })
    result = probe.validate_probe_response(_case(), payload, 200)
    assert result.passed is False
    assert "target_mismatch:dashboard" in result.errors


def test_blocked_action_fails():
    payload = _valid_response(rule={
        **_valid_response()["rule"],
        "actions": [
            {
                "action_type": "send_imessage",
                "target": "imessage",
                "value_json": {"template": "x"},
                "stop_processing": False,
            }
        ],
    })
    result = probe.validate_probe_response(_case(), payload, 200)
    assert result.passed is False
    assert "blocked_action:send_imessage" in result.errors


def test_non_200_response_fails():
    result = probe.validate_probe_response(_case(), _valid_response(), 503)
    assert result.passed is False
    assert "http_status_not_200:503" in result.errors


def test_json_report_mode_returns_structured_results():
    results = [
        probe.validate_probe_response(_case(), _valid_response(), 200),
        probe.validate_probe_response(_case(id="bad"), _valid_response(status="unsupported"), 200),
    ]
    payload = probe.results_to_json(results)
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert payload["results"][0]["id"] == "bca_suspicious_transaction"


def test_run_probe_calls_only_draft_endpoint_and_never_save_rule_endpoint():
    called_urls = []

    def fake_post(url, payload, api_key, timeout):
        called_urls.append(url)
        assert url.endswith(probe.DRAFT_PATH)
        assert not url.endswith(probe.SAVE_RULE_PATH)
        assert payload == {
            "request_text": "If BCA emails me about suspicious transaction, notify me.",
            "mode": "alert_rule",
        }
        assert api_key == "secret"
        assert timeout == 12
        return 200, _valid_response()

    results = probe.run_probe(
        [_case()],
        api_base="http://127.0.0.1:8090",
        api_key="secret",
        timeout=12,
        post_json=fake_post,
    )

    assert [result.passed for result in results] == [True]
    assert called_urls == ["http://127.0.0.1:8090/api/mail/rules/ai/draft"]


def test_main_json_uses_mocked_probe_without_network(tmp_path, monkeypatch, capsys):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([_case()]))
    monkeypatch.setenv("FINANCE_API_KEY", "secret")

    def fake_run_probe(cases, api_base, api_key, timeout, post_json=None, fail_fast=False):
        assert cases[0]["id"] == "bca_suspicious_transaction"
        assert api_base == "http://api.test"
        assert api_key == "secret"
        assert timeout == 5
        assert fail_fast is True
        return [probe.validate_probe_response(_case(), _valid_response(), 200)]

    monkeypatch.setattr(probe, "run_probe", fake_run_probe)
    code = probe.main([
        "--api-base",
        "http://api.test",
        "--fixture",
        str(fixture),
        "--timeout",
        "5",
        "--fail-fast",
        "--json",
    ])

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["passed"] == 1
    assert output["failed"] == 0


def test_main_requires_api_key(monkeypatch, capsys):
    monkeypatch.delenv("FINANCE_API_KEY", raising=False)
    assert probe.main(["--fixture", str(FIXTURE)]) == 2
    assert "FINANCE_API_KEY is required" in capsys.readouterr().err


def test_filter_cases_rejects_unknown_prompt_id():
    with pytest.raises(ValueError, match="Prompt id not found"):
        probe.filter_cases([_case()], "missing")
