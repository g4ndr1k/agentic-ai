import pytest
from finance.coretax.utils import extract_account_number, extract_isin, normalize_account_number

@pytest.mark.parametrize("value,expected", [
    ("123-456", "123456"),
    ("123 456 7", "1234567"),
    ("ABC-123", "abc123"),
    (None, None),
    ("", ""),
])
def test_normalize_account_number(value, expected):
    assert normalize_account_number(value) == expected

@pytest.mark.parametrize("text,expected", [
    ("rek 123456", "123456"),
    ("rekening 789012", "789012"),
    ("no rek 345678", "345678"),
    ("no. rekening 901234", "901234"),
    ("acct 567890", "567890"),
    ("account 123789", "123789"),
    ("rekening: 123456", "123456"),
    ("No Rek: 654321", "654321"),
    ("rek. 112233", "112233"),
    ("BCA rek 554433-2", "5544332"),
    ("Mandiri no. rek. 998877", "998877"),
    ("Tabungan rek 0011223344 a/n John", "0011223344"),
    ("acct: ABC123XYZ", "abc123xyz"),
    ("rek 12", None), # Too short
    ("no prefix 123456", None),
    ("", None),
    (None, None),
])
def test_extract_account_number(text, expected):
    assert extract_account_number(text) == expected

@pytest.mark.parametrize("text,expected", [
    ("ISIN ID1234567890", "ID1234567890"),
    ("isin: id0987654321", "ID0987654321"),
    ("US0378331005", "US0378331005"),
    ("abc ID1234567890 xyz", "ID1234567890"),
    ("ID123", None), # Too short
    ("", None),
    (None, None),
])
def test_extract_isin(text, expected):
    assert extract_isin(text) == expected
