#!/usr/bin/env python3
"""
Repair Maybank CC foreign-currency rows that were parsed with Indonesian
dot-thousands values as decimals instead of whole IDR integers.

This script updates three places so they stay in sync:
1. output/xls/ALL_TRANSACTIONS.xlsx
2. Google Sheets Transactions tab
3. SQLite finance cache

Heuristic:
- institution = Maybank
- original_currency is non-IDR
- exchange_rate < 1000
- abs(amount_idr) < 1000

For affected rows, exchange_rate and amount_idr are multiplied by 1000.
The transaction hash is recomputed because the hash includes amount.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance.config import load_config, get_finance_config, get_sheets_config
from finance.models import make_hash
from finance.sheets import SheetsClient


@dataclass
class FixRow:
    date: str
    raw_description: str
    institution: str
    account: str
    owner: str
    amount: float
    exchange_rate: float
    old_hash: str
    new_amount: float
    new_exchange_rate: float
    new_hash: str


def _needs_fix(institution, currency, exchange_rate, amount_idr) -> bool:
    if institution != "Maybank":
        return False
    if not currency or currency == "IDR":
        return False
    if exchange_rate in (None, "") or amount_idr in (None, ""):
        return False
    try:
        return float(exchange_rate) < 1000 and abs(float(amount_idr)) < 1000
    except (TypeError, ValueError):
        return False


def fix_xlsx(path: str) -> list[FixRow]:
    wb = openpyxl.load_workbook(path)
    ws = wb["ALL_TRANSACTIONS"]

    fixed: list[FixRow] = []

    for row in ws.iter_rows(min_row=2):
        owner = row[0].value
        institution = row[2].value
        date_tx = row[4].value
        raw_desc = row[6].value
        currency = row[7].value
        exchange_rate = row[9].value
        amount_idr = row[10].value
        account = row[13].value

        if not _needs_fix(institution, currency, exchange_rate, amount_idr):
            continue

        new_exchange_rate = float(exchange_rate) * 1000
        new_amount = float(amount_idr) * 1000
        if row[11].value and str(row[11].value).lower() == "debit":
            signed_amount = -abs(new_amount)
        else:
            signed_amount = abs(new_amount)

        old_hash = make_hash(
            _xlsx_date_to_iso(date_tx),
            -abs(float(amount_idr)) if str(row[11].value).lower() == "debit" else abs(float(amount_idr)),
            str(raw_desc),
            str(institution),
            str(owner),
        )
        new_hash = make_hash(
            _xlsx_date_to_iso(date_tx),
            signed_amount,
            str(raw_desc),
            str(institution),
            str(owner),
        )

        row[9].value = round(new_exchange_rate)
        row[10].value = round(new_amount)

        fixed.append(FixRow(
            date=_xlsx_date_to_iso(date_tx),
            raw_description=str(raw_desc),
            institution=str(institution),
            account=str(account),
            owner=str(owner),
            amount=signed_amount,
            exchange_rate=float(exchange_rate),
            old_hash=old_hash,
            new_amount=signed_amount,
            new_exchange_rate=round(new_exchange_rate),
            new_hash=new_hash,
        ))

    if fixed:
        wb.save(path)
    wb.close()
    return fixed


def _xlsx_date_to_iso(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    s = str(value)
    dd, mm, yyyy = s.split("/")
    return f"{yyyy}-{mm}-{dd}"


def fix_sheets(rows_to_fix: list[FixRow], client: SheetsClient):
    if not rows_to_fix:
        return 0
    rows = client._get(f"{client.cfg.transactions_tab}!A:O")
    updates = []
    matched = 0
    by_key = {
        (r.date, r.raw_description, r.institution, r.account, r.owner): r
        for r in rows_to_fix
    }
    for idx, row in enumerate(rows[1:], start=2):
        r = list(row) + [""] * (15 - len(row))
        key = (r[0], r[5], r[8], r[9], r[10])
        fix = by_key.get(key)
        if not fix:
            continue
        updates.append({
            "range": f"{client.cfg.transactions_tab}!B{idx}:M{idx}",
            "values": [[
                fix.new_amount,
                r[2],
                r[3],
                fix.new_exchange_rate,
                r[5],
                r[6],
                r[7],
                r[8],
                r[9],
                r[10],
                r[11],
                fix.new_hash,
            ]],
        })
        matched += 1

    if updates:
        client.service.spreadsheets().values().batchUpdate(
            spreadsheetId=client.cfg.spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
    return matched


def fix_sqlite(rows_to_fix: list[FixRow], db_path: str):
    if not rows_to_fix:
        return 0
    conn = sqlite3.connect(db_path)
    updated = 0
    for row in rows_to_fix:
        cur = conn.execute(
            """
            UPDATE transactions
               SET amount = ?, exchange_rate = ?, hash = ?
             WHERE date = ? AND raw_description = ? AND institution = ? AND account = ? AND owner = ?
            """,
            (
                row.new_amount,
                row.new_exchange_rate,
                row.new_hash,
                row.date,
                row.raw_description,
                row.institution,
                row.account,
                row.owner,
            ),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()
    return updated


def main():
    cfg = load_config()
    finance_cfg = get_finance_config(cfg)
    sheets = SheetsClient(get_sheets_config(cfg))
    xlsx_path = finance_cfg.xlsx_input

    rows_to_fix = fix_xlsx(xlsx_path)
    print(f"Patched XLSX rows: {len(rows_to_fix)}")
    for row in rows_to_fix:
        print(f"  {row.date} {row.raw_description[:40]} -> {abs(row.new_amount):,.0f} @ {row.new_exchange_rate:,.0f}")

    sheets_count = fix_sheets(rows_to_fix, sheets)
    print(f"Patched Sheets rows: {sheets_count}")

    sqlite_count = fix_sqlite(rows_to_fix, finance_cfg.sqlite_db)
    print(f"Patched SQLite rows: {sqlite_count}")


if __name__ == "__main__":
    main()
