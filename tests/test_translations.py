"""Translation files stay valid, in sync with each other, and in sync with the code.

The integration is English-only. Home Assistant serves
``translations/en.json`` at runtime; ``strings.json`` is the source it is
generated from (HA convention), so the two must be identical.

The rest of this module checks the strings against what the code shows:

- every form the config, subentry and options flows can show (found by
  walking the real flows, not by re-listing schemas here) needs a string for
  each field, section and translated select option;
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
from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
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
    CONF_SUNRISE_OFFSET,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_TEMP_ENTITY,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.config_flow import (
    ABORT_CONSOLIDATE_FIRST,
    ERROR_COVER_TYPE,
    ERROR_HOUSE_SETTING,
)
from custom_components.adaptive_cover.settings.validate import ERROR_KEYS
from custom_components.adaptive_cover.window_cover import ERROR_COVER_IN_USE

from .house_model import Window, mock_house
from .window_form import show_type, start_add, start_reconfigure

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


async def _config_flow_forms(hass) -> list[dict[str, Any]]:
    """Walk the first window's form (a fresh install), for every cover type."""
    forms: list[dict[str, Any]] = []
    for sensor_type in TYPE_OPTIONS:
        result = await start_add(hass)
        assert result["step_id"] == "user", result
        forms.append(result)
        if sensor_type != SensorType.BLIND:
            result = await show_type(hass, result, sensor_type, "cover.i18n")
            assert result["step_id"] == "user", result
            forms.append(result)
        hass.config_entries.flow.async_abort(result["flow_id"])
    return forms


def _house(hass):
    """A house entry (3.1) with one window per type."""
    return mock_house(
        hass,
        [
            Window(
                name=f"i18n {sensor_type}",
                sensor_type=sensor_type,
                options={**BASE_OPTIONS, **type_options},
            )
            for sensor_type, type_options in TYPE_OPTIONS.items()
        ],
    )


async def _subentry_flow_forms(hass) -> list[dict[str, Any]]:
    """The window subentry forms: add for every type, reconfigure each.

    Windows exist, so the add form offers "Copy from".
    """
    forms: list[dict[str, Any]] = []
    house = _house(hass)
    manager = hass.config_entries.subentries
    for sensor_type in TYPE_OPTIONS:
        result = await manager.async_init(
            (house.entry_id, "window"),
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["step_id"] == "user", result
        forms.append(result)
        if sensor_type != SensorType.BLIND:
            result = await manager.async_configure(
                result["flow_id"],
                {
                    name: (
                        {"cover_entity_id": "cover.i18n", "sensor_type": sensor_type}
                        if name == "window"
                        else {}
                    )
                    for name in result["data_schema"].schema
                },
            )
            assert result["step_id"] == "user", result
            forms.append(result)
        manager.async_abort(result["flow_id"])
    for subentry in house.subentries.values():
        result = await start_reconfigure(hass, house, subentry.subentry_id)
        assert result["step_id"] == "reconfigure", result
        forms.append(result)
        manager.async_abort(result["flow_id"])
    return forms


async def _house_options_forms(hass) -> list[dict[str, Any]]:
    """The house entry's options: the house settings."""
    house = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get("is_hub")
    )
    result = await hass.config_entries.options.async_init(house.entry_id)
    assert result["step_id"] == "house", result
    hass.config_entries.options.async_abort(result["flow_id"])
    return [result]


