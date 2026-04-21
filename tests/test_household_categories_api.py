from pathlib import Path
import sys
import types

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOUSEHOLD_ROOT = PROJECT_ROOT / 'household-expense'
if str(HOUSEHOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(HOUSEHOLD_ROOT))

passlib_module = types.ModuleType('passlib')
passlib_context_module = types.ModuleType('passlib.context')

class DummyCryptContext:
    def __init__(self, *args, **kwargs):
        pass

    def verify(self, *args, **kwargs):
        return True

passlib_context_module.CryptContext = DummyCryptContext
sys.modules.setdefault('passlib', passlib_module)
sys.modules.setdefault('passlib.context', passlib_context_module)

from api import db as household_db  # noqa: E402
from api.models import CategoryCreate, CategoryUpdate  # noqa: E402
from api.routers import categories  # noqa: E402


@pytest.fixture
def household_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'household.db'
    household_db.init_db(str(db_path))
    monkeypatch.setattr(categories, 'get_db', lambda: household_db.get_db(str(db_path)))
    return db_path


def test_create_category_inserts_new_active_category(household_temp_db):
    result = categories.create_category(CategoryCreate(code='fruit', label_id='Buah', sort_order=6))

    assert result['code'] == 'fruit'
    assert result['label_id'] == 'Buah'
    assert result['is_active'] == 1


def test_update_category_renames_code_and_repoints_transactions(household_temp_db):
    with household_db.get_db(str(household_temp_db)) as conn:
        conn.execute("INSERT INTO household_categories (code, label_id, sort_order, is_active) VALUES (?, ?, ?, 1)", ('groceries', 'Belanja Harian', 1))
        conn.execute(
            "INSERT INTO household_transactions (client_txn_id, created_at, updated_at, txn_datetime, amount, currency, category_code, merchant, description, payment_method, cash_pool_id, recorded_by, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('txn-1', '2026-04-21T07:00:00', '2026-04-21T07:00:00', '2026-04-21T07:00:00', 50000, 'IDR', 'groceries', '', 'Sayur', 'cash', None, 'tester', ''),
        )

    result = categories.update_category('groceries', CategoryUpdate(code='fresh-food', label_id='Bahan Segar', sort_order=2))

    assert result['code'] == 'fresh-food'
    with household_db.get_db(str(household_temp_db)) as conn:
        txn = conn.execute("SELECT category_code FROM household_transactions WHERE client_txn_id = ?", ('txn-1',)).fetchone()
    assert txn['category_code'] == 'fresh-food'


def test_delete_category_marks_it_inactive(household_temp_db):
    with household_db.get_db(str(household_temp_db)) as conn:
        conn.execute("INSERT INTO household_categories (code, label_id, sort_order, is_active) VALUES (?, ?, ?, 1)", ('snacks', 'Jajan', 3))

    result = categories.delete_category('snacks')

    assert result is None
    with household_db.get_db(str(household_temp_db)) as conn:
        row = conn.execute("SELECT is_active FROM household_categories WHERE code = ?", ('snacks',)).fetchone()
    assert row['is_active'] == 0
