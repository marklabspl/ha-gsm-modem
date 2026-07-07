from __future__ import annotations

from gsm_modem.modem.phone import is_valid_international_phone, normalize_phone, validate_phone_entry


def test_normalize_empty() -> None:
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""


def test_normalize_polish_nine_digits() -> None:
    assert normalize_phone("501234567") == "+48501234567"


def test_normalize_local_number_with_custom_country_code() -> None:
    assert normalize_phone("312345678", default_country_code="39") == "+39312345678"
    assert normalize_phone("312345678", default_country_code="+39") == "+39312345678"


def test_normalize_with_plus() -> None:
    assert normalize_phone("+48 501 234 567") == "+48501234567"


def test_normalize_international_prefix() -> None:
    assert normalize_phone("0048501234567") == "+48501234567"


def test_normalize_already_international() -> None:
    assert normalize_phone("48501234567") == "+48501234567"


def test_normalize_generic_digits() -> None:
    assert normalize_phone("12025550123") == "+12025550123"


def test_validate_phone_entry_accepts_international() -> None:
    assert validate_phone_entry("+48 501 234 567") == "+48501234567"
    assert validate_phone_entry("501234567", default_country_code="48") == "+48501234567"


def test_validate_phone_entry_rejects_invalid() -> None:
    assert validate_phone_entry("123") is None
    assert validate_phone_entry("abc") is None
    assert is_valid_international_phone("+123") is False
