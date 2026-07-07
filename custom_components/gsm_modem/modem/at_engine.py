from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import serial
from serial import SerialException

from .exceptions import ATCommandError, ATCommandTimeout, ModemConnectionError, SmsSendError
from .sms_encoding import encode_ucs2_hex, needs_ucs2

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ATResponse:
    command: str
    lines: list[str]
    raw: str


class ATEngine:
    """Small AT command engine with one persistent serial connection.

    The port is opened once and shared by all modem operations. A lock keeps AT
    commands serialized, which is important because classic modems only handle
    one command at a time.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        command_timeout: float = 0.9,
        sms_timeout: float = 35.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.command_timeout = command_timeout
        self.sms_timeout = sms_timeout
        self._serial: serial.Serial | None = None
        self._lock = threading.RLock()

    @property
    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def open(self) -> None:
        with self._lock:
            if self.is_open:
                return
            try:
                self._serial = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=0.04,
                    write_timeout=self.command_timeout,
                )
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
            except SerialException as err:
                raise ModemConnectionError(f"Cannot open serial port {self.port}: {err}") from err

    def close(self) -> None:
        with self._lock:
            if self._serial:
                self._serial.close()
                self._serial = None

    def _ensure_open(self) -> serial.Serial:
        if not self.is_open:
            self.open()
        assert self._serial is not None
        return self._serial

    def command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        allow_error: bool = False,
    ) -> ATResponse:
        """Send one AT command and wait for OK or ERROR."""
        with self._lock:
            ser = self._ensure_open()
            try:
                ser.reset_input_buffer()
                ser.write((command + "\r").encode("utf-8", errors="ignore"))
                ser.flush()
                raw = self._read_until_final(timeout or self.command_timeout)
            except SerialException as err:
                self.close()
                raise ModemConnectionError(str(err)) from err

            lines = self._clean_lines(raw, command)
            _LOGGER.debug("AT TX %s", command)
            _LOGGER.debug("AT RX %s", raw.strip())

            if any(line == "ERROR" or line.endswith(" ERROR") for line in lines):
                if allow_error:
                    return ATResponse(command=command, lines=lines, raw=raw)
                raise ATCommandError(f"{command} failed: {raw.strip()}")

            return ATResponse(command=command, lines=lines, raw=raw)


    def read_unsolicited(self, prefixes: tuple[str, ...], *, timeout: float) -> ATResponse:
        """Read unsolicited modem output until one of the prefixes is found.

        Some modems answer USSD commands in two steps: first they return OK,
        then they print +CUSD a few seconds later. This helper waits for that
        second line without sending another command.
        """
        with self._lock:
            ser = self._ensure_open()
            deadline = time.monotonic() + timeout
            buf = bytearray()
            while time.monotonic() < deadline:
                try:
                    chunk = ser.read(512)
                except SerialException as err:
                    self.close()
                    raise ModemConnectionError(str(err)) from err
                if chunk:
                    buf.extend(chunk)
                    text = buf.decode("utf-8", errors="ignore")
                    lines = self._clean_lines(text, "")
                    if any(any(line.startswith(prefix) for prefix in prefixes) for line in lines):
                        _LOGGER.debug("AT unsolicited RX %s", text.strip())
                        return ATResponse(command="<unsolicited>", lines=lines, raw=text)
                else:
                    time.sleep(0.02)
            text = buf.decode("utf-8", errors="ignore")
            return ATResponse(command="<unsolicited>", lines=self._clean_lines(text, ""), raw=text)

    def send_sms(self, number: str, message: str) -> None:
        """Send an SMS in text mode (GSM 7-bit or UCS2 for extended characters)."""
        if needs_ucs2(message):
            self.send_sms_ucs2(number, message)
            return
        with self._lock:
            ser = self._ensure_open()
            try:
                self.command("AT", timeout=0.5)
                self.command("AT+CMGF=1", timeout=0.5)
                self.command('AT+CSCS="GSM"', timeout=0.5, allow_error=True)

                ser.reset_input_buffer()
                ser.write((f'AT+CMGS="{number}"\r').encode("utf-8", errors="ignore"))
                ser.flush()
                prompt = self._read_until_prompt(2.5)
                if ">" not in prompt:
                    raise SmsSendError(f"Modem did not show SMS prompt: {prompt.strip()}")

                ser.write(message.encode("utf-8", errors="ignore") + bytes([26]))
                ser.flush()
                raw = self._read_until_final(self.sms_timeout)
                lines = self._clean_lines(raw, "")
                if any(line.startswith("+CMGS:") for line in lines) and "OK" in lines:
                    return
                if "ERROR" in raw:
                    raise SmsSendError(raw.strip())
                raise SmsSendError(f"Unexpected SMS response: {raw.strip()}")
            except SerialException as err:
                self.close()
                raise ModemConnectionError(str(err)) from err

    def send_sms_ucs2(self, number: str, message: str) -> None:
        """Send an SMS using UCS2 encoding for non-GSM characters."""
        with self._lock:
            ser = self._ensure_open()
            try:
                self.command("AT", timeout=0.5)
                self.command("AT+CMGF=1", timeout=0.5)
                self.command('AT+CSCS="UCS2"', timeout=0.5, allow_error=True)

                ser.reset_input_buffer()
                ser.write((f'AT+CMGS="{number}"\r').encode("utf-8", errors="ignore"))
                ser.flush()
                prompt = self._read_until_prompt(2.5)
                if ">" not in prompt:
                    raise SmsSendError(f"Modem did not show SMS prompt: {prompt.strip()}")

                payload = encode_ucs2_hex(message) + chr(26)
                ser.write(payload.encode("ascii"))
                ser.flush()
                raw = self._read_until_final(self.sms_timeout)
                lines = self._clean_lines(raw, "")
                if any(line.startswith("+CMGS:") for line in lines) and "OK" in lines:
                    return
                if "ERROR" in raw:
                    raise SmsSendError(raw.strip())
                raise SmsSendError(f"Unexpected SMS response: {raw.strip()}")
            except SerialException as err:
                self.close()
                raise ModemConnectionError(str(err)) from err

    def _read_until_final(self, timeout: float) -> str:
        ser = self._ensure_open()
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = ser.read(512)
            if chunk:
                buf.extend(chunk)
                text = buf.decode("utf-8", errors="ignore")
                normalized = text.replace("\r", "\n")
                lines = [line.strip() for line in normalized.split("\n") if line.strip()]
                if lines and lines[-1] == "OK":
                    return text
                if lines and (lines[-1] == "ERROR" or lines[-1].endswith(" ERROR")):
                    return text
                if "+CMS ERROR:" in text or "+CME ERROR:" in text:
                    return text
            else:
                time.sleep(0.01)
        text = buf.decode("utf-8", errors="ignore")
        raise ATCommandTimeout(f"Timeout waiting for modem response: {text.strip()}")

    def _read_until_prompt(self, timeout: float) -> str:
        ser = self._ensure_open()
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = ser.read(128)
            if chunk:
                buf.extend(chunk)
                text = buf.decode("utf-8", errors="ignore")
                if ">" in text:
                    return text
                if "ERROR" in text:
                    return text
            else:
                time.sleep(0.01)
        return buf.decode("utf-8", errors="ignore")

    @staticmethod
    def _clean_lines(raw: str, command: str) -> list[str]:
        lines = []
        for line in raw.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or line == command:
                continue
            lines.append(line)
        return lines
