"""Entity surface v2 (P1; contract change C1 in docs/refactor_plan.md).

Pins the per-window and hub entity surface: category, default visibility
and "<Device> <Role>" names; the device area copied from the physical
cover; the 1.1 -> 1.2 config-entry migration that applies the surface to
EXISTING registry rows without overriding user choices; and the new
Position sensor attributes.

Public seams only: config entries, the entity/device/area registries,
hass.states and the translation files. The expected surface below is
written out from the plan's "Entity surface" table, not read from the
integration, so it is an independent pin.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re

from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.util import dt as dt_util
from zoneinfo import ZoneInfo
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

from .characterization.golden_lib import (
    GOLDENS_DIR,
    SLC,
    FakeSunData,
    patch_sun_data,
)
from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle

COVER = "cover.test_cover"
PKG = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN

DIAG = EntityCategory.DIAGNOSTIC
CONFIG = EntityCategory.CONFIG

# (platform, unique_id suffix) -> (category, enabled by default, name).
# The suffixes are the historical, frozen unique_id suffixes.
WINDOW_SURFACE = {
    # primary
    ("sensor", "Cover Position"): (None, True, "Position"),
    ("select", "mode_select"): (None, True, "Mode"),
    ("button", "Reset Manual Override"): (None, True, "Return to auto"),
    # diagnostic, enabled
    ("binary_sensor", "Manual Override"): (DIAG, True, "Manual override"),
    ("binary_sensor", "Sun Infront"): (DIAG, True, "Sun in front"),
    ("sensor", "Control Method"): (DIAG, True, "Control method"),
    # diagnostic, enabled while the card still reads them (disabled in P6)
    ("sensor", "Start Sun"): (DIAG, True, "Start sun"),
    ("sensor", "End Sun"): (DIAG, True, "End sun"),
    ("sensor", "Next State Change"): (DIAG, True, "Next change"),
    ("sensor", "Last State Change"): (DIAG, True, "Last change"),
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


# ------------------------------------------------------------------ areas


def _window_device(hass, entry) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), config_entry_id=entry.entry_id
    )


def _physical_cover(hass, *, device_area=None, entity_area=None):
    """Register COVER as another integration's entity on its own device."""
    other = MockConfigEntry(domain="test")
    other.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers={("test", "shade-1")},
        name="Office shade",
    )
    if device_area is not None:
        dev_reg.async_update_device(device.id, area_id=device_area)
    ent_reg = er.async_get(hass)
    row = ent_reg.async_get_or_create(
        "cover",
        "test",
        "shade-1",
        config_entry=other,
        device_id=device.id,
        suggested_object_id="test_cover",
    )
    assert row.entity_id == COVER
    if entity_area is not None:
        ent_reg.async_update_entity(COVER, area_id=entity_area)


class TestDeviceArea:
    """The window device takes the physical cover's area (never overwritten)."""

    async def test_area_copied_from_cover_device(self, hass, cover_calls):
        office = ar.async_get(hass).async_create("Office")
        _physical_cover(hass, device_area=office.id)
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        assert _window_device(hass, entry).area_id == office.id

    async def test_cover_entity_area_wins_over_its_device(self, hass, cover_calls):
        areas = ar.async_get(hass)
        office = areas.async_create("Office")
        den = areas.async_create("Den")
        _physical_cover(hass, device_area=office.id, entity_area=den.id)
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        assert _window_device(hass, entry).area_id == den.id

    async def test_user_area_not_overwritten(self, hass, cover_calls):
        areas = ar.async_get(hass)
        office = areas.async_create("Office")
        den = areas.async_create("Den")
        _physical_cover(hass, device_area=office.id)
        _set_world(hass)
        entry = _entry(hass)
        # The user already put the window device in the den.
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name="Office Door",
        )
        dev_reg.async_update_device(device.id, area_id=den.id)

        await _setup(hass, entry)
        assert _window_device(hass, entry).area_id == den.id

    async def test_no_area_when_cover_has_none(self, hass, cover_calls):
        _physical_cover(hass)
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        assert _window_device(hass, entry).area_id is None

    async def test_cover_outside_registry_is_ignored(self, hass, cover_calls):
        _set_world(hass)  # COVER exists only as a state
        entry = _entry(hass)
        await _setup(hass, entry)
        assert _window_device(hass, entry).area_id is None


# -------------------------------------------------------------- migration

