from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE, DOMAIN
from .modem import GsmModemClient, normalize_phone
from .util import modem_error


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GsmModemNotify(hass, entry, runtime["modem"])])


class GsmModemNotify(NotifyEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "sms"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, modem: GsmModemClient) -> None:
        self.hass = hass
        self._modem = modem
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "translation_key": "modem",
        }

    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> None:
        data = kwargs.get("data") or {}
        number = data.get("number") or kwargs.get("target")
        if isinstance(number, list):
            number = number[0] if number else None
        raw_cc = str(
            self._entry.options.get(
                CONF_DEFAULT_COUNTRY_CODE,
                self._entry.data.get(CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE),
            )
            or ""
        )
        digits = "".join(ch for ch in raw_cc if ch.isdigit())
        if digits.startswith("00"):
            digits = digits[2:]
        default_country_code = digits or DEFAULT_DEFAULT_COUNTRY_CODE
        number = normalize_phone(str(number or ""), default_country_code=default_country_code)
        if not number:
            raise modem_error("notify_missing_number")
        body = message if not title else f"{title}\n{message}"
        await self.hass.async_add_executor_job(self._modem.send_sms, number, body)
