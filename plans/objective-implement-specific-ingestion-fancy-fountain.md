# Plan: IPOT & BNIS Statement Auto-Ignore Ingestion Rules

## Context

The finance pipeline ingests transactions from multiple brokers. Two Permata RDN accounts are linked to brokerage accounts:
- **9912259088** → IPOT (PT Indo Premier Sekuritas) Client Statements
- **9916181458** → BNI Sekuritas (BNIS) Client Statements

**Problem:** Transactions from IPOT Client Statement PDFs and BNIS Cash RDN section are cash-flow duplicates of the Permata RDN statement for the same accounts. Importing them as active transactions causes double-counting in net worth / income calculations.

**Existing pattern to remove:** `finance/importer.py` already auto-ignores Permata RDN transactions (`institution="Permata"` + `stmt_type="rdn"`) by setting `merchant="Permata RDN"` and `category="Ignored"`. This keeps records visible in the Audit View (via `/api/transactions?category=Ignored`) while excluding them from income/expense summaries.

## What Changes

### Single file: `finance/importer.py`

Two additions to the existing auto-ignore logic (lines ~249–279):

**1. Extract a helper function** above `direct_import` to consolidate all auto-ignore rules:

```python
def _auto_ignore_merchant(institution: str, stmt_type: str) -> str | None:
    inst = institution.lower()
    if inst == "ipot" and stmt_type == "statement":
        return "IPOT RDN"
    if inst == "bni sekuritas":
        return "BNIS RDN"
    return None
```

**2. Replace the `is_rdn` boolean** in the import loop with the helper result:

```python
# Before (×2 in the loop — once for overwrite path, once for new path):
is_rdn = txn.institution.lower() == "permata" and stmt_type == "rdn"
if is_rdn:
    txn.merchant = "Permata RDN"
    txn.category = "Ignored"

# After:
auto_merchant = _auto_ignore_merchant(txn.institution, stmt_type)
if auto_merchant:
    txn.merchant = auto_merchant
    txn.category = "Ignored"
    by_layer[1] += 1
```

Both the **overwrite path** (lines ~252–266) and the **new-transaction path** (lines ~271–279) must be updated.

## Why This Is Sufficient (No Parser Changes Needed)

| Parser | `institution` in XLSX | `stmt_type` in XLSX | Transactions extracted? |
|---|---|---|---|
| `ipot_statement.py` | `"IPOT"` | `"statement"` | Yes — Cash RDN flows |
| `bni_sekuritas.py` | `"BNI Sekuritas"` | `"portfolio"` | Yes — Cash RDN flows |
| `bni_sekuritas_legacy.py` | `"BNI Sekuritas"` | varies | No transactions (intentional) |
| `ipot_portfolio.py` | `"IPOT"` | (not "statement") | No transactions |

The BNIS rule uses `inst == "bni sekuritas"` without a `stmt_type` guard because:
- Legacy BNIS doesn't emit transactions (safe to match broadly)
- Any future BNIS statement type with cash flows should also be ignored for this account

## Critical Files

- **`finance/importer.py`** — only file to change; lines ~249–280 (the `is_rdn` block, ×2)

## Verification

1. Run `python3 -m finance.importer` with an IPOT Client Statement PDF in the inbox.
2. Query: `GET /api/transactions?category=Ignored&institution=IPOT` — should return the imported transactions.
3. Query: `GET /api/transactions?category=Ignored&institution=BNI+Sekuritas` — same for BNIS.
4. Confirm these transactions do **not** appear in monthly income/expense totals (`GET /api/transactions/summary/monthly`), which already filters `category NOT IN ('Ignored', ...)`.
5. Confirm `GET /api/transactions?category=Ignored` surfaces all three merchant types: `Permata RDN`, `IPOT RDN`, `BNIS RDN`.
