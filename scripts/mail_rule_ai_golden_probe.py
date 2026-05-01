#!/usr/bin/env python3
"""Manual smoke probe for local Rule AI golden prompts.

This operator-run script calls only POST /api/mail/rules/ai/draft. It never
calls the Save Rule endpoint and never mutates mailbox or rule-table state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_API_BASE = "http://127.0.0.1:8090"
DEFAULT_FIXTURE = "agent/tests/fixtures/rule_ai_golden_prompts.json"
DRAFT_PATH = "/api/mail/rules/ai/draft"
SAVE_RULE_PATH = "/api/mail/rules"

BLOCKED_ACTIONS = {
    "delete",
    "move_to_folder",
    "add_label",
    "mark_read",
    "mark_unread",
    "move_to_spam",
    "send_imessage",
    "forward",
    "auto_reply",
    "unsubscribe",
    "external_webhook",
    "route_to_pdf_pipeline",
    "skip_ai_inference",
    "stop_processing",
}


@dataclass(frozen=True)
class ProbeResult:
    id: str
    prompt: str
    passed: bool
    expected_domain: str | None
    status_code: int | None = None
    safety_status: str | None = None
    saveable: bool | None = None
    errors: list[str] | None = None
    response_status: str | None = None


def load_fixture(path: str | Path) -> list[dict[str, Any]]:
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text())
    if not isinstance(data, list):
        raise ValueError("Golden prompt fixture must be a JSON array")
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Fixture entry {index} must be an object")
        for key in (
            "id",
            "prompt",
            "expected_domain",
            "expected_safety_status",
            "expected_action_type",
            "expected_target",
            "expected_keywords_any",
        ):
            if key not in item:
                raise ValueError(f"Fixture entry {index} missing {key}")
        if item["id"] in seen_ids:
            raise ValueError(f"Duplicate prompt id: {item['id']}")
        seen_ids.add(str(item["id"]))
        if not isinstance(item["expected_keywords_any"], list) or not item["expected_keywords_any"]:
            raise ValueError(f"Fixture entry {item['id']} requires expected_keywords_any")
    return data


def validate_probe_response(
    prompt_case: dict[str, Any],
    payload: dict[str, Any] | None,
    status_code: int | None = 200,
) -> ProbeResult:
    errors: list[str] = []
    case_id = str(prompt_case.get("id", "unknown"))
    expected_domain = str(prompt_case.get("expected_domain") or "")
    if status_code != 200:
        errors.append(f"http_status_not_200:{status_code}")
    if not isinstance(payload, dict):
        errors.append("response_not_object")
        return ProbeResult(
            id=case_id,
            prompt=str(prompt_case.get("prompt", "")),
            passed=False,
            expected_domain=expected_domain,
            status_code=status_code,
            errors=errors,
        )

    if payload.get("status") != "draft":
        errors.append(f"status_not_draft:{payload.get('status')}")
    if payload.get("saveable") is not True:
        errors.append("saveable_not_true")
    expected_safety = prompt_case.get("expected_safety_status")
    if payload.get("safety_status") != expected_safety:
        errors.append(f"safety_status_mismatch:{payload.get('safety_status')}")

    rule = payload.get("rule")
    if not isinstance(rule, dict):
        errors.append("missing_rule")
        return _result_from_payload(prompt_case, payload, status_code, errors)
    if rule.get("match_type") != "ALL":
        errors.append(f"match_type_not_all:{rule.get('match_type')}")

    conditions = rule.get("conditions")
    if not isinstance(conditions, list):
        errors.append("conditions_not_array")
        conditions = []
    sender_ok = any(
        isinstance(condition, dict)
        and condition.get("field") == "from_domain"
        and condition.get("operator") == "contains"
        and str(condition.get("value", "")).lower() == expected_domain.lower()
        for condition in conditions
    )
    if not sender_ok:
        errors.append(f"missing_expected_domain:{expected_domain}")

    content_conditions = [
        condition
        for condition in conditions
        if isinstance(condition, dict)
        and condition.get("field") in {"subject", "body"}
        and condition.get("operator") == "contains"
        and str(condition.get("value", "")).strip()
    ]
    if not content_conditions:
        errors.append("missing_content_condition")
    expected_keywords = [
        str(keyword).lower()
        for keyword in prompt_case.get("expected_keywords_any", [])
    ]
    content_values = [
        str(condition.get("value", "")).lower()
        for condition in content_conditions
    ]
    if expected_keywords and not any(
        keyword in value
        for keyword in expected_keywords
        for value in content_values
    ):
        errors.append("missing_expected_keyword")

    actions = rule.get("actions")
    if not isinstance(actions, list):
        errors.append("actions_not_array")
        actions = []
    if len(actions) != 1:
        errors.append(f"actions_count_not_one:{len(actions)}")
    action = actions[0] if actions and isinstance(actions[0], dict) else {}
    action_type = action.get("action_type")
    if action_type in BLOCKED_ACTIONS:
        errors.append(f"blocked_action:{action_type}")
    if action_type != prompt_case.get("expected_action_type"):
        errors.append(f"action_type_mismatch:{action_type}")
    if action.get("target") != prompt_case.get("expected_target"):
        errors.append(f"target_mismatch:{action.get('target')}")
    if action.get("stop_processing") is not False:
        errors.append("stop_processing_not_false")
    for candidate in actions:
        if isinstance(candidate, dict) and candidate.get("action_type") in BLOCKED_ACTIONS:
            errors.append(f"blocked_action_present:{candidate.get('action_type')}")

    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        lowered = " ".join(str(warning).lower() for warning in warnings)
        if not any(token in lowered for token in ("draft", "does not mutate", "no rule was saved")):
            errors.append("warnings_missing_non_mutating_language")

    return _result_from_payload(prompt_case, payload, status_code, errors)


def _result_from_payload(
    prompt_case: dict[str, Any],
    payload: dict[str, Any],
    status_code: int | None,
    errors: list[str],
) -> ProbeResult:
    return ProbeResult(
        id=str(prompt_case.get("id", "unknown")),
        prompt=str(prompt_case.get("prompt", "")),
        passed=not errors,
        expected_domain=str(prompt_case.get("expected_domain") or ""),
        status_code=status_code,
        safety_status=payload.get("safety_status"),
        saveable=payload.get("saveable"),
        errors=errors,
        response_status=payload.get("status"),
    )


def run_probe(
    cases: list[dict[str, Any]],
    api_base: str,
    api_key: str,
    timeout: float,
    post_json: Callable[[str, dict[str, Any], str, float], tuple[int, dict[str, Any]]] | None = None,
    fail_fast: bool = False,
) -> list[ProbeResult]:
    poster = post_json or _post_json
    url = api_base.rstrip("/") + DRAFT_PATH
    results: list[ProbeResult] = []
    for prompt_case in cases:
        request_payload = {
            "request_text": prompt_case["prompt"],
            "mode": prompt_case.get("mode", "alert_rule"),
        }
        try:
            status_code, payload = poster(url, request_payload, api_key, timeout)
            result = validate_probe_response(prompt_case, payload, status_code)
        except Exception as exc:
            result = ProbeResult(
                id=str(prompt_case.get("id", "unknown")),
                prompt=str(prompt_case.get("prompt", "")),
                passed=False,
                expected_domain=str(prompt_case.get("expected_domain") or ""),
                errors=[f"request_failed:{_sanitize_error(exc)}"],
            )
        results.append(result)
        if fail_fast and not result.passed:
            break
    return results


def _post_json(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    if not url.endswith(DRAFT_PATH):
        raise ValueError("Probe may only call the AI draft endpoint")
    if url.endswith(SAVE_RULE_PATH):
        raise ValueError("Probe must never call the Save Rule endpoint")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            return response.status, json.loads(response_body)
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError:
            payload = {"error": response_body[:240]}
        return exc.code, payload


def filter_cases(
    cases: list[dict[str, Any]],
    prompt_id: str | None,
) -> list[dict[str, Any]]:
    if not prompt_id:
        return cases
    filtered = [case for case in cases if case.get("id") == prompt_id]
    if not filtered:
        raise ValueError(f"Prompt id not found: {prompt_id}")
    return filtered


def print_text_report(results: list[ProbeResult]) -> None:
    passed = 0
    for result in results:
        if result.passed:
            passed += 1
            print(f"PASS {result.id} -> {result.expected_domain}")
        else:
            reason = ", ".join(result.errors or ["unknown_error"])
            print(f"FAIL {result.id} -> {result.expected_domain} ({reason})")
    print(f"{passed} passed, {len(results) - passed} failed")


def results_to_json(results: list[ProbeResult]) -> dict[str, Any]:
    passed = sum(1 for result in results if result.passed)
    return {
        "passed": passed,
        "failed": len(results) - passed,
        "results": [asdict(result) for result in results],
    }


def _sanitize_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").replace("\r", " ").strip()
    return text[:240] or exc.__class__.__name__


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local Rule AI golden prompts through the draft endpoint only."
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--prompt-id")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("FINANCE_API_KEY", "").strip()
    if not api_key:
        print("FINANCE_API_KEY is required in the environment.", file=sys.stderr)
        return 2
    cases = filter_cases(load_fixture(args.fixture), args.prompt_id)
    results = run_probe(
        cases,
        api_base=args.api_base,
        api_key=api_key,
        timeout=args.timeout,
        fail_fast=args.fail_fast,
    )
    if args.json_output:
        print(json.dumps(results_to_json(results), indent=2, sort_keys=True))
    else:
        print_text_report(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
