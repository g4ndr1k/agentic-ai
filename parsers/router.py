"""
Parser router: auto-detects bank and statement type from first-page text,
then dispatches to the correct parser.

Detection priority:
  1. Permata CC      — "Rekening Tagihan" + "Credit Card Billing"  (page 1 bilingual title)
  2. Permata RDN     — "Permata" + "Rekening Koran" + word-boundary "RDN"  (page 1)
  3. Permata USD Sav — "Mutasi Transaksi" + product name (page 1)
  4. Permata Savings — "Permata" + "Rekening Koran"  (page 1; fallback for non-RDN accounts)
  5. BCA CC          — "BCA"/"Bank Central Asia" + "REKENING KARTU KREDIT"  (page 1)
  6. BCA RDN         — "REKENING TAPRES"  (page 1; BCA's securities RDN product)
  7. BCA Savings     — "BCA"/"Bank Central Asia" + "TAHAPAN"  (page 1, case-insensitive)
  8. Maybank Consol  — "Maybank" + "PORTFOLIO"  (page 1+2 combined; checked before CC)
  9. Maybank CC      — "maybank" + "kartu kredit"  (page 1, case-insensitive)
 10. CIMB Niaga CC   — "CIMB Niaga" + "Tgl. Statement"  (page 1+2 combined)
 11. CIMB Niaga Consol — "CIMB Niaga" + "COMBINE STATEMENT"  (page 1)
 12. IPOT Portfolio  — "PT INDO PREMIER SEKURITAS" + "Client Portofolio"  (page 1)
 13. IPOT Statement  — "PT INDO PREMIER SEKURITAS" + "Client Statement"  (page 1)
 14. BNI Sekuritas (legacy) — "CONSOLIDATE ACCOUNT STATEMENT" + "CASH SUMMARY"  (page 1)
 15. BNI Sekuritas   — "BNI Sekuritas" + "CLIENT STATEMENT"  (page 1, all-caps)
 16. Stockbit        — "PT. STOCKBIT SEKURITAS DIGITAL" + "Statement of Account"  (page 1)

Engine integration (Phase B):
  When PARSER_USE_ENGINE=true and a DB connection is supplied, the router
  attempts a Tier-1 mapping lookup via the matching engine before running
  can_parse() calls. On a Tier-1 hit the PDF is routed in O(1) without any
  can_parse() execution. On a miss the legacy cascade runs as Tier-2 and its
  result is auto-persisted for future lookups.
"""
import os

import pdfplumber

from .base import StatementResult
from . import (
    maybank_cc, maybank_consol,
    bca_cc, bca_savings, bca_rdn,
    permata_cc, permata_savings, permata_rdn, permata_usd_savings,
    cimb_niaga_cc, cimb_niaga_consol,
    ipot_portfolio, ipot_statement,
    bni_sekuritas_legacy,
    bni_sekuritas,
    stockbit_sekuritas,
)

PARSER_USE_ENGINE = os.environ.get("PARSER_USE_ENGINE", "false").lower() == "true"


# ── Parser name → parse() callable ───────────────────────────────────────────
# Kept as a function so the import graph stays lazy; called only when needed.

def _get_parse_fn(parser_name: str, pdf_path: str, ollama_client, owner_mappings: dict):
    """Return the result of calling the named parser's parse() function."""
    dispatch = {
        "permata_cc":          lambda: permata_cc.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "permata_rdn":         lambda: permata_rdn.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "permata_usd_savings": lambda: permata_usd_savings.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "permata_savings":     lambda: permata_savings.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "bca_cc":              lambda: bca_cc.parse(pdf_path, ollama_client),
        "bca_rdn":             lambda: bca_rdn.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "bca_savings":         lambda: bca_savings.parse(pdf_path, ollama_client),
        "maybank_consol":      lambda: maybank_consol.parse(pdf_path, ollama_client),
        "maybank_cc":          lambda: maybank_cc.parse(pdf_path, ollama_client),
        "cimb_niaga_cc":       lambda: cimb_niaga_cc.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "cimb_niaga_consol":   lambda: cimb_niaga_consol.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "ipot_portfolio":      lambda: ipot_portfolio.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "ipot_statement":      lambda: ipot_statement.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "bni_sekuritas_legacy":lambda: bni_sekuritas_legacy.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "bni_sekuritas":       lambda: bni_sekuritas.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
        "stockbit_sekuritas":  lambda: stockbit_sekuritas.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client),
    }
    fn = dispatch.get(parser_name)
    if fn is None:
        raise UnknownStatementError(f"Unknown parser name from engine: {parser_name!r}")
    return fn()


