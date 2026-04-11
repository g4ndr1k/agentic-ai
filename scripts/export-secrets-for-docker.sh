#!/bin/bash
# export-secrets-for-docker.sh — Regenerate secret files from macOS Keychain
# for Docker container mounts.
#
# Keychain is the source of truth. This script exports secrets into the
# secrets/ directory so that docker-compose volume mounts work.
#
# Run this after `python3 -m bridge.secret_manager init` or whenever
# secrets change:
#   ./scripts/export-secrets-for-docker.sh
#
set -euo pipefail

SECRETS_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets"
PYTHON="/opt/homebrew/bin/python3.14"

echo "Exporting secrets from Keychain → $SECRETS_DIR/"

# ── Google service account JSON ─────────────────────────────────────────
echo -n "  google_service_account.json ... "
$PYTHON -c "
import sys, json
sys.path.insert(0, '$(cd "$(dirname \"\$0\")/..\" && pwd)')
from bridge.secret_manager import get_from_keychain, _load_settings, _keychain_service
settings = _load_settings()
service = _keychain_service(settings)
raw = get_from_keychain(service, 'google_service_account_json')
if raw:
    # Keychain stores JSON as-is; write directly
    with open('$SECRETS_DIR/google_service_account.json', 'w') as f:
        f.write(raw)
    print('✓')
else:
    print('✗ (not in Keychain)')
" 2>/dev/null

# ── Google OAuth credentials JSON ───────────────────────────────────────
echo -n "  google_credentials.json ... "
$PYTHON -c "
import sys, json
sys.path.insert(0, '$(cd "$(dirname \"\$0\")/..\" && pwd)')
from bridge.secret_manager import get_from_keychain, _load_settings, _keychain_service
settings = _load_settings()
service = _keychain_service(settings)
raw = get_from_keychain(service, 'google_credentials_json')
if raw:
    with open('$SECRETS_DIR/google_credentials.json', 'w') as f:
        f.write(raw)
    print('✓')
else:
    print('✗ (not in Keychain)')
" 2>/dev/null

# ── Google OAuth token JSON ────────────────────────────────────────────
echo -n "  google_token.json ... "
$PYTHON -c "
import sys, json
sys.path.insert(0, '$(cd "$(dirname \"\$0\")/..\" && pwd)')
from bridge.secret_manager import get_from_keychain, _load_settings, _keychain_service
settings = _load_settings()
service = _keychain_service(settings)
raw = get_from_keychain(service, 'google_token_json')
if raw:
    with open('$SECRETS_DIR/google_token.json', 'w') as f:
        f.write(raw)
    print('✓')
else:
    print('✗ (not in Keychain — will be created on first OAuth flow)')
" 2>/dev/null

# ── Bridge token ────────────────────────────────────────────────────────
echo -n "  bridge.token ... "
$PYTHON -c "
import sys, os
sys.path.insert(0, '$(cd "$(dirname \"\$0\")/..\" && pwd)')
from bridge.secret_manager import get_from_keychain, _load_settings, _keychain_service
settings = _load_settings()
service = _keychain_service(settings)
raw = get_from_keychain(service, 'bridge_token')
if raw:
    os.makedirs('$SECRETS_DIR/bridge.token', exist_ok=True)
    with open('$SECRETS_DIR/bridge.token/bridge.token', 'w') as f:
        f.write(raw)
    print('✓')
else:
    print('✗ (not in Keychain)')
" 2>/dev/null

# ── Bank passwords (as banks.toml for Docker) ──────────────────────────
echo -n "  banks.toml ... "
$PYTHON -c "
import sys
sys.path.insert(0, '$(cd "$(dirname \"\$0\")/..\" && pwd)')
from bridge.secret_manager import get_from_keychain, _load_settings, _keychain_service
settings = _load_settings()
service = _keychain_service(settings)
raw = get_from_keychain(service, 'banks_toml')
if raw:
    with open('$SECRETS_DIR/banks.toml', 'w') as f:
        f.write(raw)
    print('✓')
else:
    print('✗ (not in Keychain)')
" 2>/dev/null

echo ""
echo "Done. Files in $SECRETS_DIR/:"
ls -la "$SECRETS_DIR/" | grep -v DS_Store | grep -v README | grep -v total | grep -v '^d'
