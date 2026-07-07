from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALLOWED_NUMBERS,
    CONF_BALANCE_COMMAND,
    CONF_BALANCE_REPLY_TEMPLATE,
    CONF_BALANCE_USSD_CODE,
    CONF_BAUDRATE,
    CONF_COMMAND_TIMEOUT,
    CONF_DEFAULT_COUNTRY_CODE,
    CONF_DELETE_POLICY,
    CONF_ENABLE_SMS_COMMANDS,
    CONF_HELP_COMMAND,
    CONF_HELP_REPLY_TEMPLATE,
    CONF_NOTIFY_UNAUTHORIZED_SMS,
    CONF_REPLY_TO_SMS_COMMANDS,
    CONF_PURGE_INBOX_AFTER_PROCESSING,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SMS_TIMEOUT,
    CONF_STATUS_COMMAND,
    CONF_STATUS_REPLY_TEMPLATE,
    CONF_TEST_SMS_MESSAGE,
    CONF_TEST_SMS_NUMBER,
    CONF_CUSTOM_COMMANDS,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATES,
    DEFAULT_BALANCE_COMMAND,
    DEFAULT_BALANCE_USSD_CODE,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
    DEFAULT_DEFAULT_COUNTRY_CODE,
    DEFAULT_DELETE_POLICY,
    DEFAULT_PURGE_INBOX_AFTER_PROCESSING,
    DEFAULT_HELP_COMMAND,
    DEFAULT_SMS_TIMEOUT,
    DEFAULT_STATUS_COMMAND,
    DELETE_POLICY_ALL,
    DELETE_POLICY_AUTHORIZED,
    DELETE_POLICY_UNAUTHORIZED,
    DOMAIN,
    EVENT_DIAGNOSTICS,
    EVENT_SMS_LIST,
    EVENT_SMS_COMMAND,
    EVENT_SMS_CUSTOM_COMMAND_PREFIX,
    EVENT_TEMPLATE_PREVIEW,
    EVENT_USSD_RESPONSE,
    EVENT_WATCHDOG_RECONNECT,
    EVENT_TEST_SMS_SENT,
    EVENT_SMS_RECEIVED,
    normalize_sms_box,
    SERVICE_CONFIG_ENTRY_ID,
    SERVICE_DELETE_SMS,
    SERVICE_DELETE_ALL_SMS,
    SERVICE_REPLY_SMS,
    SERVICE_READ_SMS,
    SERVICE_RECONNECT,
    SERVICE_CHECK_BALANCE,
    SERVICE_ENTER_PIN,
    SERVICE_RUN_DIAGNOSTICS,
    SERVICE_PREVIEW_REPLY,
    SERVICE_SEND_SMS,
    SERVICE_SEND_USSD,
    SERVICE_SEND_TEST_SMS,
)
from .modem import GsmModemClient, normalize_phone
from .modem.models import ModemStatus
from .util import (
    async_translate,
    command_reply_variables,
    command_set,
    command_text,
    estimate_sms_segments,
    event_suffix,
    health_from_status,
    messages_payload,
    parse_custom_command_reply_templates,
    prune_seen_indexes,
    render_command_reply,
    resolve_custom_command_reply_template,
    service_error,
    status_reply,
    options_from_entry,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NOTIFY]