# A legacy (1.1) entry as the live house has it: rows created by older
# code, with their historical entity_ids, names and categories.
LEGACY_ROWS = {
    ("sensor", "Cover Position"): ("office_door_cover_position", None),
    ("sensor", "Start Sun"): ("office_door_start_sun", None),
    ("sensor", "End Sun"): ("office_door_end_sun", None),
    ("sensor", "Control Method"): ("office_door_control_method", None),
    ("sensor", "Next State Change"): ("office_door_next_state_change", None),
    ("sensor", "Last State Change"): ("office_door_last_state_change", None),
    ("binary_sensor", "Sun Infront"): ("office_door_sun_infront", None),
    ("binary_sensor", "Manual Override"): ("office_door_manual_override", None),
    ("switch", "Toggle Control"): ("office_door_toggle_control", None),
    ("switch", "Manual Override"): ("office_door_manual_override", None),
    ("switch", "Climate Mode"): ("office_door_climate_mode", None),
    ("switch", "Outside Temperature"): ("office_door_outside_temperature", None),
    ("switch", "Lux"): ("office_door_lux", None),
    ("switch", "Irradiance"): ("office_door_irradiance", None),
    ("button", "Reset Manual Override"): (
        "office_door_reset_manual_override",
        None,
    ),
    ("select", "mode_select"): ("office_door_mode", CONFIG),
    **{
        ("number", f"number_{spec.key}"): (f"office_door_{spec.key}", CONFIG)
        for spec in TUNABLES
    },
}


def _legacy_entry(hass, row_overrides=None):
    """A 1.1 entry whose registry rows already exist (pre-P1 upgrade).

    row_overrides: {(platform, suffix): {registry field: value}} applied
    after the row is created, to model user choices.
    """
    row_overrides = row_overrides or {}
    entry = _entry(hass, minor_version=1, **FULL_CLIMATE)
    registry = er.async_get(hass)
    for (platform, suffix), (object_id, category) in LEGACY_ROWS.items():
        row = registry.async_get_or_create(
            platform,
            DOMAIN,
            f"{entry.entry_id}_{suffix}",
            config_entry=entry,
            suggested_object_id=object_id,
            entity_category=category,
            has_entity_name=True,
            original_name=suffix,
        )
        if changes := row_overrides.get((platform, suffix)):
            registry.async_update_entity(row.entity_id, **changes)
    return entry


def _snapshot(hass, entry) -> dict:
    """The registry fields the migration may touch, plus identity."""
    return {
        key: (
            row.entity_id,
            row.unique_id,
            row.entity_category,
            row.disabled_by,
            row.hidden_by,
            row.name,
        )
        for key, row in _rows(hass, entry).items()
    }


