from __future__ import annotations

from gsm_modem.modem.models import SmsMessage
from gsm_modem.parsers.multipart import merge_multipart_messages


def _udh_message(index: int, number: str, ref: int, part: int, total: int, text: str) -> SmsMessage:
    header = bytes([5, 0, 3, ref, total, part])
    body = header.decode("latin-1") + text
    return SmsMessage(index=index, status="REC UNREAD", number=number, date="01/01/24", text=body)


def test_merge_udh_parts() -> None:
    messages = [
        _udh_message(1, "+48123", 42, 1, 2, "Hel"),
        _udh_message(2, "+48123", 42, 2, 2, "lo"),
    ]
    merged = merge_multipart_messages(messages)
    assert len(merged) == 1
    assert merged[0].text == "Hello"
    assert merged[0].index == 1


def test_merge_text_parts() -> None:
    messages = [
        SmsMessage(1, "REC UNREAD", "+48123", "01/01/24", "(1/2)Hel"),
        SmsMessage(2, "REC UNREAD", "+48123", "01/01/24", "(2/2)lo"),
    ]
    merged = merge_multipart_messages(messages)
    assert len(merged) == 1
    assert merged[0].text == "Hello"
