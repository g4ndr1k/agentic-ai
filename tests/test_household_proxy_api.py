import json
import urllib.error

import pytest

import finance.api as finance_api
from fastapi import HTTPException


class DummyResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode('utf-8')


def test_household_request_sends_api_key_and_json(monkeypatch, tmp_path):
    key_file = tmp_path / 'household_api.key'
    key_file.write_text('test-key')
    captured = {}

    monkeypatch.setattr(finance_api, '_household_cfg', finance_api.HouseholdConfig(
        base_url='http://192.168.1.44:8088',
        api_key_file=str(key_file),
    ))

    def fake_urlopen(req, timeout):
        captured['url'] = req.full_url
        captured['timeout'] = timeout
        captured['method'] = req.get_method()
        captured['body'] = req.data.decode('utf-8')
        captured['api_key'] = req.headers['X-api-key']
        return DummyResponse({'ok': True})

    monkeypatch.setattr(finance_api.urllib.request, 'urlopen', fake_urlopen)

    result = finance_api._household_request('PUT', '/api/household/transactions/7', {'category_code': 'meals'})

    assert result == {'ok': True}
    assert captured == {
        'url': 'http://192.168.1.44:8088/api/household/transactions/7',
        'timeout': 15,
        'method': 'PUT',
        'body': '{"category_code": "meals"}',
        'api_key': 'test-key',
    }


def test_household_request_raises_bad_gateway_on_upstream_error(monkeypatch, tmp_path):
    key_file = tmp_path / 'household_api.key'
    key_file.write_text('test-key')

    monkeypatch.setattr(finance_api, '_household_cfg', finance_api.HouseholdConfig(
        base_url='http://192.168.1.44:8088',
        api_key_file=str(key_file),
    ))

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', hdrs=None, fp=None)

    monkeypatch.setattr(finance_api.urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(HTTPException) as exc:
        finance_api._household_request('GET', '/api/household/cash-pools')

    assert exc.value.status_code == 502
    assert 'Household API error 404' in exc.value.detail


def test_put_household_category_forwards_payload(monkeypatch):
    captured = {}

    def fake_request(method, path, body=None):
        captured['method'] = method
        captured['path'] = path
        captured['body'] = body
        return {'code': 'fruit', 'label_id': 'Buah'}

    monkeypatch.setattr(finance_api, '_household_request', fake_request)

    result = finance_api.put_household_category(
        finance_api.HouseholdCategoryUpsertRequest(code='fruit', label_id='Buah', sort_order=6)
    )

    assert result['code'] == 'fruit'
    assert captured == {
        'method': 'POST',
        'path': '/api/household/categories',
        'body': {'code': 'fruit', 'label_id': 'Buah', 'sort_order': 6},
    }


def test_delete_household_category_forwards_delete(monkeypatch):
    captured = {}

    def fake_request(method, path, body=None):
        captured['method'] = method
        captured['path'] = path
        captured['body'] = body
        return {'ok': True}

    monkeypatch.setattr(finance_api, '_household_request', fake_request)

    result = finance_api.delete_household_category('snacks')

    assert result == {'ok': True}
    assert captured == {
        'method': 'DELETE',
        'path': '/api/household/categories/snacks',
        'body': None,
    }