class TestMigration:
    """Config entry 1.1 -> 1.2 applies the surface to existing rows."""

    async def test_migration_applies_surface_to_legacy_rows(self, hass, cover_calls):
        _set_world(hass)
        entry = _legacy_entry(hass)
        legacy_ids = {
            key: (row.entity_id, row.unique_id)
            for key, row in _rows(hass, entry).items()
        }

        await _setup(hass, entry)

        assert entry.state is ConfigEntryState.LOADED
        assert (entry.version, entry.minor_version) == (1, 3)
        rows = _rows(hass, entry)
        # Identity is frozen: same unique_ids, same entity_ids.
        assert {
            key: (row.entity_id, row.unique_id) for key, row in rows.items()
        } == legacy_ids
        # Only the old select/number categories and the four diagnostic
        # sensors change visibly; everything lands on the plan's surface.
        for key, (category, enabled, name) in WINDOW_SURFACE.items():
            row = rows[key]
            assert row.entity_category == category, key
            expected = None if enabled else er.RegistryEntryDisabler.INTEGRATION
            assert row.disabled_by == expected, key
            if enabled:
                state = hass.states.get(row.entity_id)
                assert state.attributes["friendly_name"] == f"Office Door {name}"

    async def test_migration_keeps_user_choices(self, hass, cover_calls):
        _set_world(hass)
        entry = _legacy_entry(
            hass,
            {
                ("sensor", "Next State Change"): {"name": "Door next move"},
                ("sensor", "Start Sun"): {"hidden_by": er.RegistryEntryHider.USER},
                ("sensor", "Last State Change"): {
                    "disabled_by": er.RegistryEntryDisabler.USER
                },
                ("sensor", "Control Method"): {
                    "disabled_by": er.RegistryEntryDisabler.USER
                },
            },
        )
        await _setup(hass, entry)
        rows = _rows(hass, entry)

        # Renamed by the user: in use, stays enabled.
        renamed = rows[("sensor", "Next State Change")]
        assert renamed.disabled_by is None
        assert renamed.name == "Door next move"
        assert hass.states.get(renamed.entity_id) is not None
        # Hidden by the user: visibility already chosen, stays enabled.
        hidden = rows[("sensor", "Start Sun")]
        assert hidden.disabled_by is None
        assert hidden.hidden_by is er.RegistryEntryHider.USER
        # Disabled by the user stays disabled BY THE USER, including a role
        # that is enabled by default.
        for key in (("sensor", "Last State Change"), ("sensor", "Control Method")):
            assert rows[key].disabled_by is er.RegistryEntryDisabler.USER, key
        # Untouched rows stay enabled (no role is disabled by default yet);
        # categories apply regardless of user choices.
        assert rows[("sensor", "End Sun")].disabled_by is None
        for key, (category, _enabled, _name) in WINDOW_SURFACE.items():
            assert rows[key].entity_category == category, key

    async def test_migration_is_idempotent(self, hass, cover_calls):
        _set_world(hass)
        entry = _legacy_entry(hass)
        await _setup(hass, entry)
        after_first = _snapshot(hass, entry)

        # Force the migration to run a second time on the migrated rows.
        assert await hass.config_entries.async_unload(entry.entry_id)
        hass.config_entries.async_update_entry(entry, minor_version=1)
        await _setup(hass, entry)

        assert entry.minor_version == 3
        assert _snapshot(hass, entry) == after_first

    async def test_user_reenabled_entity_stays_enabled(self, hass, cover_calls):
        """After the upgrade the migration never runs again, so a sensor the
        user turns back on survives restarts and reloads."""
        _set_world(hass)
        entry = _legacy_entry(hass)
        await _setup(hass, entry)
        registry = er.async_get(hass)
        next_change = _rows(hass, entry)[("sensor", "Next State Change")]
        # No role is disabled by default yet; simulate the P6 state where the
        # integration disabled it, then the user turned it back on.
        registry.async_update_entity(
            next_change.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
        )
        registry.async_update_entity(next_change.entity_id, disabled_by=None)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

        row = registry.async_get(next_change.entity_id)
        assert row.disabled_by is None
        assert hass.states.get(row.entity_id) is not None

    async def test_newer_minor_version_loads_unchanged(self, hass, cover_calls):
        """A downgrade from a later 1.x keeps working (minor bumps are
        backward compatible) and is not rewritten."""
        _set_world(hass)
        entry = _entry(hass, minor_version=4)
        await _setup(hass, entry)
        assert entry.state is ConfigEntryState.LOADED
        assert (entry.version, entry.minor_version) == (1, 4)

    async def test_newer_major_version_is_refused(self, hass, cover_calls):
        _set_world(hass)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="From the future",
            data={"name": "From the future", CONF_SENSOR_TYPE: SensorType.BLIND},
            options={**COMMON_OPTIONS, CONF_ENTITIES: [COVER]},
            version=2,
            minor_version=1,
        )
        entry.add_to_hass(hass)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.MIGRATION_ERROR


# ------------------------------------------------ the live house upgrade

SNAPSHOT = Path(__file__).parent / "fixtures" / "house_snapshot"


def _snapshot_json(name: str) -> dict:
    return json.loads((SNAPSHOT / name).read_text())