def _step_methods(class_name: str) -> set[str]:
    """Step ids of the ``async_step_*`` methods one flow class defines."""
    tree = ast.parse((PACKAGE / "config_flow.py").read_text(encoding="utf-8"))
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name.removeprefix("async_step_")
        for node in cls.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name.startswith("async_step_")
    }


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
    )

    # The house settings (numbers and switches) are hub rows (P5 flip).
    specs = [
        (platform, spec)
        for (platform, _suffix), spec in (WINDOW_SURFACE | HUB_SURFACE).items()
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
    # The config flow runs on a fresh install only (single_config_entry).
    config_forms = await _config_flow_forms(hass)
    # The house's window subentries and the house settings.
    subentry_forms = await _subentry_flow_forms(hass)
    house_forms = await _house_options_forms(hass)

    # The walk must reach every step the code can show, and every step
    # method must be reachable (the house options' init goes straight to
    # the house step). The options flow lost nine unreachable per-page
    # steps in P3, the setup wizard its nine pages in P6 and the window
    # entries' flows in P8; this keeps dead steps from returning.
    for flow, cls, forms, formless in (
        ("config", "ConfigFlowHandler", config_forms, set()),
        ("config_subentries", "WindowSubentryFlow", subentry_forms, set()),
        ("options", "HouseOptionsFlow", house_forms, {"init"}),
    ):
        shown = {result["step_id"] for result in forms}
        unvisited = (_literal_step_ids(cls) | _step_methods(cls)) - shown - formless
        assert not unvisited, (
            f"{flow} steps the walk never reached: {sorted(unvisited)}"
        )

    needs = _Needs()
    for result in config_forms:
        needs.add_form("config", result)
    for result in subentry_forms:
        needs.add_form("config_subentries.window", result)
    for result in house_forms:
        needs.add_form("options", result)
    # The window subentry: its buttons, name, the form's errors and how it
    # ends ("Add window" on a house not on 3.x: consolidate first); the
    # house options' error.
    window = "config_subentries.window"
    needs.need(f"{window}.initiate_flow.user")
    needs.need(f"{window}.initiate_flow.reconfigure")
    needs.need(f"{window}.entry_type")
    for key in (*ERROR_KEYS, ERROR_COVER_IN_USE, ERROR_COVER_TYPE):
        needs.need(f"{window}.error.{key}")
    for reason in (
        "already_configured",
        "reconfigure_successful",
        ABORT_CONSOLIDATE_FIRST,
    ):
        needs.need(f"{window}.abort.{reason}")
    needs.need(f"options.error.{ERROR_HOUSE_SETTING}")
    # Cross-field errors (settings/validate.py): the first window's form
    # runs every rule.
    for key in ERROR_KEYS:
        needs.need(f"config.error.{key}")
    # One cover per window (window_cover.py) and a cover that can move the
    # way its type needs: the first window's form checks both; a second
    # house for the same unique_id aborts.
    needs.need(f"config.error.{ERROR_COVER_IN_USE}")
    needs.need(f"config.error.{ERROR_COVER_TYPE}")
    needs.need("config.abort.already_configured")

    have = {
        key
        for key, _ in _leaves(strings)
        if key.split(".")[0] in {"config", "config_subentries", "options", "selector"}
    }
    missing = sorted(needs.required - have)
    stale = sorted(have - needs.allowed)
    assert not missing, f"strings.json lacks {len(missing)} flow strings: {missing}"
    assert not stale, (
        f"strings.json has {len(stale)} flow strings nothing shows: {stale}"
    )


def test_issue_and_exception_strings_cover_the_code(strings: dict[str, Any]) -> None:
    """The repair issues and setup errors the code raises have their strings.

    ``consolidate_first`` (a house that still has window entries, upgrade.py)
    is both a repair issue and the setup error of its entries;
    ``house_not_migrated`` is the setup error of a house whose migration to
    3.1 was refused; ``window_setup_failed`` is one window's repair issue.
    """
    from custom_components.adaptive_cover.house import WINDOW_FAILED_ISSUE
    from custom_components.adaptive_cover.upgrade import ISSUE_ID

    issues = strings["issues"]
    assert set(issues) == {ISSUE_ID, WINDOW_FAILED_ISSUE}
    for key in issues:
        assert set(issues[key]) == {"title", "description"}, key
    assert "{count}" in issues[ISSUE_ID]["description"]
    assert "{windows}" in issues[ISSUE_ID]["description"]
    exceptions = strings["exceptions"]
    assert set(exceptions) == {ISSUE_ID, "house_not_migrated"}
    assert "{count}" in exceptions[ISSUE_ID]["message"]
    assert "{version}" in exceptions["house_not_migrated"]["message"]


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
