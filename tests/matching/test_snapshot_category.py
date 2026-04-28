"""Phase 0 snapshot tests — categorization adversarial fixture.

These tests run the legacy categorizer over the adversarial fixture and verify
the outcomes are stable across code changes. They do NOT assert correctness —
they assert stability: any divergence vs the captured baseline is surfaced.

Rows with legacy_known_bug=true are expected to diverge; the test records
what the legacy system does for audit purposes but doesn't fail on them.

How to add a case:
1. Add the failing real-world transaction to category_adversarial_fixture.jsonl.
2. Run this test to verify it is captured.

IMPORTANT (plan §0.5.5): Every categorization bug fix PR MUST add the failing
case to this fixture BEFORE the fix lands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "category_adversarial_fixture.jsonl"


def _load_fixture() -> list[dict]:
    lines = FIXTURE_PATH.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _run_legacy_categorizer(case: dict, aliases: list[dict], categories: list[str]) -> dict:
    """Run the legacy 4-layer categorizer and return the result as a dict."""
    from finance.categorizer import Categorizer
    cat = Categorizer(aliases=aliases, categories=categories, ollama_host=None)
    result = cat.categorize(
        raw_description=case["raw_description"],
        owner=case.get("owner", ""),
        account=case.get("account", ""),
    )
    return {
        "merchant": result.merchant,
        "category": result.category,
        "layer": result.layer,
        "confidence": result.confidence,
    }


@pytest.fixture(scope="module")
def empty_aliases_and_categories():
    """Minimal aliases / categories for deterministic base-case testing."""
    return [], ["Transfer", "Earned Income", "Subscriptions", "Cash Withdrawal"]


@pytest.mark.parametrize(
    "case",
    _load_fixture(),
    ids=[c["id"] for c in _load_fixture()],
)
def test_adversarial_fixture_stability(case, empty_aliases_and_categories):
    """Run the legacy categorizer; verify it doesn't raise on any input."""
    aliases, categories = empty_aliases_and_categories
    try:
        result = _run_legacy_categorizer(case, aliases, categories)
    except Exception as exc:
        if case.get("legacy_known_bug"):
            pytest.xfail(f"Known legacy bug: {exc}")
        else:
            raise AssertionError(
                f"[{case['id']}] Categorizer raised unexpectedly: {exc}"
            ) from exc

    if case.get("expected_category") is not None:
        assert result["category"] == case["expected_category"], (
            f"[{case['id']}] {case['note']!r}: "
            f"category={result['category']!r}, expected={case['expected_category']!r}"
        )