def _load_live_house(hass) -> tuple[list[dict], list[dict], dict[str, str | None]]:
    """Put the live house's registries and 1.1 entries into hass.

    Returns (window and hub entries, their registry rows, cover -> the
    cover's effective area).
    """
    entries = [
        entry
        for entry in _snapshot_json("config_entries.json")["entries"]
        if entry["role"] in ("window", "hub")
    ]
    entry_ids = {entry["entry_id"] for entry in entries}
    rows = [
        row
        for row in _snapshot_json("entity_registry.json")["entities"]
        if row["config_entry_id"] in entry_ids
    ]
    covers = [
        cover
        for cover in _snapshot_json("physical_covers.json")["covers"]
        if cover["platform"] != DOMAIN
    ]
    area_reg = ar.async_get(hass)
    for area in _snapshot_json("floors_areas.json")["areas"]:
        created = area_reg.async_create(area["area_id"])
        assert created.id == area["area_id"]
        area_reg.async_update(created.id, name=area["name"])

    # The physical covers belong to another integration, with their areas.
    zha = MockConfigEntry(domain="zha")
    zha.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for cover in covers:
        device = dev_reg.async_get_or_create(
            config_entry_id=zha.entry_id,
            identifiers={("zha", cover["device_id"])},
            name=cover["device_name"],
        )
        dev_reg.async_update_device(device.id, area_id=cover["device_area_id"])
        platform_domain, object_id = cover["entity_id"].split(".", 1)
        ent_reg.async_get_or_create(
            platform_domain,
            "zha",
            cover["entity_id"],
            config_entry=zha,
            device_id=device.id,
            suggested_object_id=object_id,
        )
        ent_reg.async_update_entity(
            cover["entity_id"], area_id=cover["registry_area_id"]
        )
        hass.states.async_set(
            cover["entity_id"],
            cover["state_now"],
            {"current_position": cover["current_position_now"]},
        )

    for entry in entries:
        MockConfigEntry(
            domain=DOMAIN,
            entry_id=entry["entry_id"],
            title=entry["title"],
            data=entry["data"],
            options=entry["options"],
            version=1,
            minor_version=1,
        ).add_to_hass(hass)
        if temp := entry["options"].get(CONF_TEMP_ENTITY):
            hass.states.async_set(temp, "72", {"unit_of_measurement": "°F"})
        if weather := entry["options"].get(CONF_WEATHER_ENTITY):
            hass.states.async_set(weather, "sunny")

    for device in _snapshot_json("device_registry.json")["devices"]:
        (entry_id,) = device["config_entries"]
        created = dev_reg.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={tuple(identifier) for identifier in device["identifiers"]},
            name=device["name"],
        )
        dev_reg.async_update_device(
            created.id, name_by_user=device["name_by_user"], area_id=device["area_id"]
        )

    for row in rows:
        platform_domain, object_id = row["entity_id"].split(".", 1)
        created = ent_reg.async_get_or_create(
            platform_domain,
            DOMAIN,
            row["unique_id"],
            config_entry=hass.config_entries.async_get_entry(row["config_entry_id"]),
            suggested_object_id=object_id,
            has_entity_name=True,
            original_name=row["original_name"],
        )
        assert created.entity_id == row["entity_id"]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0}
    )
    cover_areas = {cover["entity_id"]: cover["effective_area_id"] for cover in covers}
    return entries, rows, cover_areas


async def test_live_house_upgrade(hass, cover_calls):
    """The sanitized live house (tests/fixtures/house_snapshot) upgrades to
    the P1 surface: identity frozen, surface applied, areas copied."""
    entries, rows, cover_areas = _load_live_house(hass)
    windows = [entry for entry in entries if entry["role"] == "window"]
    assert len(windows) == 15
    await _setup(hass, hass.config_entries.async_get_entry(windows[0]["entry_id"]))

    # Every entry migrated and loaded.
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert entry.state is ConfigEntryState.LOADED, entry.title
        assert (entry.version, entry.minor_version) == (1, 3), entry.title

    # Identity is frozen: the same 318 (platform, unique_id) -> entity_id
    # rows, no more. ("X_Manual Override" is both a switch and a sensor.)
    ent_reg = er.async_get(hass)
    after = {
        (row.domain, row.unique_id): row.entity_id
        for row in ent_reg.entities.values()
        if row.platform == DOMAIN
    }
    assert after == {
        (row["domain"], row["unique_id"]): row["entity_id"] for row in rows
    }
    assert len(after) == 318

    # The surface lands on every window row; the hub stays primary.
    window_ids = {entry["entry_id"] for entry in windows}
    disabled = 0
    for row in rows:
        reg = ent_reg.async_get(row["entity_id"])
        if row["config_entry_id"] in window_ids:
            suffix = row["unique_id"].removeprefix(f"{row['config_entry_id']}_")
            category, enabled, _name = WINDOW_SURFACE[(reg.domain, suffix)]
        else:
            category, enabled = None, True
        assert reg.entity_category == category, row["entity_id"]
        if enabled:
            assert reg.disabled_by is None, row["entity_id"]
        else:
            assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            disabled += 1
    assert disabled == 0  # nothing disabled until the card stops reading them (P6)

    # Areas: the owner's stay; the others come from the physical cover.
    dev_reg = dr.async_get(hass)
    snapshot_devices = {
        device["config_entries"][0]: device
        for device in _snapshot_json("device_registry.json")["devices"]
    }
    for entry in windows:
        device = dev_reg.async_get_device_by_identifier(
            (DOMAIN, entry["entry_id"]), config_entry_id=entry["entry_id"]
        )
        user_area = snapshot_devices[entry["entry_id"]]["area_id"]
        (cover,) = entry["options"][CONF_ENTITIES]
        assert device.area_id == (user_area or cover_areas[cover]), entry["title"]
        assert device.area_id is not None, entry["title"]  # every cover has one

        # Cards keep binding by entry_id: it is the window_key.
        window = WindowHandle(hass, cover)
        assert window.attributes["window_key"] == entry["entry_id"]
        assert window.attributes["cover_entity"] == cover
        friendly = window.state("position").attributes["friendly_name"]
        assert friendly == f"{device.name_by_user or device.name} Position"