def _get_config(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def _entry_runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    return hass.data[DOMAIN][entry_id]


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise service_error("no_modem_configured")

    entry_id = call.data.get(SERVICE_CONFIG_ENTRY_ID)
    if not entry_id:
        device_id = call.data.get("device_id")
        if device_id:
            registry = dr.async_get(hass)
            device = registry.async_get(device_id)
            if device:
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        entry_id = identifier[1]
                        break

    if entry_id:
        if entry_id not in entries:
            raise service_error("modem_not_found", entry_id=entry_id)
        return entries[entry_id]

    if len(entries) == 1:
        return next(iter(entries.values()))

    raise service_error("multiple_modems")


def _modem_timeouts(entry: ConfigEntry) -> tuple[float, float]:
    command_timeout = float(_get_config(entry, CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT))
    sms_timeout = float(_get_config(entry, CONF_SMS_TIMEOUT, DEFAULT_SMS_TIMEOUT))
    return command_timeout, sms_timeout


def _entry_country_code(entry: ConfigEntry) -> str:
    raw = str(_get_config(entry, CONF_DEFAULT_COUNTRY_CODE, DEFAULT_DEFAULT_COUNTRY_CODE) or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    return digits or DEFAULT_DEFAULT_COUNTRY_CODE


def _test_sms_details(entry: ConfigEntry) -> tuple[str, str]:
    number = _get_config(entry, CONF_TEST_SMS_NUMBER, "")
    message = _get_config(entry, CONF_TEST_SMS_MESSAGE, "Test from Home Assistant")
    if not number:
        allowed = _get_config(entry, CONF_ALLOWED_NUMBERS, []) or []
        if allowed:
            number = allowed[0]
    if not number:
        raise service_error("no_test_sms_number")
    default_country_code = _entry_country_code(entry)
    normalized = normalize_phone(str(number), default_country_code=default_country_code)
    return normalized, str(message or "Test from Home Assistant")


def _help_reply(entry: ConfigEntry) -> str:
    status_cmd = _get_config(entry, CONF_STATUS_COMMAND, DEFAULT_STATUS_COMMAND)
    balance_cmd = _get_config(entry, CONF_BALANCE_COMMAND, DEFAULT_BALANCE_COMMAND)
    help_cmd = _get_config(entry, CONF_HELP_COMMAND, DEFAULT_HELP_COMMAND)
    return f"Commands: {status_cmd}, {balance_cmd}, {help_cmd}"


async def _send_reply_sms(
    hass: HomeAssistant,
    runtime: dict[str, Any],
    modem: GsmModemClient,
    sender: str | None,
    reply: str,
    status: ModemStatus,
) -> tuple[bool, str | None]:
    if not sender:
        return False, None
    try:
        await _run_locked(runtime, modem.send_sms, sender, reply)
        _track_send(runtime, sender, reply, success=True)
        return True, None
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Failed to send SMS command reply, reconnecting and retrying once: %s", err)
        try:
            await _run_locked(runtime, modem.reconnect)
            await _run_locked(runtime, modem.send_sms, sender, reply)
            _track_send(runtime, sender, reply, success=True)
            return True, None
        except Exception as retry_err:  # noqa: BLE001
            _LOGGER.warning("SMS command reply retry failed: %s", retry_err)
            _track_send(runtime, sender, reply, success=False)
            status.last_error = str(retry_err)
            return False, str(retry_err)


async def _run_locked(runtime: dict[str, Any], func, *args):
    lock: asyncio.Lock = runtime["lock"]
    async with lock:
        return await runtime["hass"].async_add_executor_job(func, *args)


def _track_send(runtime: dict[str, Any], number: str, message: str, *, success: bool) -> None:
    runtime["last_outgoing_number"] = number
    runtime["last_outgoing_segments"] = estimate_sms_segments(message)
    if success:
        runtime["sent_count"] = int(runtime.get("sent_count", 0)) + 1
    else:
        runtime["send_fail_count"] = int(runtime.get("send_fail_count", 0)) + 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    merged_options = options_from_entry(entry)
    if merged_options != dict(entry.options):
        hass.config_entries.async_update_entry(entry, options=merged_options)
        entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    port = entry.data[CONF_PORT]
    baudrate = int(entry.data[CONF_BAUDRATE])
    scan_interval = int(_get_config(entry, CONF_SCAN_INTERVAL, 30))
    command_timeout, sms_timeout = _modem_timeouts(entry)
    modem = GsmModemClient(
        port=port,
        baudrate=baudrate,
        command_timeout=command_timeout,
        sms_timeout=sms_timeout,
    )
    seen_sms_indexes: set[int] = set()
    runtime: dict[str, Any] = {
        "hass": hass,
        "modem": modem,
        "entry": entry,
        "reconnect_count": 0,
        "sent_count": 0,
        "send_fail_count": 0,
        "last_outgoing_number": None,
        "last_outgoing_segments": None,
        "lock": asyncio.Lock(),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    await hass.async_add_executor_job(modem.connect)

    async def async_update_data():
        try:
            status = await _run_locked(runtime, modem.get_status)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("GSM modem update failed, trying reconnect: %s", err)
            runtime["reconnect_count"] = int(runtime.get("reconnect_count", 0)) + 1
            hass.bus.async_fire(EVENT_WATCHDOG_RECONNECT, {"reason": str(err), "count": runtime["reconnect_count"]})
            try:
                await _run_locked(runtime, modem.reconnect)
                status = await _run_locked(runtime, modem.get_status)
            except Exception as retry_err:  # noqa: BLE001
                if "last_status" in runtime:
                    last_status = runtime["last_status"]
                    last_status.last_error = str(retry_err)
                    last_status.reconnect_count = int(runtime.get("reconnect_count", 0))
                    last_status.health = "problem"
                    return last_status
                raise UpdateFailed(str(retry_err)) from retry_err

        try:
            try:
                unread = await _run_locked(runtime, modem.list_sms, "REC UNREAD")
            except Exception as list_err:  # noqa: BLE001
                _LOGGER.warning(
                    "Unread SMS listing failed, forcing inbox cleanup and retry: %s",
                    list_err,
                )
                await _run_locked(runtime, modem.delete_all_sms, "ALL")
                seen_sms_indexes.clear()
                unread = await _run_locked(runtime, modem.list_sms, "REC UNREAD")
            status.sms_unread = len(unread)
            if unread:
                last_unread = unread[-1]
                status.last_sms_index = last_unread.index
                status.last_sms_number = last_unread.number
                status.last_sms_text = last_unread.text

            current_indexes = {int(message.index) for message in unread if message.index is not None}
            prune_seen_indexes(seen_sms_indexes, current_indexes)
            status.inbox_count, status.inbox_json = messages_payload(unread)

            messages = unread
            default_country_code = _entry_country_code(entry)
            allowed = {
                normalize_phone(number, default_country_code=default_country_code)
                for number in (_get_config(entry, CONF_ALLOWED_NUMBERS, []) or [])
            }
            delete_policy = _get_config(entry, CONF_DELETE_POLICY, DEFAULT_DELETE_POLICY)
            reply_enabled = bool(_get_config(entry, CONF_REPLY_TO_SMS_COMMANDS, True))
            purge_after_processing = bool(
                _get_config(entry, CONF_PURGE_INBOX_AFTER_PROCESSING, DEFAULT_PURGE_INBOX_AFTER_PROCESSING)
            )
            processed_any_sms = False

            for sms in messages:
                index = sms.index
                if index is None or index in seen_sms_indexes:
                    continue
                seen_sms_indexes.add(index)
                processed_any_sms = True
                sender = normalize_phone(sms.number, default_country_code=default_country_code)
                authorized = bool(sender and sender in allowed) if allowed else False
                event_data = {
                    "index": index,
                    "sender": sender,
                    "number": sender,
                    "message": sms.text,
                    "text": sms.text,
                    "authorized": authorized,
                    "date": sms.date,
                    "status": sms.status,
                }
                hass.bus.async_fire(EVENT_SMS_RECEIVED, event_data)

                if not authorized and bool(_get_config(entry, CONF_NOTIFY_UNAUTHORIZED_SMS, False)):
                    title = await async_translate(hass, "common", "unauthorized_sms_title")
                    message = await async_translate(
                        hass,
                        "common",
                        "unauthorized_sms_message",
                        sender=sender or await async_translate(hass, "common", "unknown_sender"),
                        text=sms.text or "",
                    )
                    persistent_notification.async_create(
                        hass,
                        message,
                        title=title,
                        notification_id=f"gsm_modem_unauth_{entry.entry_id}_{index}",
                    )

                command = command_text(sms.text)
                if command:
                    status.last_sms_authorized = authorized
                    status.last_sms_command = command
                _LOGGER.debug(
                    "Incoming SMS index=%s sender=%s authorized=%s command=%s",
                    index,
                    sender,
                    authorized,
                    command or "<none>",
                )

                commands_enabled = bool(_get_config(entry, CONF_ENABLE_SMS_COMMANDS, True))
                if commands_enabled and authorized and command:
                    status_command = command_text(_get_config(entry, CONF_STATUS_COMMAND, DEFAULT_STATUS_COMMAND))
                    balance_command = command_text(_get_config(entry, CONF_BALANCE_COMMAND, DEFAULT_BALANCE_COMMAND))
                    help_command = command_text(_get_config(entry, CONF_HELP_COMMAND, DEFAULT_HELP_COMMAND))
                    custom_commands = command_set(_get_config(entry, CONF_CUSTOM_COMMANDS, ""))
                    known_commands = {status_command, balance_command, help_command} | custom_commands

                    command_event = {**event_data, "command": command, "handled": False}
                    status.last_command_handled = False
                    status.last_command_action = None
                    status.last_command_reply_sent = None
                    status.last_command_reply_error = None

                    if command == status_command:
                        command_event["handled"] = True
                        command_event["action"] = "status"
                        status.last_command_handled = True
                        status.last_command_action = "status"
                        if reply_enabled:
                            reply = await render_command_reply(
                                hass,
                                _get_config(entry, CONF_STATUS_REPLY_TEMPLATE, ""),
                                command_reply_variables(status),
                                status_reply(status),
                            )
                            sent, error = await _send_reply_sms(hass, runtime, modem, sender, reply, status)
                            status.last_command_reply_sent = sent
                            status.last_command_reply_error = error
                    elif command == balance_command:
                        command_event["handled"] = True
                        command_event["action"] = "balance"
                        status.last_command_handled = True
                        status.last_command_action = "balance"
                        ussd_code = _get_config(entry, CONF_BALANCE_USSD_CODE, DEFAULT_BALANCE_USSD_CODE)
                        try:
                            ussd_response = await _run_locked(runtime, modem.send_ussd, ussd_code)
                        except Exception as ussd_err:  # noqa: BLE001 - keep command flow alive on USSD issues
                            _LOGGER.warning("BALANCE command USSD failed: %s", ussd_err)
                            ussd_response = f"USSD error: {ussd_err}"
                        if not ussd_response:
                            ussd_response = "No USSD response received from the modem."
                        status.last_ussd_response = ussd_response
                        command_event["ussd_code"] = ussd_code
                        command_event["ussd_response"] = ussd_response
                        hass.bus.async_fire(EVENT_USSD_RESPONSE, {"code": ussd_code, "response": ussd_response})
                        if reply_enabled:
                            reply = await render_command_reply(
                                hass,
                                _get_config(entry, CONF_BALANCE_REPLY_TEMPLATE, ""),
                                command_reply_variables(status, ussd_code=ussd_code, ussd_response=ussd_response),
                                ussd_response,
                            )
                            sent, error = await _send_reply_sms(hass, runtime, modem, sender, reply, status)
                            status.last_command_reply_sent = sent
                            status.last_command_reply_error = error
                    elif command == help_command:
                        command_event["handled"] = True
                        command_event["action"] = "help"
                        status.last_command_handled = True
                        status.last_command_action = "help"
                        if reply_enabled:
                            reply = await render_command_reply(
                                hass,
                                _get_config(entry, CONF_HELP_REPLY_TEMPLATE, ""),
                                command_reply_variables(
                                    status,
                                    status_command=status_command,
                                    balance_command=balance_command,
                                    help_command=help_command,
                                    commands=[status_command, balance_command, help_command],
                                ),
                                _help_reply(entry),
                            )
                            sent, error = await _send_reply_sms(hass, runtime, modem, sender, reply, status)
                            status.last_command_reply_sent = sent
                            status.last_command_reply_error = error
                    elif command in custom_commands:
                        command_event["handled"] = True
                        command_event["action"] = "custom"
                        status.last_command_handled = True
                        status.last_command_action = "custom"
                        if reply_enabled:
                            per_command_templates = parse_custom_command_reply_templates(
                                _get_config(entry, CONF_CUSTOM_COMMAND_REPLY_TEMPLATES, "")
                            )
                            default_template = _get_config(
                                entry,
                                CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                                DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
                            )
                            reply = await render_command_reply(
                                hass,
                                resolve_custom_command_reply_template(
                                    command,
                                    per_command_templates,
                                    default_template,
                                ),
                                command_reply_variables(status, command=command),
                                f"Command {command} executed.",
                            )
                            sent, error = await _send_reply_sms(hass, runtime, modem, sender, reply, status)
                            status.last_command_reply_sent = sent
                            status.last_command_reply_error = error

                    hass.bus.async_fire(EVENT_SMS_COMMAND, command_event)
                    if command in known_commands:
                        hass.bus.async_fire(f"{EVENT_SMS_CUSTOM_COMMAND_PREFIX}{event_suffix(command)}", command_event)
                    else:
                        _LOGGER.debug("SMS command '%s' not in known command set", command)
                else:
                    _LOGGER.debug(
                        "Skipping SMS command handling index=%s reasons: commands_enabled=%s authorized=%s command_present=%s",
                        index,
                        commands_enabled,
                        authorized,
                        bool(command),
                    )

                should_delete = delete_policy == DELETE_POLICY_ALL
                should_delete = should_delete or (authorized and delete_policy == DELETE_POLICY_AUTHORIZED)
                should_delete = should_delete or ((not authorized) and delete_policy == DELETE_POLICY_UNAUTHORIZED)
                if should_delete:
                    await _run_locked(runtime, modem.delete_sms, int(index))
                    seen_sms_indexes.discard(int(index))

            if purge_after_processing:
                await _run_locked(runtime, modem.delete_all_sms, "ALL")
                seen_sms_indexes.clear()
                if processed_any_sms:
                    _LOGGER.debug("Purge inbox enabled: cleared all SMS after processing cycle")

            status.reconnect_count = int(runtime.get("reconnect_count", 0))
            status.last_outgoing_number = runtime.get("last_outgoing_number")
            status.last_outgoing_segments = runtime.get("last_outgoing_segments")
            status.sent_count = int(runtime.get("sent_count", 0))
            status.send_fail_count = int(runtime.get("send_fail_count", 0))
            if status.last_command_reply_error:
                status.last_error = status.last_command_reply_error
            else:
                status.last_error = None
            status.health = health_from_status(status)
            runtime["last_status"] = status
            return status
        except Exception as err:  # noqa: BLE001 - coordinator reports errors to HA
            status.last_error = str(err)
            status.reconnect_count = int(runtime.get("reconnect_count", 0))
            status.health = "problem"
            runtime["last_status"] = status
            return status

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )
    await coordinator.async_config_entry_first_refresh()

    runtime["coordinator"] = coordinator

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_SMS):

        async def async_send_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            entry_obj: ConfigEntry = runtime_obj["entry"]
            number = normalize_phone(
                call.data["number"],
                default_country_code=_entry_country_code(entry_obj),
            )
            if not number:
                raise service_error("invalid_phone_number")
            message = call.data["message"]
            try:
                await _run_locked(runtime_obj, modem_client.send_sms, number, message)
                _track_send(runtime_obj, number, message, success=True)
            except Exception:
                _track_send(runtime_obj, number, message, success=False)
                raise
            hass.async_create_task(coordinator_obj.async_request_refresh())

        async def async_send_test_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            entry_obj: ConfigEntry = runtime_obj["entry"]
            number, message = _test_sms_details(entry_obj)
            try:
                await _run_locked(runtime_obj, modem_client.send_sms, number, message)
                _track_send(runtime_obj, number, message, success=True)
            except Exception:
                _track_send(runtime_obj, number, message, success=False)
                raise
            hass.bus.async_fire(EVENT_TEST_SMS_SENT, {"number": number, "message": message})

        async def async_send_ussd(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            code = call.data["code"]
            response = await _run_locked(runtime_obj, modem_client.send_ussd, code)
            if not response:
                response = "No USSD response received from the modem."
            if coordinator_obj.data is not None:
                coordinator_obj.data.last_ussd_response = response
                coordinator_obj.async_set_updated_data(coordinator_obj.data)
            hass.bus.async_fire(EVENT_USSD_RESPONSE, {"code": code, "response": response})

        async def async_check_balance(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            entry_obj: ConfigEntry = runtime_obj["entry"]
            code = _get_config(entry_obj, CONF_BALANCE_USSD_CODE, DEFAULT_BALANCE_USSD_CODE)
            response = await _run_locked(runtime_obj, modem_client.send_ussd, code)
            if not response:
                response = "No USSD response received from the modem."
            if coordinator_obj.data is not None:
                coordinator_obj.data.last_ussd_response = response
                coordinator_obj.async_set_updated_data(coordinator_obj.data)
            hass.bus.async_fire(EVENT_USSD_RESPONSE, {"code": code, "response": response})

        async def async_read_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            box = normalize_sms_box(call.data.get("box"))
            messages = await _run_locked(runtime_obj, modem_client.list_sms, box)
            hass.bus.async_fire(EVENT_SMS_LIST, {"messages": [message.as_dict() for message in messages]})

        async def async_run_diagnostics(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            diagnostics = await _run_locked(runtime_obj, modem_client.run_diagnostics)
            hass.bus.async_fire(EVENT_DIAGNOSTICS, {"checks": diagnostics})

        async def async_reconnect(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            await _run_locked(runtime_obj, modem_client.reconnect)
            await coordinator_obj.async_request_refresh()

        async def async_delete_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            index = int(call.data["index"])
            await _run_locked(runtime_obj, modem_client.delete_sms, index)
            await coordinator_obj.async_request_refresh()

        async def async_reply_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            index = int(call.data["index"])
            message = call.data["message"]
            messages = await _run_locked(runtime_obj, modem_client.list_sms, "ALL")
            target = next((sms for sms in messages if sms.index == index), None)
            if target is None or not target.number:
                raise service_error("sms_index_not_found", index=index)
            try:
                await _run_locked(runtime_obj, modem_client.send_sms, target.number, message)
                _track_send(runtime_obj, target.number, message, success=True)
            except Exception:
                _track_send(runtime_obj, target.number, message, success=False)
                raise
            await coordinator_obj.async_request_refresh()

        async def async_delete_all_sms(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            box = normalize_sms_box(call.data.get("box"))
            await _run_locked(runtime_obj, modem_client.delete_all_sms, box)
            await coordinator_obj.async_request_refresh()

        async def async_enter_pin(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            pin = str(call.data["pin"])
            await _run_locked(runtime_obj, modem_client.enter_pin, pin)
            await coordinator_obj.async_request_refresh()

        async def async_preview_reply_templates(call: ServiceCall) -> None:
            runtime_obj = _resolve_runtime(hass, call)
            entry_obj: ConfigEntry = runtime_obj["entry"]
            modem_client: GsmModemClient = runtime_obj["modem"]
            coordinator_obj: DataUpdateCoordinator = runtime_obj["coordinator"]
            status = coordinator_obj.data
            if status is None:
                status = await _run_locked(runtime_obj, modem_client.get_status)
            status_command = command_text(_get_config(entry_obj, CONF_STATUS_COMMAND, DEFAULT_STATUS_COMMAND))
            balance_command = command_text(_get_config(entry_obj, CONF_BALANCE_COMMAND, DEFAULT_BALANCE_COMMAND))
            help_command = command_text(_get_config(entry_obj, CONF_HELP_COMMAND, DEFAULT_HELP_COMMAND))
            ussd_code = _get_config(entry_obj, CONF_BALANCE_USSD_CODE, DEFAULT_BALANCE_USSD_CODE)
            ussd_response = status.last_ussd_response or ""
            status_preview = await render_command_reply(
                hass,
                _get_config(entry_obj, CONF_STATUS_REPLY_TEMPLATE, ""),
                command_reply_variables(status),
                status_reply(status),
            )
            balance_preview = await render_command_reply(
                hass,
                _get_config(entry_obj, CONF_BALANCE_REPLY_TEMPLATE, ""),
                command_reply_variables(status, ussd_code=ussd_code, ussd_response=ussd_response),
                ussd_response or "",
            )
            help_preview = await render_command_reply(
                hass,
                _get_config(entry_obj, CONF_HELP_REPLY_TEMPLATE, ""),
                command_reply_variables(
                    status,
                    status_command=status_command,
                    balance_command=balance_command,
                    help_command=help_command,
                    commands=[status_command, balance_command, help_command],
                ),
                _help_reply(entry_obj),
            )
            custom_commands = command_set(_get_config(entry_obj, CONF_CUSTOM_COMMANDS, ""))
            per_command_templates = parse_custom_command_reply_templates(
                _get_config(entry_obj, CONF_CUSTOM_COMMAND_REPLY_TEMPLATES, "")
            )
            default_custom_template = _get_config(
                entry_obj,
                CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
                DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE,
            )
            sample_command = next(iter(custom_commands), "GATE")
            custom_preview = await render_command_reply(
                hass,
                resolve_custom_command_reply_template(
                    sample_command,
                    per_command_templates,
                    default_custom_template,
                ),
                command_reply_variables(status, command=sample_command),
                f"Command {sample_command} executed.",
            )
            custom_previews: dict[str, str] = {}
            for custom_command in sorted(custom_commands):
                custom_previews[custom_command] = await render_command_reply(
                    hass,
                    resolve_custom_command_reply_template(
                        custom_command,
                        per_command_templates,
                        default_custom_template,
                    ),
                    command_reply_variables(status, command=custom_command),
                    f"Command {custom_command} executed.",
                )
            hass.bus.async_fire(
                EVENT_TEMPLATE_PREVIEW,
                {
                    "config_entry_id": entry_obj.entry_id,
                    "status_preview": status_preview,
                    "balance_preview": balance_preview,
                    "help_preview": help_preview,
                    "custom_preview": custom_preview,
                    "custom_preview_command": sample_command,
                    "custom_previews": custom_previews,
                },
            )

        hass.services.async_register(DOMAIN, SERVICE_SEND_SMS, async_send_sms)
        hass.services.async_register(DOMAIN, SERVICE_SEND_TEST_SMS, async_send_test_sms)
        hass.services.async_register(DOMAIN, SERVICE_SEND_USSD, async_send_ussd)
        hass.services.async_register(DOMAIN, SERVICE_CHECK_BALANCE, async_check_balance)
        hass.services.async_register(DOMAIN, SERVICE_READ_SMS, async_read_sms)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_SMS, async_delete_sms)
        hass.services.async_register(DOMAIN, SERVICE_REPLY_SMS, async_reply_sms)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_ALL_SMS, async_delete_all_sms)
        hass.services.async_register(DOMAIN, SERVICE_RUN_DIAGNOSTICS, async_run_diagnostics)
        hass.services.async_register(DOMAIN, SERVICE_RECONNECT, async_reconnect)
        hass.services.async_register(DOMAIN, SERVICE_ENTER_PIN, async_enter_pin)
        hass.services.async_register(DOMAIN, SERVICE_PREVIEW_REPLY, async_preview_reply_templates)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(runtime["modem"].close)
    return unload_ok
