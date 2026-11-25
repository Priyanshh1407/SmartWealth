"""Merchant normalisation shared by business-purpose checks and reviewer memory."""

# Bank-export values that name no real counterparty. They never support a
# business purpose and must never be remembered as a merchant decision.
PURPOSE_PLACEHOLDERS = {
    '',
    'unknown',
    'misc chrg',
    'misc charge',
    'pos debit',
    'pos purchase',
    'n/a',
    'na',
    '???',
}


def merchant_key(merchant: str) -> str:
    """Case- and whitespace-insensitive key for matching the same merchant."""
    return ' '.join(str(merchant or '').split()).lower()


def is_memorable_merchant(merchant: str) -> bool:
    return merchant_key(merchant) not in PURPOSE_PLACEHOLDERS
