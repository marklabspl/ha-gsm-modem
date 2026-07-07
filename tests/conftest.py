from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


def _install_homeassistant_stubs() -> None:
    if "homeassistant.helpers.device_registry" in sys.modules:
        return

    ha = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    persistent_notification = ModuleType("homeassistant.components.persistent_notification")
    notify_mod = ModuleType("homeassistant.components.notify")
    sensor_mod = ModuleType("homeassistant.components.sensor")
    binary_sensor_mod = ModuleType("homeassistant.components.binary_sensor")
    button_mod = ModuleType("homeassistant.components.button")
    config_entries = ModuleType("homeassistant.config_entries")
    const = ModuleType("homeassistant.const")
    core = ModuleType("homeassistant.core")
    exceptions = ModuleType("homeassistant.exceptions")
    helpers = ModuleType("homeassistant.helpers")
    selector = ModuleType("homeassistant.helpers.selector")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    template = ModuleType("homeassistant.helpers.template")
    translation = ModuleType("homeassistant.helpers.translation")

    class ConfigEntry:
        entry_id = "test"
        data: dict = {}
        options: dict = {}

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = type("ConfigFlow", (), {})
    config_entries.OptionsFlow = type("OptionsFlow", (), {})

    const.Platform = MagicMock()
    const.PERCENTAGE = "%"

    core.HomeAssistant = MagicMock
    core.ServiceCall = MagicMock
    core.callback = lambda fn: fn

    class HomeAssistantError(Exception):
        def __init__(self, *args, translation_domain=None, translation_key=None, translation_placeholders=None, **kwargs):
            super().__init__(*args)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    class ServiceValidationError(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ServiceValidationError = ServiceValidationError
    translation.async_get_translations = MagicMock(return_value={})

    update_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
    update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})
    update_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {})

    notify_mod.NotifyEntity = type("NotifyEntity", (), {})
    sensor_mod.SensorEntity = type("SensorEntity", (), {})
    sensor_mod.SensorDeviceClass = MagicMock()
    binary_sensor_mod.BinarySensorEntity = type("BinarySensorEntity", (), {})
    button_mod.ButtonEntity = type("ButtonEntity", (), {})

    persistent_notification.async_create = MagicMock()
    device_registry.async_get = MagicMock(return_value=MagicMock())
    entity_platform.AddEntitiesCallback = MagicMock
    template.Template = MagicMock()

    ha.config_entries = config_entries
    ha.const = const
    ha.core = core
    ha.exceptions = exceptions
    ha.components = components
    ha.helpers = helpers

    components.persistent_notification = persistent_notification
    components.notify = notify_mod
    components.sensor = sensor_mod
    components.binary_sensor = binary_sensor_mod
    components.button = button_mod

    helpers.selector = selector
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    helpers.update_coordinator = update_coordinator
    helpers.template = template
    helpers.translation = translation

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.persistent_notification"] = persistent_notification
    sys.modules["homeassistant.components.notify"] = notify_mod
    sys.modules["homeassistant.components.sensor"] = sensor_mod
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_mod
    sys.modules["homeassistant.components.button"] = button_mod
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.exceptions"] = exceptions
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.selector"] = selector
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    sys.modules["homeassistant.helpers.template"] = template
    sys.modules["homeassistant.helpers.translation"] = translation


_install_homeassistant_stubs()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
