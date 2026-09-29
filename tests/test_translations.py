"""Translation files stay valid, in sync with each other, and in sync with the code.

The integration is English-only. Home Assistant serves
``translations/en.json`` at runtime; ``strings.json`` is the source it is
generated from (HA convention), so the two must be identical.

The rest of this module checks the strings against what the code shows:

- every form the config and options flows can show (found by walking the real
  flows, not by re-listing schemas here) needs a string for each field,
  section and translated select option;
- every entity ``translation_key`` in the Python code (found statically with
  ``ast``) needs an ``entity.<platform>.<key>.name`` string;
- no string may outlive the code that used it (a stale key fails, so deleting
  a step or field forces its strings out in the same change).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.config_flow import ConfigFlowHandler
from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_CLIMATE_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENABLE_BLIND_SPOT,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_LENGTH_AWNING,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_ENTITY,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SensorType,
)

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "adaptive_cover"
STRINGS_PATH = PACKAGE / "strings.json"
EN_PATH = PACKAGE / "translations" / "en.json"
ICONS_PATH = PACKAGE / "icons.json"

# Entity base classes -> the platform their translations live under.
PLATFORM_BASES = {
    "BinarySensorEntity": "binary_sensor",
    "ButtonEntity": "button",
    "CoverEntity": "cover",
    "NumberEntity": "number",
    "SelectEntity": "select",
    "SensorEntity": "sensor",
    "SwitchEntity": "switch",
}

TYPE_OPTIONS: dict[str, dict[str, Any]] = {
    SensorType.BLIND: {CONF_HEIGHT_WIN: 2.1, CONF_DISTANCE: 0.5},
    SensorType.AWNING: {
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_LENGTH_AWNING: 2.1,
        CONF_AWNING_ANGLE: 0,
    },
    SensorType.TILT: {
        CONF_TILT_DEPTH: 3,
        CONF_TILT_DISTANCE: 2,
        CONF_TILT_MODE: "mode2",
    },
}

BASE_OPTIONS: dict[str, Any] = {
    CONF_MODE: "basic",
    CONF_AZIMUTH: 180,
    CONF_DEFAULT_HEIGHT: 60,
    CONF_FOV_LEFT: 90,
    CONF_FOV_RIGHT: 90,
    CONF_SUNSET_POS: 0,
    CONF_SUNSET_OFFSET: 0,
    CONF_SUNRISE_OFFSET: 0,
    CONF_INVERSE_STATE: False,
    CONF_ENABLE_BLIND_SPOT: False,
    CONF_INTERP: False,
    CONF_ENTITIES: [],
    CONF_DELTA_POSITION: 1,
    CONF_DELTA_TIME: 2,
    CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 15},
    CONF_MANUAL_OVERRIDE_RESET: False,
    CONF_TEMP_ENTITY: "sensor.indoor",
}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _leaves(node: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (dotted.path, value) for every non-dict value."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, node


class _Needs:
    """Translation keys the code uses: ``required`` must exist, ``allowed`` may."""

    def __init__(self) -> None:
        self.required: set[str] = set()
        self.allowed: set[str] = set()

    def need(self, key: str) -> None:
        self.required.add(key)
        self.allowed.add(key)

    def allow(self, key: str) -> None:
        self.allowed.add(key)

    def add_form(self, flow: str, result: dict[str, Any]) -> None:
        """Record the strings one shown form uses."""
        assert result["type"] is FlowResultType.FORM, result
        base = f"{flow}.step.{result['step_id']}"
        self.allow(f"{base}.title")
        self.allow(f"{base}.description")
        for marker, validator in result["data_schema"].schema.items():
            name = str(marker)
            if isinstance(validator, section):
                sbase = f"{base}.sections.{name}"
                self.need(f"{sbase}.name")
                self.allow(f"{sbase}.description")
                for sub_marker, sub_validator in validator.schema.schema.items():
                    self._add_field(sbase, str(sub_marker), sub_validator)
            else:
                self._add_field(base, name, validator)

    def _add_field(self, prefix: str, name: str, validator: Any) -> None:
        self.need(f"{prefix}.data.{name}")
        self.allow(f"{prefix}.data_description.{name}")
        if isinstance(validator, selector.SelectSelector):
            key = validator.config.get("translation_key")
            if key:
                for option in validator.config["options"]:
                    value = option if isinstance(option, str) else option["value"]
                    self.need(f"selector.{key}.options.{value}")


def _literal_step_ids(class_name: str) -> set[str]:
    """``step_id="..."`` literals inside one class of config_flow.py."""
    tree = ast.parse((PACKAGE / "config_flow.py").read_text(encoding="utf-8"))
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        kw.value.value
        for node in ast.walk(cls)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "step_id" and isinstance(kw.value, ast.Constant)
    }


async def _configure(
    hass, result: dict[str, Any], user_input: dict[str, Any], expect_step: str
) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.FORM, result
    assert result["step_id"] == expect_step, result
    return result


async def _config_flow_forms(hass) -> list[dict[str, Any]]:
    """Walk the setup wizard through every page it can show."""
    forms: list[dict[str, Any]] = []
    type_steps = {
        SensorType.BLIND: "vertical",
        SensorType.AWNING: "horizontal",
        SensorType.TILT: "tilt",
    }
    for sensor_type, type_step in type_steps.items():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "user", result
        forms.append(result)
        result = await _configure(
            hass,
            result,
            {"name": f"i18n {sensor_type}", CONF_MODE: sensor_type},
            type_step,
        )
        forms.append(result)
        if sensor_type == SensorType.BLIND:
            # Opt into every optional page: interp -> blind_spot -> automation
            # -> climate -> weather.
            result = await _configure(
                hass,
                result,
                {
                    CONF_CLIMATE_MODE: True,
                    CONF_INTERP: True,
                    CONF_ENABLE_BLIND_SPOT: True,
                },
                "interp",
            )
            forms.append(result)
            for user_input, step in (
                ({}, "blind_spot"),
                ({}, "automation"),
                ({}, "climate"),
                (
                    {
                        CONF_TEMP_ENTITY: "sensor.indoor",
                        CONF_WEATHER_ENTITY: "weather.home",
                    },
                    "weather",
                ),
            ):
                result = await _configure(hass, result, user_input, step)
                forms.append(result)
        hass.config_entries.flow.async_abort(result["flow_id"])
    return forms


async def _options_flow_forms(hass) -> list[dict[str, Any]]:
    """Every options form, for each cover type with climate mode off and on."""
    forms: list[dict[str, Any]] = []
    legacy_steps = sorted(_literal_step_ids("OptionsFlowHandler") - {"init"})
    for sensor_type, type_options in TYPE_OPTIONS.items():
        for climate in (False, True):
            entry = MockConfigEntry(
                domain=DOMAIN,
                title=f"i18n {sensor_type} {climate}",
                data={"name": f"i18n {sensor_type}", CONF_SENSOR_TYPE: sensor_type},
                options={**BASE_OPTIONS, **type_options, CONF_CLIMATE_MODE: climate},
            )
            entry.add_to_hass(hass)
            result = await hass.config_entries.options.async_init(entry.entry_id)
            forms.append(result)
            hass.config_entries.options.async_abort(result["flow_id"])

            # The per-page options steps predate the one-page form and are no
            # longer routed to, but while the methods exist their strings are
            # referenced; call them directly. (Deleting them, planned for P3,
            # makes their strings stale and this test will say so.)
            flow = ConfigFlowHandler.async_get_options_flow(entry)
            flow.hass = hass
            flow.handler = entry.entry_id
            flow.flow_id = f"i18n-{entry.entry_id}"
            for step in legacy_steps:
                result = await getattr(flow, f"async_step_{step}")()
                forms.append(result)
    return forms


def _init_param_translation_keys(
    tree: ast.Module, cls: ast.ClassDef, init: ast.FunctionDef, param: str
) -> set[str]:
    """String literals passed for ``param`` wherever this module builds ``cls``."""
    index = [arg.arg for arg in init.args.args].index(param) - 1  # minus self
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == cls.name
        ):
            continue
        values = [kw.value for kw in node.keywords if kw.arg == param]
        if not values and len(node.args) > index:
            values = [node.args[index]]
        for value in values:
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                pytest.fail(
                    f"{cls.name}(...) passes a non-literal {param!r}; "
                    "extend tests/test_translations.py to resolve it"
                )
            keys.add(value.value)
    return keys


def _surface_translation_keys() -> set[tuple[str, str]]:
    """(platform, translation_key) from the entity-surface table (P1).

    Entity classes get their translation_key from ``entity_surface.py``
    through ``apply_surface()``, not from a literal the ast scan below can
    see. Numbers use each tunable's option key.
    """
    from custom_components.adaptive_cover.entity_surface import (
        HUB_SURFACE,
        WINDOW_SURFACE,
        window_surface,
    )
    from custom_components.adaptive_cover.number import TUNABLES

    specs = [
        (platform, spec)
        for (platform, _suffix), spec in (WINDOW_SURFACE | HUB_SURFACE).items()
    ]
    specs += [
        ("number", window_surface("number", f"number_{tunable.key}"))
        for tunable in TUNABLES
    ]
    return {
        (platform, spec.translation_key)
        for platform, spec in specs
        if spec is not None and spec.translation_key is not None
    }


def _entity_translation_keys() -> set[tuple[str, str]]:
    """(platform, translation_key) for every entity class in the package."""
    found: set[tuple[str, str]] = _surface_translation_keys()
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            keys: set[str] = set()
            for node in ast.walk(cls):
                if isinstance(node, ast.keyword) and node.arg == "translation_key":
                    pytest.fail(
                        f"{path.name}:{cls.name} passes translation_key=...; "
                        "extend tests/test_translations.py to cover it"
                    )
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    name = (
                        target.id
                        if isinstance(target, ast.Name)
                        else target.attr
                        if isinstance(target, ast.Attribute)
                        else None
                    )
                    if name != "_attr_translation_key":
                        continue
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        keys.add(value.value)
                        continue
                    init = next(
                        (
                            f
                            for f in cls.body
                            if isinstance(f, ast.FunctionDef) and f.name == "__init__"
                        ),
                        None,
                    )
                    if (
                        isinstance(value, ast.Name)
                        and init is not None
                        and value.id in [a.arg for a in init.args.args]
                    ):
                        keys |= _init_param_translation_keys(tree, cls, init, value.id)
                        continue
                    pytest.fail(
                        f"{path.name}:{cls.name} sets _attr_translation_key from an "
                        "expression this test cannot resolve; extend it"
                    )
            if not keys:
                continue
            platforms = {
                PLATFORM_BASES[base.id]
                for base in cls.bases
                if isinstance(base, ast.Name) and base.id in PLATFORM_BASES
            }
            assert len(platforms) == 1, f"{path.name}:{cls.name} platform {platforms}"
            (platform,) = platforms
            found |= {(platform, key) for key in keys}
    return found


@pytest.fixture
def strings() -> dict[str, Any]:
    return _load(STRINGS_PATH)


@pytest.mark.parametrize(
    "path", [STRINGS_PATH, EN_PATH, ICONS_PATH], ids=lambda p: p.name
)
def test_translation_files_are_valid_json(path: Path) -> None:
    data = _load(path)
    assert isinstance(data, dict) and data
    for key, value in _leaves(data):
        assert isinstance(value, str) and value.strip(), (
            f"{path.name}: {key} = {value!r}"
        )


def test_en_json_matches_strings_json(strings: dict[str, Any]) -> None:
    """en.json is generated from strings.json; hand edits to either drift."""
    en = _load(EN_PATH)
    only_strings = sorted(dict(_leaves(strings)).keys() - dict(_leaves(en)).keys())
    only_en = sorted(dict(_leaves(en)).keys() - dict(_leaves(strings)).keys())
    assert not only_strings, f"missing from en.json: {only_strings}"
    assert not only_en, f"missing from strings.json: {only_en}"
    assert en == strings, "values differ: copy strings.json to translations/en.json"


def test_english_is_the_only_language() -> None:
    assert sorted(p.name for p in (PACKAGE / "translations").iterdir()) == ["en.json"]


@pytest.mark.usefixtures("stub_sun_integration")
async def test_flow_strings_cover_every_form(hass, strings: dict[str, Any]) -> None:
    config_forms = await _config_flow_forms(hass)
    options_forms = await _options_flow_forms(hass)

    # The walk must reach every step the code can show.
    for flow, cls, forms in (
        ("config", "ConfigFlowHandler", config_forms),
        ("options", "OptionsFlowHandler", options_forms),
    ):
        shown = {result["step_id"] for result in forms}
        unvisited = _literal_step_ids(cls) - shown
        assert not unvisited, (
            f"{flow} steps the walk never reached: {sorted(unvisited)}"
        )

    needs = _Needs()
    for result in config_forms:
        needs.add_form("config", result)
    for result in options_forms:
        needs.add_form("options", result)

    have = {
        key
        for key, _ in _leaves(strings)
        if key.split(".")[0] in {"config", "options", "selector"}
    }
    missing = sorted(needs.required - have)
    stale = sorted(have - needs.allowed)
    assert not missing, f"strings.json lacks {len(missing)} flow strings: {missing}"
    assert not stale, (
        f"strings.json has {len(stale)} flow strings nothing shows: {stale}"
    )


def test_entity_strings_cover_every_translation_key(strings: dict[str, Any]) -> None:
    used = _entity_translation_keys()
    assert used, "found no entity translation_key at all; the ast scan is broken"

    entity = strings.get("entity", {})
    missing = sorted(
        f"entity.{platform}.{key}.name"
        for platform, key in used
        if "name" not in entity.get(platform, {}).get(key, {})
    )
    assert not missing, f"strings.json lacks entity names: {missing}"

    declared = {(platform, key) for platform, keys in entity.items() for key in keys}
    assert not declared - used, f"stale entity strings: {sorted(declared - used)}"

    icons = _load(ICONS_PATH).get("entity", {})
    icon_keys = {(platform, key) for platform, keys in icons.items() for key in keys}
    assert not icon_keys - used, (
        f"icons.json keys no entity uses: {sorted(icon_keys - used)}"
    )
