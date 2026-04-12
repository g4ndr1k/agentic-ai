# Verified Review of `qwen_audit.md`

**Verified on:** 2026-04-11  
**Verified against:** checked-in codebase in `/Users/g4ndr1k/agentic-ai`  
**Purpose:** verify the claims in the original Qwen-generated audit against the current repository state. This is not a brand-new full audit.

---

## Summary

The original `qwen_audit.md` was directionally useful, but it mixed real issues with a few overstatements and at least one claim that I could not substantiate from the current code.

### Verification outcome

- Confirmed: 38 findings
- Partial / needs reframing: 6 findings
- Not substantiated as a current bug: 2 findings
- Not revalidated in this pass: 1 finding

### Bottom line

- The strongest confirmed problems are still around wealth explanation logic, auth fallback behavior, database concurrency hardening, stale carry-forward values, weak transaction dedup identity, and a handful of API hardening gaps.
- The original CRITICAL section was overstated. One item is a real bug but not obviously critical, one is only partially true, and one is a client robustness issue rather than an auth bypass.
- The report is not exhaustive. It also missed several Stage 3 integrity issues that were found and patched separately in this repo.

---

## Highest-Priority Confirmed Issues

| Revised priority | File | Verified issue |
|---|---|---|
| High | `finance/api.py` | `_wealth_delta_rows()` treats liabilities as a positive delta source in the explanation layer, which can invert the meaning of debt changes in wealth explanations. |
| High | `bridge/auth.py` | `token_source="keychain"` still falls back silently to file-based auth on Keychain miss. |
| High | `finance/db.py` | Finance DB connections do not set `PRAGMA busy_timeout`, so lock contention can fail immediately. |
| High | `finance/db.py` | `idx_tx_hash` is redundant because `transactions.hash` is already `UNIQUE`. |
| High | `finance/api.py` | `carry_forward_holdings()` copies stale valuation fields forward without price refresh. |
| High | `scripts/seed_gold_holdings.py` | Gold seeding hardcodes `institution="Physical"`, so UI-entered gold with another institution label can coexist and double-count. |
| High | `finance/categorizer.py` | Contains-match alias logic is vulnerable to short-substring false positives and only sorts by filtered-vs-generic, not by specificity length. |
| High | `finance/categorizer.py` | Ollama categorization path has no retry, so transient failures spill work into review. |
| High | `finance/sheets.py` | Cached Sheets client never resets on auth/service failure. |
| High | `finance/sync.py` | `open_db()` connection can leak if Sheets reads fail before the `with conn:` block completes. |
| High | `finance/models.py` | Transaction hash omits `account`, creating a real cross-account collision risk. |

---

## Confirmed Findings

### Critical / High from the original report

| Original ID | Status | Revised priority | Notes |
|---|---|---|---|
| C2 | Confirmed | High | [finance/api.py] liabilities explanation sign issue is real, but it affects explanation correctness rather than stored net worth math. |
| H1 | Confirmed | High | [bridge/auth.py] does silently fall back from Keychain to file. |
| H3 | Confirmed | High | [finance/db.py] has no `busy_timeout`. |
| H4 | Confirmed | High | [finance/db.py] has redundant hash index. |
| H5 | Confirmed | High | [finance/api.py] carry-forward copies stale values. |
| H6 | Confirmed | High | [scripts/seed_gold_holdings.py] + [finance/api.py] can create duplicate gold rows by institution naming mismatch. |
| H7 | Confirmed | High | [finance/categorizer.py] contains matching can over-match. |
| H8 | Confirmed | High | [finance/categorizer.py] has no retry on Ollama suggestion failures. |
| H9 | Confirmed | High | [finance/sheets.py] service object is cached indefinitely. |
| H10 | Confirmed | High | [finance/sync.py] can leak the DB connection if earlier reads raise. |
| H11 | Confirmed | High | [finance/models.py] hash excludes `account`. |

### Medium findings confirmed from code

| Original ID | Status | Revised priority | Notes |
|---|---|---|---|
| M1 | Confirmed | Medium | [finance/models.py] `parse_xlsx_date()` does not validate actual calendar correctness. |
| M2 | Confirmed | Medium | [finance/db.py] only applies additive migrations for `merchant_aliases`; transaction table evolution is not covered. |
| M3 | Confirmed | Medium | [finance/db.py] has no `transactions.institution` index. |
| M4 | Confirmed | Medium | [finance/db.py] has no `transactions.account` index. |
| M5 | Confirmed | Medium | [bridge/server.py] and [finance/api.py] return raw exception details to clients in some paths. |
| M8 | Confirmed | Medium | [finance/api.py] docstring says Keychain-first; implementation is env-first. |
| M9 | Confirmed | Medium | [finance/api.py] CORS is fully wildcarded for methods and headers while credentials are enabled. |
| M10 | Confirmed | Medium | [finance/api.py] has no rate limiting for expensive mutation/calc endpoints. |
| M11 | Confirmed | Medium | [finance/db.py] migration detection uses brittle SQL string matching. |
| M12 | Confirmed | Medium | [finance/api.py] still includes `Transfer` / `Adjustment` rows in `by_category` with `0%` expense. |
| M13 | Confirmed | Medium | [finance/api.py] wealth explanation Ollama paths have no retry. |
| M14 | Confirmed | Medium | [scripts/seed_gold_holdings.py] includes the current incomplete month. |
| M15 | Confirmed | Medium | [finance/api.py] `_row()` assumes `sqlite3.Row` is always in use. |
| M16 | Confirmed | Medium | [bridge/server.py] JSON parsing does not enforce `Content-Type: application/json`. |

