from __future__ import annotations


class GsmModemError(Exception):
    """Base exception for GSM modem errors."""


class ModemConnectionError(GsmModemError):
    """Raised when the serial port cannot be opened or used."""


class ATCommandError(GsmModemError):
    """Raised when a modem returns ERROR for an AT command."""


class ATCommandTimeout(GsmModemError):
    """Raised when a modem does not answer in time."""


class SmsSendError(GsmModemError):
    """Raised when SMS sending fails."""
