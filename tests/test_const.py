from __future__ import annotations

from gsm_modem.const import normalize_sms_box


def test_normalize_sms_box_maps_selector_values() -> None:
    assert normalize_sms_box("all") == "ALL"
    assert normalize_sms_box("rec_unread") == "REC UNREAD"
    assert normalize_sms_box("rec_read") == "REC READ"


def test_normalize_sms_box_accepts_legacy_modem_values() -> None:
    assert normalize_sms_box("ALL") == "ALL"
    assert normalize_sms_box("REC UNREAD") == "REC UNREAD"
    assert normalize_sms_box("REC READ") == "REC READ"


def test_normalize_sms_box_defaults_to_all() -> None:
    assert normalize_sms_box(None) == "ALL"
    assert normalize_sms_box("") == "ALL"
    assert normalize_sms_box("unknown") == "ALL"
