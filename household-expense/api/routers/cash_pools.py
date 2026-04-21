"""Cash pool endpoints (backend API, hidden from PWA UI in v1)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import require_auth
from api.db import get_db
from api.models import CashPoolCreate, CashPoolResponse, CashPoolUpdate

router = APIRouter(prefix="/api/household/cash-pools", tags=["cash-pools"])


@router.get("", response_model=list[CashPoolResponse])
def list_cash_pools(_auth: dict = Depends(require_auth)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, funded_amount, funded_at, remaining_amount, status, notes "
            "FROM cash_pools ORDER BY funded_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=CashPoolResponse, status_code=status.HTTP_201_CREATED)
def create_cash_pool(body: CashPoolCreate, _auth: dict = Depends(require_auth)):
    pool_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO cash_pools (id, name, funded_amount, funded_at, remaining_amount, status, notes) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (pool_id, body.name, body.funded_amount, body.funded_at, body.funded_amount, body.notes),
        )
        row = conn.execute("SELECT * FROM cash_pools WHERE id = ?", (pool_id,)).fetchone()

    return dict(row)


@router.put("/{pool_id}", response_model=CashPoolResponse)
def update_cash_pool(pool_id: str, body: CashPoolUpdate, _auth: dict = Depends(require_auth)):
    if body.remaining_amount is not None and body.adjustment_amount is not None:
        raise HTTPException(status_code=400, detail="Use remaining_amount or adjustment_amount, not both")

    with get_db() as conn:
        row = conn.execute("SELECT * FROM cash_pools WHERE id = ?", (pool_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cash pool not found")

        remaining_amount = row["remaining_amount"]
        if body.adjustment_amount is not None:
            remaining_amount = remaining_amount + body.adjustment_amount
        elif body.remaining_amount is not None:
            remaining_amount = body.remaining_amount

        if remaining_amount < 0:
            raise HTTPException(status_code=400, detail="remaining_amount cannot be negative")

        updates = {
            "name": body.name if body.name is not None else row["name"],
            "funded_amount": body.funded_amount if body.funded_amount is not None else row["funded_amount"],
            "funded_at": body.funded_at if body.funded_at is not None else row["funded_at"],
            "remaining_amount": remaining_amount,
            "status": body.status if body.status is not None else row["status"],
            "notes": body.notes if body.notes is not None else row["notes"],
        }
        conn.execute(
            "UPDATE cash_pools SET name = ?, funded_amount = ?, funded_at = ?, remaining_amount = ?, status = ?, notes = ? WHERE id = ?",
            (
                updates["name"],
                updates["funded_amount"],
                updates["funded_at"],
                updates["remaining_amount"],
                updates["status"],
                updates["notes"],
                pool_id,
            ),
        )
        updated = conn.execute("SELECT * FROM cash_pools WHERE id = ?", (pool_id,)).fetchone()

    return dict(updated)
