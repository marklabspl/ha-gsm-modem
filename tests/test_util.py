from __future__ import annotations

import json

from gsm_modem.modem.models import ModemStatus, SmsMessage
from gsm_modem.util import (
    command_set,
    command_text,
    diagnostics_report,
    event_suffix,
    health_from_status,
    messages_payload,
    parse_custom_command_reply_templates,
    prune_seen_indexes,
    resolve_custom_command_reply_template,
    status_reply,
)


def test_command_text_normalizes() -> None:
    assert command_text("  status  ") == "STATUS"
    assert command_text("status please") == "STATUS"
    assert command_text("STATUS?") == "STATUS"
    assert command_text("\n STATUS \nmore text") == "STATUS"
    assert command_text(None) == ""


def test_event_suffix() -> None:
    assert event_suffix("BRAMA") == "brama"
    assert event_suffix("GATE-1") == "gate_1"
    assert event_suffix("!!!") == "unknown"


def test_command_set_parses_lists() -> None:
    assert command_set("BRAMA, GATE\nGARAGE;ALARM") == {"BRAMA", "GATE", "GARAGE", "ALARM"}
    assert command_set("") == set()


def test_parse_custom_command_reply_templates() -> None:
    raw = """
    # brama
    BRAMA | Brama: {{ states('cover.brama') }}
    gate | Gate OK
    INVALID_LINE
    ALARM |
    """
    parsed = parse_custom_command_reply_templates(raw)
    assert parsed == {
        "BRAMA": "Brama: {{ states('cover.brama') }}",
        "GATE": "Gate OK",
    }


def test_resolve_custom_command_reply_template() -> None:
    per_command = {"BRAMA": "Brama OK"}
    default = "Default {{ command }}"
    assert resolve_custom_command_reply_template("BRAMA", per_command, default) == "Brama OK"
    assert resolve_custom_command_reply_template("GATE", per_command, default) == default
    assert resolve_custom_command_reply_template("brama", per_command, default) == "Brama OK"


def test_status_reply() -> None:
    status = ModemStatus(
        registration="Registered - home network",
        operator="Play",
        signal_percent=80,
        sim_state="READY",
    )
    reply = status_reply(status)
    assert "Modem: excellent" in reply
    assert "Registered - home network" in reply
    assert "Play" in reply
    assert "80%" in reply
    assert "READY" in reply


def test_command_reply_variables_sets_health() -> None:
    from gsm_modem.util import command_reply_variables

    status = ModemStatus(
        sim_state="READY",
        registration="Registered - home network",
        signal_percent=80,
    )
    variables = command_reply_variables(status)
    assert variables["health"] == "excellent"
    assert status.health == "excellent"


def test_messages_payload_limits_to_last_twenty() -> None:
    messages = [
        SmsMessage(index=i, status="REC READ", number="+48123", date=None, text=f"msg-{i}")
        for i in range(25)
    ]
    count, payload = messages_payload(messages)
    assert count == 25
    items = json.loads(payload)
    assert len(items) == 20
    assert items[0]["index"] == 5
    assert items[-1]["index"] == 24


def test_diagnostics_report_all_pass() -> None:
    ok, report = diagnostics_report({"at": {"ok": True}, "sim": {"ok": True}})
    assert ok is True
    assert "PASS - At" in report
    assert "PASS - Sim" in report


def test_diagnostics_report_with_error() -> None:
    ok, report = diagnostics_report({"signal": {"ok": False, "error": "timeout"}})
    assert ok is False
    assert "FAIL - Signal" in report
    assert "timeout" in report


def test_prune_seen_indexes() -> None:
    seen = {1, 2, 3, 99}
    prune_seen_indexes(seen, {2, 3, 4})
    assert seen == {2, 3}


def test_health_from_status() -> None:
    assert health_from_status(ModemStatus(last_error="boom")) == "problem"
    assert health_from_status(ModemStatus(sim_state="PIN")) == "sim_not_ready"
    excellent = ModemStatus(
        sim_state="READY",
        registration="Registered - home network",
        signal_percent=75,
    )
    assert health_from_status(excellent) == "excellent"
    weak = ModemStatus(
        sim_state="READY",
        registration="Registered - roaming",
        signal_percent=10,
    )
    assert health_from_status(weak) == "weak_signal"
    assert health_from_status(ModemStatus(sim_state="READY", registration="Not registered")) == "not_registered"
