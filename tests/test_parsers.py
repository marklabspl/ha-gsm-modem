from __future__ import annotations

from gsm_modem.modem.models import SmsMessage
from gsm_modem.parsers.basic import (
    first_payload,
    parse_cmgl,
    parse_cops,
    parse_cpin,
    parse_cpms_storage,
    parse_creg,
    parse_csq,
    parse_cusd,
    registration_entity_state,
    sim_state_entity_state,
)


def test_first_payload_skips_ok_and_urc() -> None:
    lines = ["+CPIN: READY", "ZTE", "OK"]
    assert first_payload(lines) == "ZTE"


def test_parse_cpin() -> None:
    assert parse_cpin(["+CPIN: READY", "OK"]) == "READY"


def test_sim_state_entity_state() -> None:
    assert sim_state_entity_state("READY") == "ready"
    assert sim_state_entity_state("SIM PIN") == "sim_pin"
    assert sim_state_entity_state("PH-SIM PIN") == "ph_sim_pin"


def test_registration_entity_state() -> None:
    assert registration_entity_state("Registered - home network") == "home"
    assert registration_entity_state("Not registered") == "not_registered"


def test_parse_cpms_storage_compact() -> None:
    used, total = parse_cpms_storage(["+CPMS: 50,50,50,50,50,50", "OK"])
    assert used == 50
    assert total == 50


def test_parse_cpms_storage_quoted() -> None:
    used, total = parse_cpms_storage(['+CPMS: "SM",12,50', "OK"])
    assert used == 12
    assert total == 50


def test_parse_csq_good_signal() -> None:
    percent, raw = parse_csq(["+CSQ: 20,99", "OK"])
    assert percent == 65
    assert raw == "20,99"


def test_parse_csq_unknown() -> None:
    percent, raw = parse_csq(["+CSQ: 99,99", "OK"])
    assert percent is None
    assert raw == "99,99"


def test_parse_cops_quoted() -> None:
    assert parse_cops(['+COPS: 0,0,"Play",2', "OK"]) == "Play"


def test_parse_creg_home() -> None:
    label, raw = parse_creg(["+CREG: 0,1", "OK"])
    assert label == "Registered - home network"
    assert raw == "0,1"


def test_parse_creg_roaming() -> None:
    label, _ = parse_creg(["+CREG: 0,5", "OK"])
    assert label == "Registered - roaming"


def test_parse_cmgl_single_message() -> None:
    lines = [
        '+CMGL: 3,"REC UNREAD","+48501234567",,"24/01/01,12:00:00+04"',
        "Hello world",
        "OK",
    ]
    messages = parse_cmgl(lines)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.index == 3
    assert msg.status == "REC UNREAD"
    assert msg.number == "+48501234567"
    assert msg.text == "Hello world"


def test_parse_cmgl_multiple_messages() -> None:
    lines = [
        '+CMGL: 1,"REC READ","+48111",,"24/01/01,10:00:00+04"',
        "First",
        '+CMGL: 2,"REC UNREAD","+48222",,"24/01/01,11:00:00+04"',
        "Second",
        "OK",
    ]
    messages = parse_cmgl(lines)
    assert len(messages) == 2
    assert messages[0].text == "First"
    assert messages[1].text == "Second"


def test_parse_cusd_quoted() -> None:
    lines = ['+CUSD: 0,"Saldo: 10 PLN",15', "OK"]
    assert parse_cusd(lines) == "Saldo: 10 PLN"


def test_parse_cusd_without_quotes() -> None:
    lines = ["+CUSD: 2", "OK"]
    assert parse_cusd(lines) == "2"


def test_sms_message_as_dict() -> None:
    msg = SmsMessage(index=1, status="REC READ", number="+48123", date="01/01/24", text="Hi")
    assert msg.as_dict() == {
        "index": 1,
        "status": "REC READ",
        "number": "+48123",
        "date": "01/01/24",
        "text": "Hi",
    }
