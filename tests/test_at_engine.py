from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gsm_modem.modem.at_engine import ATEngine
from gsm_modem.modem.exceptions import ATCommandError, ATCommandTimeout


def test_clean_lines_normalizes_crlf() -> None:
    raw = "AT\r\nOK\r\n"
    lines = ATEngine._clean_lines(raw, "AT")
    assert lines == ["OK"]


def test_clean_lines_mixed_endings() -> None:
    raw = "+CSQ: 20,99\nOK\r"
    lines = ATEngine._clean_lines(raw, "")
    assert "+CSQ: 20,99" in lines
    assert "OK" in lines


def test_command_success() -> None:
    engine = ATEngine("/dev/null")
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.read.side_effect = [b"OK\r\n"]
    engine._serial = mock_serial

    response = engine.command("AT", timeout=1.0)
    assert "OK" in response.lines
    mock_serial.write.assert_called_with(b"AT\r")


def test_command_error_raises() -> None:
    engine = ATEngine("/dev/null")
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.read.side_effect = [b"ERROR\r\n"]
    engine._serial = mock_serial

    with pytest.raises(ATCommandError):
        engine.command("AT+INVALID", timeout=1.0)


def test_command_error_allowed() -> None:
    engine = ATEngine("/dev/null")
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.read.side_effect = [b"ERROR\r\n"]
    engine._serial = mock_serial

    response = engine.command("AT+CPIN?", timeout=1.0, allow_error=True)
    assert "ERROR" in response.lines


def test_read_until_final_timeout() -> None:
    engine = ATEngine("/dev/null")
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.read.return_value = b""
    engine._serial = mock_serial

    with patch("gsm_modem.modem.at_engine.time.monotonic") as monotonic:
        monotonic.side_effect = [0.0, 0.0, 2.0]
        with pytest.raises(ATCommandTimeout):
            engine._read_until_final(1.0)