### Low findings confirmed from code

| Original ID | Status | Revised priority | Notes |
|---|---|---|---|
| L1 | Confirmed | Low | [finance/db.py] stores money in `REAL`. |
| L2 | Confirmed | Low | [finance/db.py] `merchant_aliases` has no uniqueness rule. |
| L3 | Confirmed | Low | [finance/db.py] enables foreign keys without declaring any. |
| L4 | Confirmed | Low | [finance/db.py] `sync_log` grows without retention handling. |
| L5 | Confirmed | Low | [scripts/seed_gold_holdings.py] uses direct `sqlite3.connect()`, bypassing `open_db()`. |
| L6 | Confirmed | Low | [finance/models.py] `DD-MM-YY` parsing hardcodes `20xx`. |
| L9 | Confirmed | Low | [finance/api.py] `_import_run` uses `_get_sheets()`, but the follow-on sync passes `_sheets` directly. |
| L10 | Confirmed | Low | [pwa/src/stores/finance.js] `currentMonthKey` is frozen at store creation time. |
| L11 | Confirmed | Low | [pwa/src/stores/finance.js] month normalization enforces a minimum but not an explicit moving upper bound beyond the startup month. |
| L12 | Confirmed | Low | [finance/sheets.py] `write_override()` is a read-then-write TOCTOU pattern. |
| L14 | Confirmed | Low | [bridge/server.py] invalid `limit` parsing can bubble into raw exception responses. |
| L15 | Confirmed | Low | [bridge/server.py] TCC/FDA check is only performed at startup. |
| L16 | Confirmed | Low | [bridge/secret_manager.py] itself documents that `security ... -w` briefly exposes secrets to same-user process inspection. |

---

## Partial / Needs Reframing

These claims point at something real, but the original write-up overstated impact or mixed proven behavior with assumptions.

| Original ID | Status | Revised priority | Why it changed |
|---|---|---|---|
| C1 | Partial | Medium | I verified that `conn.executescript(SCHEMA)` in [finance/db.py] commits an open transaction. I did **not** verify the claim that it resets `isolation_level` on the current runtime. |
| C3 | Partial | Medium | [pwa/src/api/client.js] really does strip auth headers when the env var is empty, but [finance/api.py] fails closed. This is a client robustness/configuration issue, not a proven backend auth bypass. |
| M6 | Partial | Medium | There is no request-body limit visible in FastAPI code, but deployment-level limits were not checked. Keep as hardening work, not a proven exploit path. |
| M7 | Partial | Medium | Raw transaction data is interpolated into LLM prompts, but the practical impact is better framed as prompt-hardening work than a concrete compromise. |
| L13 | Partial | Low | Same reasoning as M7 for the wealth explainer prompts. |
| L17 | Partial | Low | The hex auto-detection concern is plausible in theory, but the current code already guards with even-length hex plus UTF-8 decode, so the residual risk is speculative. |

---

## Not Substantiated As A Current Bug

| Original ID | Status | Revised priority | Why it was not retained as a bug |
|---|---|---|---|
| H2 | Not substantiated | Low | I tested current sqlite behavior and did not reproduce the claimed transactional breakage from `with conn:` plus `BEGIN IMMEDIATE` in [finance/sync.py]. The pattern is awkward, but the report’s failure mode was not demonstrated. |
| L7 | Not substantiated | Low | The SPA/static mount in [finance/api.py] is intentionally placed after current API routes. This is only a possible future routing hazard, not a present bug. |

---

## Not Revalidated In This Pass

| Original ID | Status | Note |
|---|---|---|
| L8 | Not revalidated | The claimed example/help-text issue in `bridge/secret_manager.py` was not rechecked during this verification pass. |

---

## Verification Notes

- I manually reviewed the cited files and ran small local sqlite behavior checks where the original report made strong transactional claims.
- I verified the `executescript()` commit behavior directly. It does commit an active transaction in the current Python sqlite runtime.
- I also checked the current code after recent Stage 3 fixes. Some integrity bugs that existed elsewhere in the wealth stack were not mentioned in the original Qwen report at all, so this document should not be treated as exhaustive.

---

## Practical Next Steps

If this file is used as the working audit source, the best current queue is:

1. Fix the confirmed explanation/auth/database hardening issues first:
   `C2`, `H1`, `H3`, `H5`, `H11`
2. Clean up operational reliability next:
   `H8`, `H9`, `H10`, `M13`
3. Then address consistency and performance debt:
   `H4`, `M1`, `M2`, `M3`, `M4`, `M8`, `M9`, `M12`

The original severity labels should no longer be used as-is. This verified version is the safer basis for follow-up work.