class UnknownStatementError(Exception):
    pass


def detect_and_parse(pdf_path: str, ollama_client=None,
                     owner_mappings: dict | None = None,
                     conn=None) -> StatementResult:
    """Open the PDF, read the first page, route to correct parser.

    When PARSER_USE_ENGINE=true and conn is supplied, attempts a Tier-1
    mapping lookup before running the full can_parse() cascade.
    """
    if owner_mappings is None:
        owner_mappings = {}

    with pdfplumber.open(pdf_path) as pdf:
        page1_text = pdf.pages[0].extract_text() or ""
        page2_text = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""
        combined = page1_text + "\n" + page2_text
        meta = pdf.metadata or {}

    # ── Engine path (Phase B) ────────────────────────────────────────────────
    if PARSER_USE_ENGINE and conn is not None:
        from finance.matching.engine import classify, reset_run_state
        from finance.matching.domains.parser_routing import domain as parser_domain

        source_row = {
            "page1_text": page1_text,
            "page2_text": page2_text,
            "producer": meta.get("Producer", ""),
            "creator": meta.get("Creator", ""),
        }
        match = classify(parser_domain, conn, source_row, run_id=f"pdf:{os.path.basename(pdf_path)}")
        if match is not None:
            return _get_parse_fn(match.target, pdf_path, ollama_client, owner_mappings)
        # Fall through to legacy path so UnknownStatementError is raised with
        # full diagnostic info (partial can_parse signals) — better than the
        # engine silently returning None.

    # ── Legacy path (always-correct fallback) ────────────────────────────────
    if permata_cc.can_parse(page1_text):
        return permata_cc.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if permata_rdn.can_parse(page1_text):
        return permata_rdn.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if permata_usd_savings.can_parse(page1_text):
        return permata_usd_savings.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if permata_savings.can_parse(page1_text):
        return permata_savings.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    # BCA detection
    if bca_cc.can_parse(page1_text):
        return bca_cc.parse(pdf_path, ollama_client)

    if bca_rdn.can_parse(page1_text):
        return bca_rdn.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if bca_savings.can_parse(page1_text):
        return bca_savings.parse(pdf_path, ollama_client)

    # Maybank consolidated MUST be checked before Maybank CC:
    # the consolidated PDF lists "Maybank Kartu Kredit" as a product on page 1,
    # which would falsely trigger the CC detector.
    if maybank_consol.can_parse(combined):
        return maybank_consol.parse(pdf_path, ollama_client)

    if maybank_cc.can_parse(page1_text):
        return maybank_cc.parse(pdf_path, ollama_client)

    # CIMB Niaga: use combined (p1+p2) for CC — on 2-page statements "CIMB Niaga"
    # only appears in the Poin Xtra footer on page 2.
    if cimb_niaga_cc.can_parse(combined):
        return cimb_niaga_cc.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if cimb_niaga_consol.can_parse(page1_text):
        return cimb_niaga_consol.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    # IPOT: portfolio before statement (both share "PT INDO PREMIER SEKURITAS")
    if ipot_portfolio.can_parse(page1_text):
        return ipot_portfolio.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if ipot_statement.can_parse(page1_text):
        return ipot_statement.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if bni_sekuritas_legacy.can_parse(page1_text):
        return bni_sekuritas_legacy.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if bni_sekuritas.can_parse(page1_text):
        return bni_sekuritas.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    if stockbit_sekuritas.can_parse(page1_text):
        return stockbit_sekuritas.parse(pdf_path, owner_mappings=owner_mappings, ollama_client=ollama_client)

    _partial = _collect_partial_signals(page1_text, combined)
    raise UnknownStatementError(
        f"Could not identify statement type from PDF: {pdf_path}\n"
        f"Partial can_parse signals: {_partial or 'none'}\n"
        f"First-page preview: {page1_text[:300]}"
    )


