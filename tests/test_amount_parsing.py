import unittest

from parsers.base import parse_idr_amount
from parsers.maybank_cc import _parse_tx_rest


class AmountParsingTests(unittest.TestCase):
    def test_parse_idr_amount_handles_indonesian_dot_thousands(self):
        self.assertEqual(parse_idr_amount("147.857"), 147857.0)
        self.assertEqual(parse_idr_amount("1.572.426"), 1572426.0)
        self.assertEqual(parse_idr_amount("17.093"), 17093.0)

    def test_parse_idr_amount_preserves_decimal_forms(self):
        self.assertEqual(parse_idr_amount("8,65"), 8.65)
        self.assertEqual(parse_idr_amount("1.705,00"), 1705.0)
        self.assertEqual(parse_idr_amount("1234.56"), 1234.56)

    def test_maybank_foreign_row_uses_full_idr_amount(self):
        tx = _parse_tx_rest(
            "AMAZON DIGI* NG86J3O33 WWW.AMAZON.COUSD 8,65 147.857",
            "17/02/2026",
            "17/02/2026",
            "4047",
            17093,
            [],
            None,
        )
        self.assertIsNotNone(tx)
        self.assertEqual(tx.foreign_amount, 8.65)
        self.assertEqual(tx.exchange_rate, 17093)
        self.assertEqual(tx.amount_idr, 147857.0)


if __name__ == "__main__":
    unittest.main()
