# Agentic AI

Personal finance and mail-alert system for macOS.

This repo combines three production stages:
- Stage 1: Apple Mail + iMessage bridge and mail alert agent
- Stage 2: bank-statement parsing, Google Sheets import, FastAPI backend, and finance PWA
- Stage 3: wealth tracking, holdings, balances, liabilities, and net-worth dashboards

The system is built for a personal Apple-centric workflow:
- macOS host services for Mail.app, Messages.app, and protected local databases
- Dockerized agent and finance API services
- Vue 3 PWA frontend for iPhone and desktop use
- macOS Keychain as the preferred secret store

## What it does

- Reads Apple Mail local data on macOS
- Classifies financial emails with Ollama
- Sends iMessage alerts through Messages.app
- Accepts `agent:` commands from authorized iMessage senders
- Parses password-protected bank and brokerage PDFs
- Exports normalized XLSX transaction data
- Imports and categorizes transactions into Google Sheets
- Syncs Sheets data into SQLite for fast local reads
- Serves a personal finance and wealth dashboard as a PWA
- Supports offline PWA reads via service worker + IndexedDB cache

## Architecture

- bridge/ runs on the host Mac
  - reads Mail.app and Messages.app SQLite databases
  - sends iMessages via AppleScript
  - exposes authenticated HTTP endpoints on localhost
  - runs PDF processing and pipeline orchestration
- agent/ runs in Docker
  - polls the bridge
  - classifies messages with Ollama
  - sends alerts and handles commands
- finance/ runs as a FastAPI backend
  - exposes finance and wealth APIs
  - serves the built PWA from pwa/dist/
- pwa/ is a Vue 3 + Vite application
  - mobile-first personal finance UI
  - offline-capable with service worker and IndexedDB-backed GET fallback

## Repository layout

- agent/ — Dockerized mail agent
- bridge/ — macOS host bridge for Mail, Messages, PDF processing, and orchestration
- finance/ — FastAPI backend, Google Sheets sync/import, SQLite cache, wealth APIs
- parsers/ — bank and brokerage PDF parsers
- exporters/ — XLSX export pipeline
- pwa/ — Vue 3 PWA frontend
- config/settings.toml — runtime configuration
- SYSTEM_DESIGN.md — full architecture and operations document

## Requirements

- Apple Silicon Mac running macOS
- Docker Desktop
- Homebrew Python 3.14
- Ollama running locally
- Mail.app configured and syncing locally
- Messages.app signed in
- Full Disk Access granted to /Applications/AgenticAI.app

## Quick start

### 1. Install core dependencies

```bash
brew install ollama jq sqlite python@3.14
brew install --cask docker
ln -sf /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3
```

### 2. Install Python PDF dependencies

```bash
/opt/homebrew/bin/pip3 install pikepdf pdfplumber openpyxl
```

### 3. Start Ollama and pull the model

```bash
ollama pull gemma4:e4b
```

### 4. Configure the app bundle for stable TCC identity

```bash
./scripts/setup-app.sh
```

Then grant Full Disk Access to:
- /Applications/AgenticAI.app

### 5. Configure secrets

This project prefers macOS Keychain over plaintext secret files.
Use the project’s Keychain helpers in bridge/secret_manager.py and related scripts.

### 6. Build the PWA and start containers

```bash
cd pwa
npm install
npm run build
cd ..
docker compose up --build -d
```

## Common commands

### Finance API

```bash
python3 -m finance.server
python3 -m finance.server --reload
python3 -m finance.sync
python3 -m finance.importer --dry-run
python3 -m finance.importer
```

### PWA

```bash
cd pwa
npm install
npm run dev
npm run build
npm test
```

### Docker

```bash
docker compose up --build -d
docker compose logs -f finance-api
docker compose logs -f mail-agent
```

## PWA notes

- Mobile-first, but also supports a desktop layout
- Offline state on mobile is shown by the header status dot turning red
- Successful GET responses are cached for offline reopening
- Offline mutations are queued and replayed on reconnect
- iOS may hold onto old PWA bundles aggressively; after a redeploy, force-close/reopen or re-add the home screen app if needed

## Security and secrets

- Secrets should live in macOS Keychain, not committed files
- Docker containers consume exported secret artifacts when needed
- Bridge endpoints use bearer authentication
- The bridge is the only component that directly reads protected Mail/Messages databases

## Supported document sources

The repo includes parsers for multiple institutions, including:
- Maybank
- BCA
- Permata
- CIMB Niaga
- IPOT / Indo Premier
- BNI Sekuritas
- Stockbit Sekuritas

Outputs feed both transaction workflows and wealth holdings/balance workflows.

## Documentation

- SYSTEM_DESIGN.md — canonical deep-dive design and ops guide
- CLAUDE.md — project-specific workflow notes and commands

## Status

Current state:
- Stage 1 complete
- Stage 2 fully built
- Stage 3 fully built

## License

Private/personal project unless you choose otherwise.
