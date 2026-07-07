from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SmsMessage:
    index: int | None
    status: str | None
    number: str | None
    date: str | None
    text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "status": self.status,
            "number": self.number,
            "date": self.date,
            "text": self.text,
        }


@dataclass(slots=True)
class ModemStatus:
    sim_state: str | None = None
    signal_percent: int | None = None
    signal_raw: str | None = None
    operator: str | None = None
    registration: str | None = None
    registration_raw: str | None = None
    imei: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    sms_unread: int | None = None
    last_sms_text: str | None = None
    last_sms_number: str | None = None
    last_sms_index: int | None = None
    last_sms_authorized: bool | None = None
    last_sms_command: str | None = None
    last_command_handled: bool | None = None
    last_command_action: str | None = None
    last_command_reply_sent: bool | None = None
    last_command_reply_error: str | None = None
    last_ussd_response: str | None = None
    inbox_count: int | None = None
    inbox_json: str | None = None
    diagnostics_report: str | None = None
    diagnostics_ok: bool | None = None
    health: str | None = None
    last_error: str | None = None
    reconnect_count: int = 0
    last_outgoing_number: str | None = None
    last_outgoing_segments: int | None = None
    sent_count: int = 0
    send_fail_count: int = 0
