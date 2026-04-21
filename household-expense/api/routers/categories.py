"""Category CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import require_auth
from api.db import get_db
from api.models import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/api/household/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(_auth: dict = Depends(require_auth)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT code, label_id, sort_order, is_active FROM household_categories WHERE is_active = 1 ORDER BY sort_order, label_id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, _auth: dict = Depends(require_auth)):
    with get_db() as conn:
        existing = conn.execute("SELECT code FROM household_categories WHERE code = ?", (body.code,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Category already exists: {body.code}")
        conn.execute(
            "INSERT INTO household_categories (code, label_id, sort_order, is_active) VALUES (?, ?, ?, 1)",
            (body.code, body.label_id, body.sort_order),
        )
        row = conn.execute(
            "SELECT code, label_id, sort_order, is_active FROM household_categories WHERE code = ?",
            (body.code,),
        ).fetchone()
    return dict(row)


@router.put("/{code}", response_model=CategoryResponse)
def update_category(code: str, body: CategoryUpdate, _auth: dict = Depends(require_auth)):
    with get_db() as conn:
        current = conn.execute(
            "SELECT code, label_id, sort_order, is_active FROM household_categories WHERE code = ?",
            (code,),
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Category not found")
        if body.code != code:
            existing = conn.execute("SELECT code FROM household_categories WHERE code = ?", (body.code,)).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail=f"Category already exists: {body.code}")
            conn.execute(
                "INSERT INTO household_categories (code, label_id, sort_order, is_active) VALUES (?, ?, ?, ?)",
                (body.code, body.label_id, body.sort_order, current['is_active']),
            )
            conn.execute("UPDATE household_transactions SET category_code = ? WHERE category_code = ?", (body.code, code))
            conn.execute("DELETE FROM household_categories WHERE code = ?", (code,))
        else:
            conn.execute(
                "UPDATE household_categories SET label_id = ?, sort_order = ? WHERE code = ?",
                (body.label_id, body.sort_order, code),
            )
        row = conn.execute(
            "SELECT code, label_id, sort_order, is_active FROM household_categories WHERE code = ?",
            (body.code,),
        ).fetchone()
    return dict(row)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(code: str, _auth: dict = Depends(require_auth)):
    with get_db() as conn:
        cur = conn.execute("UPDATE household_categories SET is_active = 0 WHERE code = ? AND is_active = 1", (code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Category not found")
