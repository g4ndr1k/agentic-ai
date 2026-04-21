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
from api.models import CashPoolUpdate  # noqa: E402
from api.routers import cash_pools  # noqa: E402


@pytest.fixture
def household_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / 'household.db'
    household_db.init_db(str(db_path))
    monkeypatch.setattr(cash_pools, 'get_db', lambda: household_db.get_db(str(db_path)))
    return db_path


def test_update_cash_pool_applies_adjustment_amount(household_temp_db):
    with household_db.get_db(str(household_temp_db)) as conn:
        conn.execute(
            "INSERT INTO cash_pools (id, name, funded_amount, funded_at, remaining_amount, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('pool-1', 'Kas ART April', 1000000, '2026-04-15T00:00:00', 250000, 'active', ''),
        )

    result = cash_pools.update_cash_pool('pool-1', CashPoolUpdate(adjustment_amount=50000, notes='Tambah uang belanja'))

    assert result['remaining_amount'] == 300000
    assert result['notes'] == 'Tambah uang belanja'


def test_update_cash_pool_rejects_conflicting_amount_updates(household_temp_db):
    with household_db.get_db(str(household_temp_db)) as conn:
        conn.execute(
            "INSERT INTO cash_pools (id, name, funded_amount, funded_at, remaining_amount, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('pool-1', 'Kas ART April', 1000000, '2026-04-15T00:00:00', 250000, 'active', ''),
        )

    with pytest.raises(Exception) as exc:
        cash_pools.update_cash_pool('pool-1', CashPoolUpdate(remaining_amount=300000, adjustment_amount=50000))

    assert getattr(exc.value, 'status_code', None) == 400
