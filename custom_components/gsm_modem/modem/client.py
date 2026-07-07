from __future__ import annotations

import logging
import time

from .at_engine import ATEngine
from .exceptions import ATCommandTimeout, ModemConnectionError, SmsSendError
from .models import ModemStatus, SmsMessage
from ..parsers.multipart import merge_multipart_messages
from ..parsers.basic import (
    first_payload,
    parse_cmgl,
    parse_cops,
    parse_cpin,
    parse_cpms_storage,
    parse_creg,
    parse_csq,
    parse_cusd,
)

_LOGGER = logging.getLogger(__name__)


class GsmModemClient:
    """High-level modem client used by Home Assistant.

    The client hides AT commands from entities and services. It keeps one serial
    connection open through ATEngine and exposes small, boring methods such as
    get_status(), send_sms() and list_sms().
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
        self.engine = ATEngine(
            port=port,
            baudrate=baudrate,
            command_timeout=command_timeout,
            sms_timeout=sms_timeout,
        )
        self._initialized = False

    def connect(self) -> None:
        self.engine.open()
        self.initialize()

    def close(self) -> None:
        self.engine.close()
        self._initialized = False

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def quick_test(self) -> None:
        self.engine.open()
        self.engine.command("AT", timeout=0.8)

    def initialize(self, *, force: bool = False) -> None:
        if self._initialized and not force:
            return
        self.engine.command("AT", timeout=0.5)
        self.engine.command("ATE0", timeout=0.5, allow_error=True)
        self.engine.command("AT+CMEE=2", timeout=0.5, allow_error=True)
        self.engine.command("AT+CMGF=1", timeout=0.5)
        self.engine.command('AT+CSCS="GSM"', timeout=0.5, allow_error=True)
        self.engine.command('AT+CPMS="SM","SM","SM"', timeout=0.8, allow_error=True)
        self._initialized = True


    def ping(self) -> bool:
        try:
            response = self.engine.command("AT", timeout=0.6, allow_error=True)
            return "OK" in response.lines
        except Exception:  # noqa: BLE001
            return False

    def get_status(self) -> ModemStatus:
        self.initialize()
        status = ModemStatus()

        status.sim_state = parse_cpin(self.engine.command("AT+CPIN?", timeout=1.0, allow_error=True).lines)
        status.signal_percent, status.signal_raw = parse_csq(self.engine.command("AT+CSQ", timeout=1.0).lines)
        status.operator = parse_cops(self.engine.command("AT+COPS?", timeout=1.2, allow_error=True).lines)
        status.registration, status.registration_raw = parse_creg(
            self.engine.command("AT+CREG?", timeout=1.0, allow_error=True).lines
        )
        status.manufacturer = first_payload(self.engine.command("AT+CGMI", timeout=1.0, allow_error=True).lines)
        status.model = first_payload(self.engine.command("AT+CGMM", timeout=1.0, allow_error=True).lines)
        imei = first_payload(self.engine.command("AT+CGSN", timeout=1.0, allow_error=True).lines)
        status.imei = imei.strip() if imei else None

        # Do not read REC UNREAD here. Some modems mark unread messages as read
        # immediately after CMGL, which would consume command SMS before the
        # coordinator command-processing pass.
        return status

    def send_sms(self, number: str, message: str) -> None:
        self.initialize()
        try:
            self.engine.send_sms(number, message)
        except (ATCommandTimeout, ModemConnectionError, SmsSendError):
            _LOGGER.debug("SMS send failed, reconnecting modem and retrying once", exc_info=True)
            self.reconnect()
            time.sleep(0.5)
            self.initialize(force=True)
            self.engine.send_sms(number, message)


    def send_ussd(self, code: str) -> str | None:
        """Send a USSD code and return the modem response when available.

        USSD is not as consistent as SMS. Some modems return the response in
        the command result, some return OK first and print +CUSD later, and some
        older devices dislike the DCS argument. We try the safest common path
        first and then fall back to a shorter command form.
        """
        self.initialize()
        self.engine.command("AT+CUSD=1", timeout=1.2, allow_error=True)

        try:
            response = self.engine.command(f'AT+CUSD=1,"{code}",15', timeout=6.0, allow_error=True)
            parsed = parse_cusd(response.lines)
            if parsed:
                return parsed
        except ATCommandTimeout:
            _LOGGER.debug("USSD primary command timed out, waiting for delayed +CUSD", exc_info=True)

        delayed = self.engine.read_unsolicited(("+CUSD:",), timeout=25.0)
        parsed = parse_cusd(delayed.lines)
        if parsed:
            return parsed

        # Some older ZTE/Huawei firmwares accept the USSD command without DCS.
        try:
            response = self.engine.command(f'AT+CUSD=1,"{code}"', timeout=6.0, allow_error=True)
            parsed = parse_cusd(response.lines)
            if parsed:
                return parsed
        except ATCommandTimeout:
            _LOGGER.debug("USSD fallback command timed out, waiting for delayed +CUSD", exc_info=True)

        delayed = self.engine.read_unsolicited(("+CUSD:",), timeout=25.0)
        return parse_cusd(delayed.lines)

    def enter_pin(self, pin: str) -> None:
        self.initialize()
        self.engine.command(f'AT+CPIN="{pin}"', timeout=5.0)

    def list_sms(self, box: str = "ALL") -> list[SmsMessage]:
        self.initialize()
        timeout = max(8.0, float(self.engine.command_timeout) * 4.0)
        try:
            response = self.engine.command(f'AT+CMGL="{box}"', timeout=timeout, allow_error=True)
        except (ATCommandTimeout, ModemConnectionError):
            _LOGGER.debug("SMS list failed, reconnecting modem and retrying once", exc_info=True)
            self.reconnect()
            time.sleep(0.5)
            self.initialize(force=True)
            response = self.engine.command(f'AT+CMGL="{box}"', timeout=timeout, allow_error=True)
        return merge_multipart_messages(parse_cmgl(response.lines))

    def _sms_storage_used(self) -> tuple[int, int]:
        response = self.engine.command("AT+CPMS?", timeout=2.0, allow_error=True)
        return parse_cpms_storage(response.lines)

    @staticmethod
    def _command_succeeded(response) -> bool:
        if any(line == "ERROR" or line.endswith(" ERROR") for line in response.lines):
            return False
        if "+CMS ERROR:" in response.raw or "+CME ERROR:" in response.raw:
            return False
        return "OK" in response.lines

    def delete_sms(self, index: int) -> None:
        self.initialize()
        self.engine.command(f"AT+CMGD={index}", timeout=2.0)

    def _delete_sms_allow_error(self, index: int) -> bool:
        response = self.engine.command(f"AT+CMGD={index}", timeout=2.0, allow_error=True)
        return self._command_succeeded(response)

    def delete_all_sms(self, box: str = "ALL") -> int:
        self.initialize()
        normalized_box = str(box or "ALL").strip().upper()
        initial_used, total = self._sms_storage_used()

        if normalized_box == "ALL":
            if initial_used <= 0:
                _LOGGER.debug("SMS storage already empty")
                return 0

            for bulk_cmd in ("AT+CMGD=1,4", "AT+CMGD=0,4"):
                try:
                    response = self.engine.command(bulk_cmd, timeout=10.0, allow_error=True)
                    if self._command_succeeded(response):
                        used_after, _ = self._sms_storage_used()
                        if used_after <= 0:
                            _LOGGER.info("Cleared SMS inbox with %s (%s messages)", bulk_cmd, initial_used)
                            return initial_used
                        _LOGGER.debug(
                            "Bulk delete %s left %s/%s messages, continuing cleanup",
                            bulk_cmd,
                            used_after,
                            total,
                        )
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("Bulk SMS delete failed for %s", bulk_cmd, exc_info=True)

            deleted = 0
            max_attempts = max(initial_used, total, 60) + 20
            for _ in range(max_attempts):
                used, _ = self._sms_storage_used()
                if used <= 0:
                    break
                if self._delete_sms_allow_error(1):
                    deleted += 1
                    continue
                if self._delete_sms_allow_error(used):
                    deleted += 1
                    continue
                _LOGGER.warning("SMS delete stalled with %s messages still on modem", used)
                break

            final_used, _ = self._sms_storage_used()
            if final_used > 0:
                _LOGGER.warning(
                    "SMS inbox cleanup incomplete: %s of %s messages remain",
                    final_used,
                    initial_used,
                )
            else:
                _LOGGER.info("Cleared SMS inbox after sequential delete (%s messages)", initial_used)
            return deleted

        bulk_modes = {
            "REC READ": ("AT+CMGD=1,1", "AT+CMGD=0,1"),
        }
        for bulk_cmd in bulk_modes.get(normalized_box, ()):
            try:
                response = self.engine.command(bulk_cmd, timeout=8.0, allow_error=True)
                if self._command_succeeded(response):
                    return initial_used
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Bulk SMS delete failed for %s", bulk_cmd, exc_info=True)

        try:
            messages = self.list_sms(normalized_box)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not list SMS for delete box %s", normalized_box, exc_info=True)
            return 0

        deleted = 0
        for message in sorted(
            (sms for sms in messages if sms.index is not None),
            key=lambda sms: int(sms.index),
            reverse=True,
        ):
            if self._delete_sms_allow_error(int(message.index)):
                deleted += 1
        return deleted

    def run_diagnostics(self) -> dict[str, object]:
        self.initialize(force=True)
        checks: dict[str, object] = {}

        def check(name: str, command: str, timeout: float = 1.0) -> None:
            try:
                response = self.engine.command(command, timeout=timeout, allow_error=True)
                checks[name] = {"ok": "OK" in response.lines, "response": response.lines}
            except Exception as err:  # noqa: BLE001 - diagnostics must report errors, not raise them
                checks[name] = {"ok": False, "error": str(err)}

        check("at", "AT", 0.5)
        check("sim", "AT+CPIN?", 1.0)
        check("signal", "AT+CSQ", 1.0)
        check("registration", "AT+CREG?", 1.0)
        check("operator", "AT+COPS?", 1.2)
        check("sms_text_mode", "AT+CMGF?", 1.0)
        check("sms_storage", "AT+CPMS?", 1.2)
        check("ussd", "AT+CUSD=1", 1.0)
        return checks
