#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

section() {
  printf '\n========== %s ==========\n' "$1"
}

cd "${ROOT_DIR}"

section "Backend targeted safety suites"
"${PYTHON_BIN}" -m pytest agent/tests/test_rule_explain.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_rule_ai_builder.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_rule_ai_golden_probe.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_rule_ai_save_compatibility.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_rule_ai_audit.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_action_execution.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_action_approvals.py -q
"${PYTHON_BIN}" -m pytest agent/tests/test_imap_mutations.py -q

section "Backend full suite"
"${PYTHON_BIN}" -m pytest agent/tests -q

section "Dashboard helper tests"
cd "${ROOT_DIR}/mail-dashboard"
npm run test:rules-ui

section "Dashboard Playwright E2E"
npm run test:e2e

section "Dashboard build"
npm run build

section "Mail Agent preflight"
cd "${ROOT_DIR}"
python3 scripts/mailagent_preflight.py

section "Phase 4 verification complete"
