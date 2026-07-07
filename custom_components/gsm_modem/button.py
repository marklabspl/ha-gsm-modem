from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ALLOWED_NUMBERS,
    CONF_BALANCE_USSD_CODE,
    CONF_DEFAULT_COUNTRY_CODE,
    CONF_TEST_SMS_MESSAGE,
    CONF_TEST_SMS_NUMBER,
    DEFAULT_DEFAULT_COUNTRY_CODE,
    DOMAIN,
    EVENT_DIAGNOSTICS,
    EVENT_SMS_LIST,
    EVENT_USSD_RESPONSE,
    EVENT_TEST_SMS_SENT,
)
from .modem import GsmModemClient, normalize_phone
from .modem.exceptions import ATCommandTimeout, GsmModemError
from .util import diagnostics_report, modem_error


def _entry_country_code(entry: ConfigEntry) -> str:
    raw = str(entry.options.get(CONF_DEFAULT_COUNTRY_CODE, entry.data.get(CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE)) or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    return digits or DEFAULT_DEFAULT_COUNTRY_CODE


@dataclass(frozen=True)
class ButtonDescription:
    key: str
    action: str


BUTTONS = [
    ButtonDescription("send_test_sms", "send_test_sms"),
    ButtonDescription("check_balance", "check_balance"),
    ButtonDescription("clear_all_sms", "clear_all_sms"),
    ButtonDescription("read_unread_sms", "read_unread_sms"),
    ButtonDescription("read_all_sms", "read_all_sms"),
    ButtonDescription("refresh_status", "refresh_status"),
    ButtonDescription("run_diagnostics", "diagnostics"),
    ButtonDescription("reconnect", "reconnect"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    async_add_entities([GsmButton(hass, coordinator, entry, desc) for desc in BUTTONS])


class GsmButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, hass: HomeAssistant, coordinator, entry: ConfigEntry, description: ButtonDescription) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_translation_key = description.key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "translation_key": "modem",
        }

    async def async_press(self) -> None:
        runtime = self.hass.data[DOMAIN][self.entry.entry_id]
        modem: GsmModemClient = runtime["modem"]

        try:
            await self._async_run_action(modem)
        except HomeAssistantError:
            raise
        except ATCommandTimeout as err:
            raise modem_error("command_timeout", detail=str(err)) from err
        except GsmModemError as err:
            raise modem_error("modem_communication_error", detail=str(err)) from err

    async def _async_run_action(self, modem: GsmModemClient) -> None:
        if self.description.action == "send_test_sms":
            default_country_code = _entry_country_code(self.entry)
            number = self.entry.options.get(CONF_TEST_SMS_NUMBER, self.entry.data.get(CONF_TEST_SMS_NUMBER, ""))
            number = normalize_phone(number, default_country_code=default_country_code) or ""
            if not number:
                allowed = self.entry.options.get(CONF_ALLOWED_NUMBERS, self.entry.data.get(CONF_ALLOWED_NUMBERS, [])) or []
                if allowed:
                    number = normalize_phone(allowed[0], default_country_code=default_country_code) or ""
            if not number:
                raise modem_error("no_test_sms_number")
            message = self.entry.options.get(
                CONF_TEST_SMS_MESSAGE,
                self.entry.data.get(CONF_TEST_SMS_MESSAGE, "Test from Home Assistant"),
            )
            await self.hass.async_add_executor_job(modem.send_sms, number, message)
            self.hass.bus.async_fire(EVENT_TEST_SMS_SENT, {"number": number, "message": message})
            return


        if self.description.action == "check_balance":
            code = self.entry.options.get(CONF_BALANCE_USSD_CODE, self.entry.data.get(CONF_BALANCE_USSD_CODE, "*101#"))
            response = await self.hass.async_add_executor_job(modem.send_ussd, code)
            if not response:
                response = "No USSD response received from the modem."
            if self.coordinator.data is not None:
                self.coordinator.data.last_ussd_response = response
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.hass.bus.async_fire(EVENT_USSD_RESPONSE, {"code": code, "response": response})
            return

        if self.description.action == "read_unread_sms":
            messages = await self.hass.async_add_executor_job(modem.list_sms, "REC UNREAD")
            self.hass.bus.async_fire(EVENT_SMS_LIST, {"messages": [message.as_dict() for message in messages]})
            await self.coordinator.async_request_refresh()
            return

        if self.description.action == "read_all_sms":
            messages = await self.hass.async_add_executor_job(modem.list_sms, "ALL")
            if self.coordinator.data is not None:
                import json
                self.coordinator.data.inbox_count = len(messages)
                self.coordinator.data.inbox_json = json.dumps([message.as_dict() for message in messages[-20:]], ensure_ascii=False)
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.hass.bus.async_fire(EVENT_SMS_LIST, {"messages": [message.as_dict() for message in messages]})
            return

        if self.description.action == "clear_all_sms":
            await self.hass.async_add_executor_job(modem.delete_all_sms, "ALL")
            await self.coordinator.async_request_refresh()
            return

        if self.description.action == "refresh_status":
            await self.coordinator.async_request_refresh()
            return

        if self.description.action == "diagnostics":
            diagnostics = await self.hass.async_add_executor_job(modem.run_diagnostics)
            ok, report = diagnostics_report(diagnostics)
            if self.coordinator.data is not None:
                self.coordinator.data.diagnostics_ok = ok
                self.coordinator.data.diagnostics_report = report
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.hass.bus.async_fire(EVENT_DIAGNOSTICS, {"checks": diagnostics, "ok": ok, "report": report})
            return

        if self.description.action == "reconnect":
            await self.hass.async_add_executor_job(modem.reconnect)
            await self.coordinator.async_request_refresh()
