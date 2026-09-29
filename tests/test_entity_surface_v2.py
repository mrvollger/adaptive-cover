"""Entity surface v2 (P1; contract change C1 in docs/refactor_plan.md).

Pins the per-window and hub entity surface: category, default visibility
and "<Device> <Role>" names.

Public seams only: config entries, the entity/device/area registries,
hass.states and the translation files. The expected surface below is
written out from the plan's "Entity surface" table, not read from the
integration, so it is an independent pin.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.const import EntityCategory
from homeassistant.helpers import (
    entity_registry as er,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_IRRADIANCE_ENTITY,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.number import TUNABLES

from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"
PKG = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN

DIAG = EntityCategory.DIAGNOSTIC
CONFIG = EntityCategory.CONFIG

# (platform, unique_id suffix) -> (category, enabled by default, name).
# The suffixes are the historical, frozen unique_id suffixes.
WINDOW_SURFACE = {
    # primary
    ("sensor", "Cover Position"): (None, True, "Target position"),
    ("select", "mode_select"): (None, True, "Mode"),
    ("button", "Reset Manual Override"): (None, True, "Return to auto"),
    # diagnostic, enabled
    ("binary_sensor", "Manual Override"): (DIAG, True, "Manual override"),
    ("binary_sensor", "Sun Infront"): (DIAG, True, "Sun in front"),
    ("sensor", "Control Method"): (DIAG, True, "Control method"),
    # diagnostic, disabled by default
    ("sensor", "Start Sun"): (DIAG, False, "Start sun"),
    ("sensor", "End Sun"): (DIAG, False, "End sun"),
    ("sensor", "Next State Change"): (DIAG, False, "Next change"),
    ("sensor", "Last State Change"): (DIAG, False, "Last change"),
    # config (functional until P5)
    ("switch", "Toggle Control"): (CONFIG, True, "Automatic control"),
    ("switch", "Manual Override"): (CONFIG, True, "Manual override detection"),
    ("switch", "Climate Mode"): (CONFIG, True, "Climate mode"),
    ("switch", "Outside Temperature"): (CONFIG, True, "Outside temperature"),
    ("switch", "Lux"): (CONFIG, True, "Lux"),
    ("switch", "Irradiance"): (CONFIG, True, "Irradiance"),
    ("number", "number_eye_height"): (CONFIG, True, "Eye height"),
    ("number", "number_occupied_distance"): (
        CONFIG,
        True,
        "Seat distance from window",
    ),
    ("number", "number_overhang_depth"): (CONFIG, True, "Overhang depth"),
    ("number", "number_overhang_height"): (
        CONFIG,
        True,
        "Overhang height above sill",
    ),
    ("number", "number_temp_low"): (CONFIG, True, "Heating threshold"),
    ("number", "number_temp_high"): (CONFIG, True, "Cooling threshold"),
    ("number", "number_privacy_offset"): (
        CONFIG,
        True,
        "Privacy delay after sunset",
    ),
}

# Hub: unique_id -> (entity_id of a fresh install, friendly name).
HUB_SURFACE = {
    ("cover", "adaptive_cover_hub_cover"): (
        "cover.adaptive_cover_all",
        "Adaptive Cover All",
    ),
    ("select", "adaptive_cover_hub_house_mode"): (
        "select.adaptive_cover_all_cover_control_mode",
        "Adaptive Cover All Cover control mode",
    ),
    ("button", "adaptive_cover_hub_reset_all"): (
        "button.adaptive_cover_all_return_all_shades_to_auto",
        "Adaptive Cover All Return all shades to auto",
    ),
}

# Every aux entity present: all 6 switches and all 7 numbers exist.
FULL_CLIMATE = {
    CONF_CLIMATE_MODE: True,
    CONF_TEMP_ENTITY: "sensor.indoor",
    CONF_TEMP_LOW: 21,
    CONF_TEMP_HIGH: 25,
    CONF_WEATHER_ENTITY: "weather.home",
    CONF_WEATHER_STATE: ["sunny"],
    CONF_OUTSIDETEMP_ENTITY: "sensor.outdoor",
    CONF_LUX_ENTITY: "sensor.lux",
    CONF_LUX_THRESHOLD: 1000,
    CONF_IRRADIANCE_ENTITY: "sensor.irradiance",
    CONF_IRRADIANCE_THRESHOLD: 300,
}


def _entry(hass, name="Office Door", covers=(COVER,), minor_version=1, **extra):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: list(covers),
            CONF_DELTA_TIME: 0,
            **extra,
        },
        version=1,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _set_world(hass, *, cover_position=60):
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0}
    )
    hass.states.async_set(COVER, "open", {"current_position": cover_position})
    hass.states.async_set("sensor.indoor", "22.0")
    hass.states.async_set("sensor.outdoor", "20.0")
    hass.states.async_set("sensor.lux", "500")
    hass.states.async_set("sensor.irradiance", "200")
    hass.states.async_set("weather.home", "sunny")


def _rows(hass, entry) -> dict[tuple[str, str], er.RegistryEntry]:
    """The entry's registry rows keyed by (platform, unique_id suffix)."""
    prefix = f"{entry.entry_id}_"
    return {
        (row.domain, row.unique_id.removeprefix(prefix)): row
        for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


@pytest.fixture
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


# ---------------------------------------------------------------- surface


class TestFreshSurface:
    """A new entry gets the plan's categories, visibility and names."""

    async def test_categories_and_default_visibility(self, hass, cover_calls):
        _set_world(hass)
        entry = _entry(hass, **FULL_CLIMATE)
        await _setup(hass, entry)

        rows = _rows(hass, entry)
        assert set(rows) == set(WINDOW_SURFACE)
        for key, (category, enabled, _name) in WINDOW_SURFACE.items():
            row = rows[key]
            assert row.entity_category == category, key
            if enabled:
                assert row.disabled_by is None, key
                assert hass.states.get(row.entity_id) is not None, key
            else:
                assert row.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
                assert hass.states.get(row.entity_id) is None, key

    async def test_names_are_device_plus_role(self, hass, cover_calls):
        _set_world(hass)
        entry = _entry(hass, **FULL_CLIMATE)
        await _setup(hass, entry)

        for key, row in _rows(hass, entry).items():
            _category, enabled, name = WINDOW_SURFACE[key]
            assert row.has_entity_name, key
            assert row.original_name == name, key
            if enabled:
                friendly = hass.states.get(row.entity_id).attributes["friendly_name"]
                assert friendly == f"Office Door {name}", key

    async def test_regression_manual_override_names_distinct(self, hass, cover_calls):
        """The override-detection switch and the override binary sensor were
        both named "<Device> Manual Override"; every role now has its own
        name (P1 naming cleanup, decision 5)."""
        _set_world(hass)
        entry = _entry(hass, **FULL_CLIMATE)
        await _setup(hass, entry)
        rows = _rows(hass, entry)

        friendly = {
            key: hass.states.get(row.entity_id).attributes["friendly_name"]
            for key, row in rows.items()
            if row.disabled_by is None
        }
        assert (
            friendly[("switch", "Manual Override")]
            != friendly[("binary_sensor", "Manual Override")]
        )
        assert len(set(friendly.values())) == len(friendly)

    async def test_hub_entities_primary_with_stable_ids(self, hass, cover_calls):
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        await hass.async_block_till_done()  # the hub bootstraps in a task

        registry = er.async_get(hass)
        for (platform, unique_id), (entity_id, friendly) in HUB_SURFACE.items():
            assert registry.async_get_entity_id(platform, DOMAIN, unique_id) == (
                entity_id
            )
            row = registry.async_get(entity_id)
            assert row.entity_category is None
            assert row.disabled_by is None
            assert hass.states.get(entity_id).attributes["friendly_name"] == friendly


class TestTranslations:
    """Entity names come from strings.json, mirrored in translations/en.json."""

    @staticmethod
    def _entity_strings(path: Path) -> dict:
        return json.loads(path.read_text())["entity"]

    def test_en_json_mirrors_strings_json(self):
        assert self._entity_strings(PKG / "strings.json") == self._entity_strings(
            PKG / "translations" / "en.json"
        )

    def test_number_names_match_tunable_specs(self):
        numbers = self._entity_strings(PKG / "strings.json")["number"]
        assert {spec.key: spec.name for spec in TUNABLES} == {
            key: value["name"] for key, value in numbers.items()
        }
