import sys
import types
import unittest

sys.modules.setdefault("pdfplumber", types.SimpleNamespace(open=None))

from parsers.bca_savings import _parse_transactions


class BcaSavingsParserTests(unittest.TestCase):
    def test_ftfva_tanggal_followed_by_blank_lines_salvages_binus_description(self):
        page_text = "\n".join([
            "05/03 TRSF E-BANKING DB",
            "",
            "0403/FTFVA/WS95031",
            "",
            "TANGGAL :04/03",
            "",
            "71201/BINUS S SIMP",
            "",
            "55,200,000.00 DB",
            "",
            "1370000195",
            "",
            "05/03 KARTU KREDIT/PL 0304 WSID950310042 1,791,583.00 DB",
        ])

        txns = _parse_transactions(
            [page_text],
            account_number="2171138631",
            year="2026",
            month="03",
            errors=[],
        )

        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].amount_idr, 55200000.0)
        self.assertIn("BINUS S SIMP", txns[0].description)
        self.assertIn("0403/FTFVA/WS95031", txns[0].description)


if __name__ == "__main__":
    unittest.main()
