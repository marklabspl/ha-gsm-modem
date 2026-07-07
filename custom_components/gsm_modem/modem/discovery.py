from __future__ import annotations

import glob
import logging

from .client import GsmModemClient

_LOGGER = logging.getLogger(__name__)


def candidate_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))


def probe_port(port: str, baudrate: int = 115200, *, command_timeout: float = 0.8) -> bool:
    modem = GsmModemClient(port, baudrate, command_timeout=command_timeout)
    try:
        modem.quick_test()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            modem.close()
        except Exception:  # noqa: BLE001
            pass


def discover_modem_ports(baudrate: int = 115200, *, command_timeout: float = 0.8) -> list[str]:
    working: list[str] = []
    for port in candidate_ports():
        if probe_port(port, baudrate, command_timeout=command_timeout):
            working.append(port)
            _LOGGER.debug("GSM modem responded on %s", port)
    return working
