from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    BAUDRATES,
    CONF_ALLOWED_NUMBERS,
    CONF_BALANCE_COMMAND,
    CONF_BALANCE_REPLY_TEMPLATE,
    CONF_BALANCE_USSD_CODE,
    CONF_BAUDRATE,
    CONF_COMMAND_TIMEOUT,
    CONF_DEFAULT_COUNTRY_CODE,
    CONF_DELETE_AUTHORIZED,
    CONF_DELETE_POLICY,
    CONF_DELETE_UNAUTHORIZED,
    CONF_ENABLE_SMS_COMMANDS,
    CONF_HELP_COMMAND,
    CONF_HELP_REPLY_TEMPLATE,
    CONF_CUSTOM_COMMANDS,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATES,
    CONF_NOTIFY_UNAUTHORIZED_SMS,
    CONF_PORT,
    CONF_PURGE_INBOX_AFTER_PROCESSING,
    CONF_REPLY_TO_SMS_COMMANDS,
    CONF_SCAN_INTERVAL,
    CONF_SMS_TIMEOUT,
    CONF_STATUS_COMMAND,
    CONF_STATUS_REPLY_TEMPLATE,
    CONF_TEST_SMS_MESSAGE,
    CONF_TEST_SMS_NUMBER,
    DEFAULT_BALANCE_COMMAND,
    DEFAULT_BALANCE_USSD_CODE,
    DEFAULT_BALANCE_REPLY_TEMPLATE,
    DEFAULT_BAUDRATE,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_DEFAULT_COUNTRY_CODE,
    DEFAULT_DELETE_POLICY,
    DEFAULT_HELP_COMMAND,
    DEFAULT_HELP_REPLY_TEMPLATE,
    DEFAULT_CUSTOM_COMMANDS,
    DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
    DEFAULT_PURGE_INBOX_AFTER_PROCESSING,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SMS_TIMEOUT,
    DEFAULT_STATUS_COMMAND,
    DEFAULT_STATUS_REPLY_TEMPLATE,
    DEFAULT_TEST_SMS_MESSAGE,
    DELETE_POLICY_ALL,
    DELETE_POLICY_AUTHORIZED,
    DELETE_POLICY_NEVER,
    DELETE_POLICY_UNAUTHORIZED,
    DELETE_POLICIES,
    DOMAIN,
    SCAN_INTERVALS,
)
from .modem import GsmModemClient, normalize_phone, validate_phone_entry
from .modem.discovery import candidate_ports, discover_modem_ports
from .util import options_from_entry

_LOGGER = logging.getLogger(__name__)

_LOCALIZED_DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "pl": {
        CONF_STATUS_REPLY_TEMPLATE: (
            "Status modemu:\n"
            "- Stan: {{ health }}\n"
            "- Sieć: {{ registration }}\n"
            "- Operator: {{ operator }}\n"
            "- Sygnał: {{ signal_percent }}%\n"
            "- SIM: {{ sim_state }}"
        ),
        CONF_BALANCE_REPLY_TEMPLATE: "Saldo ({{ ussd_code }}): {{ ussd_response }}",
        CONF_HELP_REPLY_TEMPLATE: "Dostępne komendy: {{ commands | join(', ') }}",
        CONF_CUSTOM_COMMAND_REPLY_TEMPLATE: "Komenda {{ command }} wykonana.",
    },
    "en": {
        CONF_STATUS_REPLY_TEMPLATE: DEFAULT_STATUS_REPLY_TEMPLATE,
        CONF_BALANCE_REPLY_TEMPLATE: DEFAULT_BALANCE_REPLY_TEMPLATE,
        CONF_HELP_REPLY_TEMPLATE: DEFAULT_HELP_REPLY_TEMPLATE,
        CONF_CUSTOM_COMMAND_REPLY_TEMPLATE: DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
    },
}


def _ports(baudrate: int = DEFAULT_BAUDRATE) -> list[str]:
    discovered = discover_modem_ports(baudrate)
    if discovered:
        return discovered
    ports = candidate_ports()
    return ports or [DEFAULT_PORT]


