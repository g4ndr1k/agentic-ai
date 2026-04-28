"""
Centralized CoreTax taxonomy and inference rules.
Maps PWM asset classes and source kinds to CoreTax kode_harta.
"""

# Mapping from PWM asset_class to CoreTax kode_harta
ASSET_CLASS_TO_KODE = {
    "bond": "034",
    "mutual_fund": "036",
    "stock": "039",
    "gold": "051",
}


def infer_kode_harta(source_kind: str, payload: dict) -> str:
    """
    Infer the most likely CoreTax kode_harta for a given PWM item.
    """
    if source_kind == "account_balance":
        return "012"

    if source_kind == "liability":
        return "liability"  # Standard placeholder for liabilities

    if source_kind == "holding":
        asset_class = payload.get("asset_class", "")
        return ASSET_CLASS_TO_KODE.get(asset_class, "")

    return ""


def is_liability(kode: str | None) -> bool:
    """Check if a kode_harta represents a liability."""
    if not kode:
        return False
    # Standard CoreTax liability codes usually start with '1' or are specifically labeled
    # For now, we use the placeholder 'liability' or check known ranges if needed.
    return kode.lower() == "liability" or kode.startswith("1")
