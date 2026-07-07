from __future__ import annotations

import json
import re
import string
from pathlib import Path

from gsm_modem.const import CONFIG_ENTRY_OPTION_KEYS

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "gsm_modem" / "translations"
CONFIG_ONLY_KEYS = ("port", "baudrate")


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = str(value)
    return out


def _placeholders(value: str) -> set[str]:
    return {tup[1] for tup in string.Formatter().parse(value) if tup[1] is not None}


def _load(lang: str) -> dict:
    return json.loads((ROOT / f"{lang}.json").read_text(encoding="utf-8"))


def test_translation_files_have_same_keys() -> None:
    en = _flatten(_load("en"))
    pl = _flatten(_load("pl"))
    assert set(en) == set(pl)


def test_config_flow_option_keys_are_translated() -> None:
    for lang in ("en", "pl"):
        data = _load(lang)
        for key in CONFIG_ENTRY_OPTION_KEYS:
            assert data["options"]["step"]["init"]["data"][key]
            assert data["config"]["step"]["user"]["data"][key]
            assert data["options"]["step"]["init"]["data_description"][key]
            assert data["config"]["step"]["user"]["data_description"][key]
            assert data["common"]["config"][key]


def test_config_only_fields_are_translated() -> None:
    for lang in ("en", "pl"):
        data = _load(lang)
        for key in CONFIG_ONLY_KEYS:
            assert data["config"]["step"]["user"]["data"][key]
            assert data["config"]["step"]["user"]["data_description"][key]


def test_translation_placeholders_match_between_languages() -> None:
    en = _flatten(_load("en"))
    pl = _flatten(_load("pl"))
    for key, en_value in en.items():
        assert _placeholders(en_value) == _placeholders(pl[key]), key


def test_no_jinja_in_translation_json() -> None:
    """Jinja examples must live in Python defaults, not translation JSON."""
    pattern = re.compile(r"\{\{|\{%")
    for lang in ("en", "pl"):
        flat = _flatten(_load(lang))
        for key, value in flat.items():
            assert not pattern.search(value), f"{lang}:{key}"


def test_config_flow_errors_are_translated() -> None:
    for lang in ("en", "pl"):
        data = _load(lang)
        assert data["config"]["error"]["invalid_phone_numbers"]
        assert data["options"]["error"]["invalid_phone_numbers"]


def test_selector_option_keys_are_valid() -> None:
    """Home Assistant requires selector option keys to match [a-z0-9-_]+."""
    pattern = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
    for lang in ("en", "pl"):
        options = _load(lang)["selector"]["sms_box"]["options"]
        for key in options:
            assert pattern.match(key), f"{lang}: sms_box option {key!r}"
