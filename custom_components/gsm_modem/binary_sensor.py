from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@dataclass(frozen=True)
class BinaryDescription:
    key: str
    value_fn: Callable[[Any], bool | None]


BINARY_SENSORS = [
    BinaryDescription("modem_problem", lambda s: s.health == "problem"),
    BinaryDescription("sim_ready", lambda s: s.sim_state == "READY"),
    BinaryDescription("network_registered", lambda s: bool(s.registration and "registered" in s.registration.lower() and "not registered" not in s.registration.lower())),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GsmBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS])


class GsmBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry, description: BinaryDescription):
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_translation_key = description.key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "translation_key": "modem",
        }

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self._description.value_fn(self.coordinator.data)
