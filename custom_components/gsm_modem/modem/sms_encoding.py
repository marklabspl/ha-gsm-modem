from __future__ import annotations

_GSM7_EXTRA = set(" @£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_POLISH_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


def needs_ucs2(message: str) -> bool:
    for char in message:
        if char in _POLISH_CHARS or char not in _GSM7_EXTRA:
            return True
    return False


def encode_ucs2_hex(message: str) -> str:
    return message.encode("utf-16-be").hex().upper()
