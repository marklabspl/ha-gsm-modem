from __future__ import annotations

from gsm_modem.modem.sms_encoding import encode_ucs2_hex, needs_ucs2


def test_needs_ucs2_ascii() -> None:
    assert needs_ucs2("Hello 123") is False


def test_needs_ucs2_polish() -> None:
    assert needs_ucs2("Cześć") is True


def test_encode_ucs2_hex() -> None:
    assert encode_ucs2_hex("AB") == "00410042"
