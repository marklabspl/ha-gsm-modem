from __future__ import annotations

import re

from ..modem.phone import normalize_phone
from ..modem.models import SmsMessage

_SIM_STATE_STATE_KEYS = {
    "READY": "ready",
    "SIM PIN": "sim_pin",
    "SIM PUK": "sim_puk",
    "NOT INSERTED": "not_inserted",
}

_REGISTRATION_STATE_KEYS = {
    "Registered - home network": "home",
    "Registered - roaming": "roaming",
    "Not registered": "not_registered",
    "Searching": "searching",
    "Registration denied": "registration_denied",
    "Unknown": "unknown",
}


def _slugify_state(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "unknown"


def sim_state_entity_state(raw: str | None) -> str | None:
    """Map modem CPIN values to Home Assistant entity state keys."""
    if raw is None:
        return None
    key = raw.strip()
    return _SIM_STATE_STATE_KEYS.get(key, _slugify_state(key))


def registration_entity_state(raw: str | None) -> str | None:
    """Map modem registration labels to Home Assistant entity state keys."""
    if raw is None:
        return None
    key = raw.strip()
    return _REGISTRATION_STATE_KEYS.get(key, _slugify_state(key))


def first_payload(lines: list[str]) -> str | None:
    for line in lines:
        if line not in {"OK", "ERROR"} and not line.startswith("+"):
            return line.strip()
    return None


def parse_cpin(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("+CPIN:"):
            return line.split(":", 1)[1].strip()
    return None


def parse_csq(lines: list[str]) -> tuple[int | None, str | None]:
    for line in lines:
        if line.startswith("+CSQ:"):
            raw = line.split(":", 1)[1].strip()
            match = re.search(r"(\d+)\s*,", raw)
            if not match:
                return None, raw
            rssi = int(match.group(1))
            if rssi == 99:
                return None, raw
            return max(0, min(100, round(rssi / 31 * 100))), raw
    return None, None


def parse_cops(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("+COPS:"):
            match = re.search(r'"([^"]+)"', line)
            if match:
                return match.group(1)
            return line.split(":", 1)[1].strip()
    return None


def parse_creg(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        if not line.startswith("+CREG:"):
            continue
        raw = line.split(":", 1)[1].strip()
        parts = [part.strip().strip('"') for part in raw.split(",")]
        try:
            stat = int(parts[1] if len(parts) > 1 else parts[0])
        except (ValueError, IndexError):
            return raw, raw
        labels = {
            0: "Not registered",
            1: "Registered - home network",
            2: "Searching",
            3: "Registration denied",
            4: "Unknown",
            5: "Registered - roaming",
        }
        return labels.get(stat, raw), raw
    return None, None


def parse_cmgl(lines: list[str]) -> list[SmsMessage]:
    messages: list[SmsMessage] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+CMGL:"):
            header = line.split(":", 1)[1]
            idx_match = re.search(r"\+CMGL:\s*(\d+)", line)
            quoted = re.findall(r'"([^"]*)"', header)
            # Common text mode header:
            # +CMGL: 1,"REC READ","+48123",,"24/01/01,12:00:00+04"
            text = lines[i + 1].strip() if i + 1 < len(lines) else ""
            messages.append(
                SmsMessage(
                    index=int(idx_match.group(1)) if idx_match else None,
                    status=quoted[0] if len(quoted) > 0 else None,
                    number=normalize_phone(quoted[1]) if len(quoted) > 1 else None,
                    date=quoted[-1] if len(quoted) > 2 else None,
                    text=text,
                )
            )
            i += 2
            continue
        i += 1
    return messages


def parse_cusd(lines: list[str]) -> str | None:
    """Parse a basic +CUSD response.

    Most modems return something like:
    +CUSD: 0,"Your balance is ...",15
    """
    for line in lines:
        if not line.startswith("+CUSD:"):
            continue
        payload = line.split(":", 1)[1].strip()
        parts = []
        current = []
        in_quotes = False
        for char in payload:
            if char == '"':
                in_quotes = not in_quotes
                continue
            if char == "," and not in_quotes:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(char)
        parts.append("".join(current).strip())
        if len(parts) >= 2 and parts[1]:
            return parts[1]
        return payload
    return None


def parse_cpms_storage(lines: list[str]) -> tuple[int, int]:
    """Return (used, total) message slots for the first CPMS storage in the response."""
    for line in lines:
        if not line.startswith("+CPMS:"):
            continue
        match = re.search(r'\+CPMS:\s*(?:"[^"]*"\s*,\s*)?(\d+)\s*,\s*(\d+)', line)
        if match:
            return int(match.group(1)), int(match.group(2))
    return 0, 0
