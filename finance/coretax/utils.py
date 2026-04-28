import re


def normalize_account_number(value: str | None) -> str | None:
    """
    Normalize account number: lowercase and remove all non-alphanumeric characters.
    """
    if value is None:
        return None
    return re.sub(r"[^a-z0-9]", "", value.lower())


def extract_account_number(text: str | None) -> str | None:
    """
    Extract account number from text using various Indonesian banking patterns.
    Supports: 'rek', 'rekening', 'no rek', 'no. rekening', 'acct', etc.
    Returns normalized numeric-like string or None.
    """
    if not text:
        return None

    # 1. Normalize: lowercase for matching prefixes
    t_lower = text.lower()

    # 2. Match patterns
    prefixes = [
        r"no\.?\s*rekening",
        r"rekening",
        r"no\.?\s*rek",
        r"rek",
        r"acct",
        r"account",
    ]

    for p in prefixes:
        # Match prefix followed by optional dot, then optional colon/space, then the account number
        # We use \b to ensure we don't match prefixes inside other words
        pattern = rf"\b{p}\.?[:\s]+([a-zA-Z0-9\-\.\s]+)"
        m = re.search(pattern, t_lower)
        if m:
            start, end = m.span(1)
            original_val = text[start:end].strip()

            # Simple approach: take first block of alphanumeric/dash/dot
            match_block = re.match(r"([a-zA-Z0-9\-\.]+)", original_val)
            if match_block:
                candidate = match_block.group(1)
                # If it's too short (e.g. 1-2 chars), it might be noise, skip
                if len(candidate) >= 3:
                    return normalize_account_number(candidate)

    return None


def extract_isin(text: str | None) -> str | None:
    """
    Extract ISIN from text.
    ISIN format: 2 letters + 10 alphanumeric chars.
    """
    if not text:
        return None
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{10})\b", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None