def _collect_partial_signals(page1_text: str, combined: str) -> list[str]:
    """Collect all can_parse() signals that are partially satisfied.

    Returns list of parser names where can_parse() returned True — useful for
    ambiguity debugging and for Phase B.9 ambiguity-chooser UI.
    """
    signals = []
    checks = [
        ("permata_cc", permata_cc, page1_text),
        ("permata_rdn", permata_rdn, page1_text),
        ("permata_usd_savings", permata_usd_savings, page1_text),
        ("permata_savings", permata_savings, page1_text),
        ("bca_cc", bca_cc, page1_text),
        ("bca_rdn", bca_rdn, page1_text),
        ("bca_savings", bca_savings, page1_text),
        ("maybank_consol", maybank_consol, combined),
        ("maybank_cc", maybank_cc, page1_text),
        ("cimb_niaga_cc", cimb_niaga_cc, combined),
        ("cimb_niaga_consol", cimb_niaga_consol, page1_text),
        ("ipot_portfolio", ipot_portfolio, page1_text),
        ("ipot_statement", ipot_statement, page1_text),
        ("bni_sekuritas_legacy", bni_sekuritas_legacy, page1_text),
        ("bni_sekuritas", bni_sekuritas, page1_text),
        ("stockbit_sekuritas", stockbit_sekuritas, page1_text),
    ]
    for name, module, text in checks:
        try:
            if module.can_parse(text):
                signals.append(name)
        except Exception:
            pass
    return signals


def detect_bank_and_type(pdf_path: str) -> tuple[str, str]:
    """Lightweight detection — returns (bank, type) without full parsing."""
    with pdfplumber.open(pdf_path) as pdf:
        page1_text = pdf.pages[0].extract_text() or ""
        page2_text = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""
        combined = page1_text + "\n" + page2_text

    if permata_cc.can_parse(page1_text):
        return "Permata", "cc"
    if permata_rdn.can_parse(page1_text):
        return "Permata", "rdn"
    if permata_usd_savings.can_parse(page1_text):
        return "Permata", "savings"
    if permata_savings.can_parse(page1_text):
        return "Permata", "savings"
    if bca_cc.can_parse(page1_text):
        return "BCA", "cc"
    if bca_rdn.can_parse(page1_text):
        return "BCA", "rdn"
    if bca_savings.can_parse(page1_text):
        return "BCA", "savings"
    if maybank_consol.can_parse(combined):
        return "Maybank", "consolidated"
    if maybank_cc.can_parse(page1_text):
        return "Maybank", "cc"
    if cimb_niaga_cc.can_parse(combined):
        return "CIMB Niaga", "cc"
    if cimb_niaga_consol.can_parse(page1_text):
        return "CIMB Niaga", "consol"
    if ipot_portfolio.can_parse(page1_text):
        return "IPOT", "portfolio"
    if ipot_statement.can_parse(page1_text):
        return "IPOT", "statement"
    if bni_sekuritas_legacy.can_parse(page1_text):
        return "BNI Sekuritas", "portfolio"
    if bni_sekuritas.can_parse(page1_text):
        return "BNI Sekuritas", "portfolio"
    if stockbit_sekuritas.can_parse(page1_text):
        return "Stockbit Sekuritas", "portfolio"
    return "Unknown", "unknown"
