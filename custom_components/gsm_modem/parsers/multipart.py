from __future__ import annotations

import re
from dataclasses import replace

from ..modem.models import SmsMessage

_PART_TEXT_RE = re.compile(r"^\((\d+)/(\d+)\)\s*(.*)$", re.DOTALL)


def _extract_udh(text: str | None) -> tuple[int, int, int, str] | None:
    if not text:
        return None
    try:
        data = text.encode("latin-1", errors="surrogateescape")
    except Exception:  # noqa: BLE001
        return None
    if len(data) < 6 or data[0] != 5 or data[1] != 0 or data[2] != 3:
        return None
    ref, total, part = data[3], data[4], data[5]
    if total < 1 or part < 1 or part > total:
        return None
    payload = data[6:].decode("latin-1", errors="ignore")
    return ref, total, part, payload


def merge_multipart_messages(messages: list[SmsMessage]) -> list[SmsMessage]:
    if len(messages) < 2:
        return messages

    part_indexes: set[int] = set()
    merged_messages: list[SmsMessage] = []
    udh_groups: dict[tuple[str, int], list[tuple[int, SmsMessage, str]]] = {}

    for message in messages:
        udh = _extract_udh(message.text)
        if udh and message.number is not None and message.index is not None:
            ref, _total, part, payload = udh
            udh_groups.setdefault((message.number, ref), []).append((part, message, payload))

    for group in udh_groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda item: item[0])
        first_msg = group[0][1]
        for _, msg, _ in group:
            part_indexes.add(int(msg.index))
        merged_messages.append(
            replace(first_msg, text="".join(payload for _, _, payload in group))
        )

    text_groups: dict[tuple[str, str, int], list[tuple[int, SmsMessage, str]]] = {}
    for message in messages:
        if message.index in part_indexes or not message.text or not message.number or message.index is None:
            continue
        match = _PART_TEXT_RE.match(message.text)
        if not match:
            continue
        part = int(match.group(1))
        total = int(match.group(2))
        payload = match.group(3)
        key = (message.number, message.date or "", total)
        text_groups.setdefault(key, []).append((part, message, payload))

    for group in text_groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda item: item[0])
        first_msg = group[0][1]
        for _, msg, _ in group:
            part_indexes.add(int(msg.index))
        merged_messages.append(
            replace(first_msg, text="".join(payload for _, _, payload in group))
        )

    if not part_indexes:
        return messages

    result = [message for message in messages if message.index not in part_indexes]
    result.extend(merged_messages)
    result.sort(key=lambda message: message.index or 0)
    return result