def _parse_numbers(value: str | list[str] | None, default_country_code: str = DEFAULT_DEFAULT_COUNTRY_CODE) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = value.replace(";", ",").replace("\n", ",").split(",")

    numbers: list[str] = []
    for item in raw_items:
        normalized = validate_phone_entry(str(item), default_country_code=default_country_code)
        if normalized and normalized not in numbers:
            numbers.append(normalized)
    return numbers


def _invalid_phone_entries(value: str | list[str] | None, default_country_code: str) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = value.replace(";", ",").replace("\n", ",").split(",")

    invalid: list[str] = []
    for item in raw_items:
        stripped = str(item).strip()
        if not stripped:
            continue
        if validate_phone_entry(stripped, default_country_code=default_country_code) is None:
            invalid.append(stripped)
    return invalid


def _validate_form_input(user_input: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    country_code = _normalize_country_code(user_input.get(CONF_DEFAULT_COUNTRY_CODE))
    invalid_allowed = _invalid_phone_entries(user_input.get(CONF_ALLOWED_NUMBERS, ""), country_code)
    if invalid_allowed:
        errors["base"] = "invalid_phone_numbers"
    test_number = str(user_input.get(CONF_TEST_SMS_NUMBER, "")).strip()
    if test_number and validate_phone_entry(test_number, default_country_code=country_code) is None:
        errors[CONF_TEST_SMS_NUMBER] = "invalid_phone_numbers"
    return errors


def _normalize_country_code(value: str | None) -> str:
    cleaned = "".join(ch for ch in str(value or "") if ch.isdigit())
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    return cleaned or DEFAULT_DEFAULT_COUNTRY_CODE


def _numbers_to_text(numbers: list[str] | None) -> str:
    return ", ".join(numbers or [])


def _delete_policy_from_legacy(data: dict) -> str:
    if CONF_DELETE_POLICY in data:
        return data[CONF_DELETE_POLICY]
    delete_authorized = bool(data.get(CONF_DELETE_AUTHORIZED, False))
    delete_unauthorized = bool(data.get(CONF_DELETE_UNAUTHORIZED, True))
    if delete_authorized and delete_unauthorized:
        return DELETE_POLICY_ALL
    if delete_authorized:
        return DELETE_POLICY_AUTHORIZED
    if delete_unauthorized:
        return DELETE_POLICY_UNAUTHORIZED
    return DELETE_POLICY_NEVER


def _normalize_options(data: dict) -> dict:
    result = dict(data)
    default_country_code = _normalize_country_code(result.get(CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE))
    result[CONF_DEFAULT_COUNTRY_CODE] = default_country_code
    result[CONF_SCAN_INTERVAL] = int(result.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    if CONF_BAUDRATE in result:
        result[CONF_BAUDRATE] = int(result[CONF_BAUDRATE])
    result[CONF_COMMAND_TIMEOUT] = float(result.get(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT))
    result[CONF_SMS_TIMEOUT] = float(result.get(CONF_SMS_TIMEOUT, DEFAULT_SMS_TIMEOUT))
    result[CONF_ALLOWED_NUMBERS] = _parse_numbers(
        result.get(CONF_ALLOWED_NUMBERS, ""),
        default_country_code=default_country_code,
    )
    result[CONF_TEST_SMS_NUMBER] = validate_phone_entry(
        result.get(CONF_TEST_SMS_NUMBER, ""),
        default_country_code=default_country_code,
    ) or ""
    result[CONF_TEST_SMS_MESSAGE] = str(result.get(CONF_TEST_SMS_MESSAGE, DEFAULT_TEST_SMS_MESSAGE)).strip() or DEFAULT_TEST_SMS_MESSAGE
    result[CONF_DELETE_POLICY] = result.get(CONF_DELETE_POLICY, DEFAULT_DELETE_POLICY)
    result[CONF_PURGE_INBOX_AFTER_PROCESSING] = bool(
        result.get(CONF_PURGE_INBOX_AFTER_PROCESSING, DEFAULT_PURGE_INBOX_AFTER_PROCESSING)
    )
    result[CONF_BALANCE_USSD_CODE] = str(result.get(CONF_BALANCE_USSD_CODE, DEFAULT_BALANCE_USSD_CODE)).strip() or DEFAULT_BALANCE_USSD_CODE
    result[CONF_ENABLE_SMS_COMMANDS] = bool(result.get(CONF_ENABLE_SMS_COMMANDS, True))
    result[CONF_REPLY_TO_SMS_COMMANDS] = bool(result.get(CONF_REPLY_TO_SMS_COMMANDS, True))
    result[CONF_NOTIFY_UNAUTHORIZED_SMS] = bool(result.get(CONF_NOTIFY_UNAUTHORIZED_SMS, False))
    result[CONF_STATUS_COMMAND] = str(result.get(CONF_STATUS_COMMAND, DEFAULT_STATUS_COMMAND)).strip().upper() or DEFAULT_STATUS_COMMAND
    result[CONF_BALANCE_COMMAND] = str(result.get(CONF_BALANCE_COMMAND, DEFAULT_BALANCE_COMMAND)).strip().upper() or DEFAULT_BALANCE_COMMAND
    result[CONF_HELP_COMMAND] = str(result.get(CONF_HELP_COMMAND, DEFAULT_HELP_COMMAND)).strip().upper() or DEFAULT_HELP_COMMAND
    result[CONF_CUSTOM_COMMANDS] = str(result.get(CONF_CUSTOM_COMMANDS, DEFAULT_CUSTOM_COMMANDS)).strip()
    result[CONF_CUSTOM_COMMAND_REPLY_TEMPLATE] = str(
        result.get(CONF_CUSTOM_COMMAND_REPLY_TEMPLATE, DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE)
    ).strip()
    result[CONF_CUSTOM_COMMAND_REPLY_TEMPLATES] = str(
        result.get(CONF_CUSTOM_COMMAND_REPLY_TEMPLATES, "")
    ).strip()
    result[CONF_STATUS_REPLY_TEMPLATE] = str(result.get(CONF_STATUS_REPLY_TEMPLATE, DEFAULT_STATUS_REPLY_TEMPLATE)).strip()
    result[CONF_BALANCE_REPLY_TEMPLATE] = str(result.get(CONF_BALANCE_REPLY_TEMPLATE, DEFAULT_BALANCE_REPLY_TEMPLATE)).strip()
    result[CONF_HELP_REPLY_TEMPLATE] = str(result.get(CONF_HELP_REPLY_TEMPLATE, DEFAULT_HELP_REPLY_TEMPLATE)).strip()
    return result


async def _localized_template_defaults(hass, current: dict | None = None) -> dict[str, str]:
    current = current or {}
    language = hass.config.language if getattr(hass, "config", None) else "en"
    localized = _LOCALIZED_DEFAULT_TEMPLATES.get(
        language,
        _LOCALIZED_DEFAULT_TEMPLATES["en"],
    )
    return {
        CONF_STATUS_REPLY_TEMPLATE: str(
            current.get(CONF_STATUS_REPLY_TEMPLATE, localized[CONF_STATUS_REPLY_TEMPLATE])
        ),
        CONF_BALANCE_REPLY_TEMPLATE: str(
            current.get(CONF_BALANCE_REPLY_TEMPLATE, localized[CONF_BALANCE_REPLY_TEMPLATE])
        ),
        CONF_HELP_REPLY_TEMPLATE: str(
            current.get(CONF_HELP_REPLY_TEMPLATE, localized[CONF_HELP_REPLY_TEMPLATE])
        ),
        CONF_CUSTOM_COMMAND_REPLY_TEMPLATE: str(
            current.get(
                CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                localized[CONF_CUSTOM_COMMAND_REPLY_TEMPLATE],
            )
        ),
    }


def _base_schema(
    current: dict | None = None,
    *,
    include_port: bool = False,
    template_defaults: dict[str, str] | None = None,
) -> vol.Schema:
    current = current or {}
    template_defaults = template_defaults or {}
    baudrate = int(current.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
    fields = {}
    if include_port:
        ports = _ports(baudrate)
        fields[vol.Required(CONF_PORT, default=current.get(CONF_PORT, ports[0]))] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=ports, mode=selector.SelectSelectorMode.DROPDOWN)
        )
    fields.update(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=str(current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[str(value) for value in SCAN_INTERVALS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_SCAN_INTERVAL,
                )
            ),
            vol.Optional(CONF_COMMAND_TIMEOUT, default=float(current.get(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(
                CONF_DEFAULT_COUNTRY_CODE,
                default=current.get(CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE),
            ): selector.TextSelector(),
            vol.Optional(CONF_SMS_TIMEOUT, default=float(current.get(CONF_SMS_TIMEOUT, DEFAULT_SMS_TIMEOUT))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5.0, max=120.0, step=1.0, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_ALLOWED_NUMBERS, default=_numbers_to_text(current.get(CONF_ALLOWED_NUMBERS, []))): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_TEST_SMS_NUMBER, default=current.get(CONF_TEST_SMS_NUMBER, "")): selector.TextSelector(),
            vol.Optional(CONF_TEST_SMS_MESSAGE, default=current.get(CONF_TEST_SMS_MESSAGE, DEFAULT_TEST_SMS_MESSAGE)): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_BALANCE_USSD_CODE, default=current.get(CONF_BALANCE_USSD_CODE, DEFAULT_BALANCE_USSD_CODE)): selector.TextSelector(),
            vol.Optional(CONF_ENABLE_SMS_COMMANDS, default=current.get(CONF_ENABLE_SMS_COMMANDS, True)): selector.BooleanSelector(),
            vol.Optional(CONF_REPLY_TO_SMS_COMMANDS, default=current.get(CONF_REPLY_TO_SMS_COMMANDS, True)): selector.BooleanSelector(),
            vol.Optional(CONF_NOTIFY_UNAUTHORIZED_SMS, default=current.get(CONF_NOTIFY_UNAUTHORIZED_SMS, False)): selector.BooleanSelector(),
            vol.Optional(
                CONF_PURGE_INBOX_AFTER_PROCESSING,
                default=current.get(CONF_PURGE_INBOX_AFTER_PROCESSING, DEFAULT_PURGE_INBOX_AFTER_PROCESSING),
            ): selector.BooleanSelector(),
            vol.Optional(CONF_STATUS_COMMAND, default=current.get(CONF_STATUS_COMMAND, DEFAULT_STATUS_COMMAND)): selector.TextSelector(),
            vol.Optional(CONF_BALANCE_COMMAND, default=current.get(CONF_BALANCE_COMMAND, DEFAULT_BALANCE_COMMAND)): selector.TextSelector(),
            vol.Optional(CONF_HELP_COMMAND, default=current.get(CONF_HELP_COMMAND, DEFAULT_HELP_COMMAND)): selector.TextSelector(),
            vol.Optional(CONF_CUSTOM_COMMANDS, default=current.get(CONF_CUSTOM_COMMANDS, DEFAULT_CUSTOM_COMMANDS)): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                default=current.get(
                    CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                    template_defaults.get(
                        CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                        DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
                    ),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_CUSTOM_COMMAND_REPLY_TEMPLATES,
                default=current.get(CONF_CUSTOM_COMMAND_REPLY_TEMPLATES, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_STATUS_REPLY_TEMPLATE,
                default=current.get(
                    CONF_STATUS_REPLY_TEMPLATE,
                    template_defaults.get(CONF_STATUS_REPLY_TEMPLATE, DEFAULT_STATUS_REPLY_TEMPLATE),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_BALANCE_REPLY_TEMPLATE,
                default=current.get(
                    CONF_BALANCE_REPLY_TEMPLATE,
                    template_defaults.get(CONF_BALANCE_REPLY_TEMPLATE, DEFAULT_BALANCE_REPLY_TEMPLATE),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_HELP_REPLY_TEMPLATE,
                default=current.get(
                    CONF_HELP_REPLY_TEMPLATE,
                    template_defaults.get(CONF_HELP_REPLY_TEMPLATE, DEFAULT_HELP_REPLY_TEMPLATE),
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(CONF_DELETE_POLICY, default=_delete_policy_from_legacy(current)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DELETE_POLICIES,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_DELETE_POLICY,
                )
            ),
        }
    )
    if include_port:
        fields[vol.Required(CONF_BAUDRATE, default=str(current.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)))] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[str(value) for value in BAUDRATES],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key=CONF_BAUDRATE,
            )
        )
    return vol.Schema(fields)


class GsmModemConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 7

    @staticmethod
    async def async_migrate_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
        if entry.version < 7:
            hass.config_entries.async_update_entry(
                entry,
                options=options_from_entry(entry),
                version=7,
            )
        return True

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_form_input(user_input)
            if errors:
                template_defaults = await _localized_template_defaults(self.hass, user_input)
                return self.async_show_form(
                    step_id="user",
                    data_schema=_base_schema(user_input, include_port=True, template_defaults=template_defaults),
                    errors=errors,
                )

            template_defaults = await _localized_template_defaults(self.hass, user_input)
            localized_input = dict(user_input)
            localized_input.setdefault(CONF_STATUS_REPLY_TEMPLATE, template_defaults[CONF_STATUS_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_BALANCE_REPLY_TEMPLATE, template_defaults[CONF_BALANCE_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_HELP_REPLY_TEMPLATE, template_defaults[CONF_HELP_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_CUSTOM_COMMAND_REPLY_TEMPLATE, template_defaults[CONF_CUSTOM_COMMAND_REPLY_TEMPLATE])
            data = _normalize_options(localized_input)
            modem = GsmModemClient(
                data[CONF_PORT],
                int(data[CONF_BAUDRATE]),
                command_timeout=float(data[CONF_COMMAND_TIMEOUT]),
                sms_timeout=float(data[CONF_SMS_TIMEOUT]),
            )
            try:
                await self.hass.async_add_executor_job(modem.quick_test)
                await self.async_set_unique_id(data[CONF_PORT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"GSM Modem {data[CONF_PORT]}", data=data)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Modem test failed on %s: %s", data[CONF_PORT], err)
                errors["base"] = "cannot_connect"
            finally:
                await self.hass.async_add_executor_job(modem.close)

        baudrate = DEFAULT_BAUDRATE
        ports = await self.hass.async_add_executor_job(_ports, baudrate)
        schema_current = {CONF_PORT: ports[0] if ports else DEFAULT_PORT}
        template_defaults = await _localized_template_defaults(self.hass, schema_current)
        return self.async_show_form(
            step_id="user",
            data_schema=_base_schema(schema_current, include_port=True, template_defaults=template_defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GsmModemOptionsFlow()


class GsmModemOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            current = {**self.config_entry.data, **self.config_entry.options}
            template_defaults = await _localized_template_defaults(self.hass, current)
            errors = _validate_form_input(user_input)
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_base_schema({**current, **user_input}, include_port=False, template_defaults=template_defaults),
                    errors=errors,
                )

            localized_input = dict(user_input)
            localized_input.setdefault(CONF_STATUS_REPLY_TEMPLATE, template_defaults[CONF_STATUS_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_BALANCE_REPLY_TEMPLATE, template_defaults[CONF_BALANCE_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_HELP_REPLY_TEMPLATE, template_defaults[CONF_HELP_REPLY_TEMPLATE])
            localized_input.setdefault(CONF_CUSTOM_COMMAND_REPLY_TEMPLATE, template_defaults[CONF_CUSTOM_COMMAND_REPLY_TEMPLATE])
            return self.async_create_entry(title="", data=_normalize_options(localized_input))

        current = {**self.config_entry.data, **self.config_entry.options}
        template_defaults = await _localized_template_defaults(self.hass, current)
        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(current, include_port=False, template_defaults=template_defaults),
        )