# ---------------------------------------------------- position attributes

_NEXT_EVENT_RE = re.compile(
    r"^now=(?P<now>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) -> "
    r"name='(?P<name>[^']+)' time=(?P<time>\S+) pos=(?P<pos>\d+)$"
)


def _next_event_cases():
    lines = (GOLDENS_DIR / "next_events.txt").read_text().splitlines()
    cases = [
        (m["now"], m["time"], int(m["pos"]))
        for line in lines
        if (m := _NEXT_EVENT_RE.match(line))
    ]
    assert len(cases) == 3, "goldens/next_events.txt changed shape"
    return cases


class TestPositionAttributes:
    """New Position attributes; the existing ones are pinned elsewhere."""

    async def test_window_identity(self, hass, cover_calls):
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        window = WindowHandle(hass, COVER)
        attrs = window.attributes
        assert attrs["window_key"] == entry.entry_id == window.window_key
        assert attrs["cover_entity"] == COVER
        assert attrs["cover_type"] == "cover_blind"
        assert attrs["override_until"] is None
        assert "cover_entities" not in attrs
        # Additive: the historical attributes are still there.
        for key in ("intent", "decision_trace", "forecast_today", "sun"):
            assert key in attrs

    async def test_multi_cover_entry_lists_every_cover(self, hass, cover_calls):
        _set_world(hass)
        hass.states.async_set("cover.second", "open", {"current_position": 60})
        entry = _entry(hass, covers=(COVER, "cover.second"))
        await _setup(hass, entry)
        attrs = WindowHandle(hass, "cover.second").attributes
        assert attrs["cover_entity"] == COVER
        assert attrs["cover_entities"] == [COVER, "cover.second"]

    @pytest.mark.parametrize(
        ("now_str", "time_str", "pos"),
        _next_event_cases(),
        ids=[case[0] for case in _next_event_cases()],
    )
    async def test_next_move_matches_next_change_golden(
        self, hass, cover_calls, now_str, time_str, pos
    ):
        await hass.config.async_set_time_zone(SLC["tz"])
        local_now = dt.datetime.fromisoformat(now_str).replace(
            tzinfo=ZoneInfo(SLC["tz"])
        )
        sun = FakeSunData(SLC["lat"], SLC["lon"], SLC["tz"], "2026-03-20")
        with freeze_time(local_now), patch_sun_data(sun):
            _set_world(hass)
            entry = _entry(hass, name=f"Next {now_str[-8:]}")
            await _setup(hass, entry)
            next_move = WindowHandle(hass, COVER).attributes["next_move"]

        assert set(next_move) == {"time", "position"}
        assert dt_util.parse_datetime(next_move["time"]) == dt_util.parse_datetime(
            time_str
        )
        assert next_move["position"] == pos

    async def test_override_until_follows_manual_override(
        self, hass, cover_calls, freezer
    ):
        _set_world(hass)
        entry = _entry(hass)  # override duration: 15 minutes
        await _setup(hass, entry)
        window = WindowHandle(hass, COVER)
        # Our startup command lands, then a person moves the shade.
        hass.states.async_set(COVER, "open", {"current_position": window.target})
        await hass.async_block_till_done()
        hass.states.async_set(COVER, "open", {"current_position": 90})
        await hass.async_block_till_done()

        assert window.is_manual
        latched_at = hass.states.get(COVER).last_updated
        expected = dt_util.as_local(latched_at + dt.timedelta(minutes=15))
        until = window.attributes["override_until"]
        assert dt_util.parse_datetime(until) == expected
        assert window.state("manual_override").attributes["until"] == until

        # Past the expiry the next refresh clears it.
        freezer.tick(dt.timedelta(minutes=16))
        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 181.0, "elevation": 45.0}
        )
        await hass.async_block_till_done()
        assert not window.manual_override
        assert window.attributes["override_until"] is None
        assert window.state("manual_override").attributes["until"] is None
