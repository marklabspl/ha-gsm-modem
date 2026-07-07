from __future__ import annotations

import json
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import CONFIG_ENTRY_OPTION_KEYS, DOMAIN
from .modem.sms_encoding import needs_ucs2


def options_from_entry(entry) -> dict:
    """Merge persisted config entry data and options for UI-facing settings."""
    merged = {key: entry.data[key] for key in CONFIG_ENTRY_OPTION_KEYS if key in entry.data}
    merged.update(entry.options)
    return merged


def command_text(value: str | None) -> str:
    raw = (value or "").strip().upper()
    if not raw:
        return ""
    first_line = next((line.strip() for line in raw.replace("\r", "\n").split("\n") if line.strip()), "")
    if not first_line:
        return ""
    token = first_line.split()[0]
    return token.strip(".,;:!?\"'()[]{}")


def event_suffix(command: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", command.lower()).strip("_")
    return value or "unknown"


def command_set(value: str | None) -> set[str]:
    if not value:
        return set()
    raw = str(value).replace(";", ",").replace("\n", ",").split(",")
    return {command_text(item) for item in raw if command_text(item)}


def parse_custom_command_reply_templates(value: str | None) -> dict[str, str]:
    """Parse per-command SMS reply templates from multiline text.

    Format (one command per line):
        BRAMA | Brama: {{ states('cover.brama') }}
        GATE | Gate: {{ states('cover.gate') }}

    Lines starting with # are ignored. Command names are normalized like SMS commands.
    """
    result: dict[str, str] = {}
    if not value:
        return result
    for line in str(value).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "|" not in stripped:
            continue
        command_part, template = stripped.split("|", 1)
        command = command_text(command_part)
        template = template.strip()
        if command and template:
            result[command] = template
    return result


def resolve_custom_command_reply_template(
    command: str,
    per_command_templates: dict[str, str],
    default_template: str,
) -> str:
    normalized = command_text(command)
    if normalized and normalized in per_command_templates:
        return per_command_templates[normalized]
    return default_template


def status_reply(status) -> str:
    health = status.health or health_from_status(status)
    signal = status.signal_percent if status.signal_percent is not None else "?"
    return (
        f"Modem: {health}\n"
        f"Network: {status.registration or 'unknown'}\n"
        f"Operator: {status.operator or 'unknown'}\n"
        f"Signal: {signal}%\n"
        f"SIM: {status.sim_state or 'unknown'}"
    )


def prepare_status_for_reply(status) -> None:
    status.health = health_from_status(status)


def command_reply_variables(status, **extra: Any) -> dict[str, Any]:
    prepare_status_for_reply(status)
    return {
        "status": status,
        "registration": status.registration,
        "operator": status.operator,
        "signal_percent": status.signal_percent,
        "sim_state": status.sim_state,
        "health": status.health,
        **extra,
    }


async def render_command_reply(
    hass,
    template_str: str | None,
    variables: dict[str, Any],
    fallback: str,
) -> str:
    try:
        rendered = await render_reply_template(hass, template_str, variables)
    except Exception:  # noqa: BLE001 - template errors should not break polling
        return fallback
    return rendered or fallback


def messages_payload(messages) -> tuple[int, str]:
    items = [message.as_dict() for message in messages]
    return len(items), json.dumps(items[-20:], ensure_ascii=False)


def diagnostics_report(checks: dict[str, object]) -> tuple[bool, str]:
    lines: list[str] = []
    ok_all = True
    for name, result in checks.items():
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        ok_all = ok_all and ok
        label = name.replace("_", " ").title()
        lines.append(f"{'PASS' if ok else 'FAIL'} - {label}")
        if isinstance(result, dict) and result.get("error"):
            lines.append(f"  {result['error']}")
    return ok_all, "\n".join(lines)


def prune_seen_indexes(seen: set[int], current_indexes: set[int]) -> None:
    seen.intersection_update(current_indexes)


async def render_reply_template(hass, template_str: str | None, variables: dict[str, Any]) -> str | None:
    if not template_str or not str(template_str).strip():
        return None
    from homeassistant.helpers.template import Template

    template = Template(str(template_str), hass)
    rendered = await template.async_render(variables, parse_result=False)
    return str(rendered).strip() or None


def health_from_status(status) -> str:
    if status.last_error:
        return "problem"
    if status.sim_state != "READY":
        return "sim_not_ready"
    registration = (status.registration or "").lower()
    if registration and "not registered" in registration:
        return "not_registered"
    if registration and "registered" in registration:
        if status.signal_percent is not None and status.signal_percent >= 50:
            return "excellent"
        return "weak_signal"
    return "not_registered"


def estimate_sms_segments(message: str) -> int:
    text = str(message or "")
    if not text:
        return 1
    if needs_ucs2(text):
        single, multipart = 70, 67
    else:
        single, multipart = 160, 153
    if len(text) <= single:
        return 1
    return (len(text) + multipart - 1) // multipart


def modem_error(key: str, **placeholders: object) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def service_error(key: str, **placeholders: object) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


async def async_translate(hass: HomeAssistant, category: str, key: str, **placeholders: object) -> str:
    from homeassistant.helpers import translation

    strings = await translation.async_get_translations(
        hass,
        hass.config.language,
        category,
        {DOMAIN},
    )
    message = strings.get(f"component.{DOMAIN}.{category}.{key}", key)
    if placeholders:
        try:
            return message.format(**placeholders)
        except (KeyError, ValueError):
            return message
    return message
