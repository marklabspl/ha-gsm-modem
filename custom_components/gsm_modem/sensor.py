from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@dataclass(frozen=True)
class SensorDescription:
    key: str
    value_fn: Callable[[Any], Any]
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    attr_fn: Callable[[Any], dict[str, Any]] | None = None


def _inbox_attrs(status) -> dict[str, Any]:
    if not status.inbox_json:
        return {"messages": []}
    try:
        return {"messages": json.loads(status.inbox_json)}
    except json.JSONDecodeError:
        return {"messages": [], "raw": status.inbox_json}


def _diagnostics_attrs(status) -> dict[str, Any]:
    return {"report": status.diagnostics_report or ""}


def _diagnostics_state(status) -> str:
    if status.diagnostics_ok is True:
        return "pass"
    if status.diagnostics_ok is False:
        return "fail"
    return "unknown"


SENSORS = [
    SensorDescription("signal", lambda s: s.signal_percent, PERCENTAGE, SensorDeviceClass.SIGNAL_STRENGTH),
    SensorDescription("health", lambda s: s.health),
    SensorDescription("operator", lambda s: s.operator),
    SensorDescription("sim_state", lambda s: s.sim_state),
    SensorDescription("registration", lambda s: s.registration),
    SensorDescription("sms_unread", lambda s: s.sms_unread),
    SensorDescription("sms_inbox", lambda s: s.inbox_count, attr_fn=_inbox_attrs),
    SensorDescription("diagnostics", _diagnostics_state, attr_fn=_diagnostics_attrs),
    SensorDescription("reconnect_count", lambda s: s.reconnect_count),
    SensorDescription("last_error", lambda s: s.last_error),
    SensorDescription("signal_raw", lambda s: s.signal_raw),
    SensorDescription("registration_raw", lambda s: s.registration_raw),
    SensorDescription("last_sms_index", lambda s: s.last_sms_index),
    SensorDescription("last_sms_number", lambda s: s.last_sms_number),
    SensorDescription("last_sms_text", lambda s: s.last_sms_text),
    SensorDescription("last_sms_authorized", lambda s: s.last_sms_authorized),
    SensorDescription("last_sms_command", lambda s: s.last_sms_command),
    SensorDescription("last_command_handled", lambda s: s.last_command_handled),
    SensorDescription("last_command_action", lambda s: s.last_command_action),
    SensorDescription("last_command_reply_sent", lambda s: s.last_command_reply_sent),
    SensorDescription("last_command_reply_error", lambda s: s.last_command_reply_error),
    SensorDescription("last_ussd_response", lambda s: s.last_ussd_response),
    SensorDescription("last_outgoing_number", lambda s: s.last_outgoing_number),
    SensorDescription("last_outgoing_segments", lambda s: s.last_outgoing_segments),
    SensorDescription("sent_count", lambda s: s.sent_count),
    SensorDescription("send_fail_count", lambda s: s.send_fail_count),
    SensorDescription("imei", lambda s: s.imei),
    SensorDescription("manufacturer", lambda s: s.manufacturer),
    SensorDescription("model", lambda s: s.model),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GsmSensor(coordinator, entry, desc) for desc in SENSORS])


class GsmSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry, description: SensorDescription):
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_translation_key = description.key
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "translation_key": "modem",
        }

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self._description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        if self.coordinator.data is None or self._description.attr_fn is None:
            return None
        return self._description.attr_fn(self.coordinator.data)
