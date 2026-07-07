from __future__ import annotations

import re

from ..const import DEFAULT_DEFAULT_COUNTRY_CODE

INTERNATIONAL_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def is_valid_international_phone(number: str | None) -> bool:
    """Return True when number is a normalized international +E.164 style value."""
    if not number:
        return False
    return bool(INTERNATIONAL_PHONE_RE.match(str(number).strip()))


def normalize_phone(number: str | None, default_country_code: str = DEFAULT_DEFAULT_COUNTRY_CODE) -> str:
    """Normalize common phone number formats to an international + format.

    This is intentionally conservative. It handles the common Polish formats used
    in the first test setup, but does not try to be a full phone number library.
    """
    if not number:
        return ""

    raw = str(number).strip()
    leading_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""

    if raw.startswith("00"):
        return f"+{digits[2:]}"
    if leading_plus:
        return f"+{digits}"
    if digits.startswith("48") and len(digits) == 11:
        return f"+{digits}"
    normalized_cc = re.sub(r"\D", "", str(default_country_code or ""))
    if normalized_cc.startswith("00"):
        normalized_cc = normalized_cc[2:]
    normalized_cc = normalized_cc or DEFAULT_DEFAULT_COUNTRY_CODE
    if len(digits) == 9:
        return f"+{normalized_cc}{digits}"
    return f"+{digits}"


def validate_phone_entry(number: str | None, default_country_code: str = DEFAULT_DEFAULT_COUNTRY_CODE) -> str | None:
    """Normalize a user-entered phone number or return None when invalid."""
    normalized = normalize_phone(number, default_country_code=default_country_code)
    if not normalized or not is_valid_international_phone(normalized):
        return None
    return normalized
