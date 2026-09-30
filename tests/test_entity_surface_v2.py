"""Entity surface v2 (P1; contract change C1 in docs/refactor_plan.md).

Pins the per-window and hub entity surface: category, default visibility
and "<Device> <Role>" names; the device area copied from the physical
cover; the house entry's versions; and the new Position sensor
attributes. (The 1.x migrations that applied the surface to existing
rows are gone since v2.1: every house that runs v2.1 went through them
on v2.0.x. The six window switches are gone too.)

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
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    SensorType,
)
from custom_components.adaptive_cover.house_settings import HOUSE_NUMBERS

from .characterization.golden_lib import (
    GOLDENS_DIR,
    SLC,
    FakeSunData,
    patch_sun_data,
)
from .conftest import COMMON_OPTIONS
from .house_model import mock_window_entry, window_subentry
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
    # The six switches (hidden aliases since the P5 flip) are gone (P8).
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

# Every aux entity present (before P5 every switch and number existed).
FULL_CLIMATE = {
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


def _entry(hass, name="Office Door", covers=(COVER,), **extra):
    """A house with one window (its key is the house's entry_id)."""
    return mock_window_entry(
        hass,
        {"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        {
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: list(covers),
            CONF_DELTA_TIME: 0,
            **extra,
        },
    )


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
    """The window's registry rows keyed by (platform, unique_id suffix)."""
    prefix = f"{entry.entry_id}_"
    return {
        (row.domain, row.unique_id.removeprefix(prefix)): row
        for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if row.unique_id.startswith(prefix)
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
            assert row.hidden_by is None, key
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
        name (P1 naming cleanup, decision 5). Since v2.1 detection is the
        house's switch."""
        _set_world(hass)
        entry = _entry(hass, **FULL_CLIMATE)
        await _setup(hass, entry)
        rows = _rows(hass, entry)

        friendly = {
            key: hass.states.get(row.entity_id).attributes["friendly_name"]
            for key, row in rows.items()
            if row.disabled_by is None
        }
        detection = er.async_get(hass).async_get_entity_id(
            "switch", DOMAIN, "adaptive_cover_hub_manual_detection"
        )
        assert (
            hass.states.get(detection).attributes["friendly_name"]
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
        """Every number is a house number (P5 flip) and has a name."""
        numbers = self._entity_strings(PKG / "strings.json")["number"]
        assert {spec.key for spec in HOUSE_NUMBERS} == set(numbers)
        assert all(value["name"] for value in numbers.values())


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
            config_subentry_id=window_subentry(entry).subentry_id,
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


# --------------------------------------------------------------- versions


class TestMigration:
    """The house entry's versions (the 1.x migrations are gone since v2.1)."""

    async def test_user_reenabled_entity_stays_enabled(self, hass, cover_calls):
        """No migration touches a running house's rows: a sensor the user
        turns back on survives restarts and reloads."""
        _set_world(hass)
        entry = _entry(hass)
        await _setup(hass, entry)
        registry = er.async_get(hass)
        next_change = _rows(hass, entry)[("sensor", "Next State Change")]
        # Simulate a row the integration disabled, then the user turned back on.
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
        """A downgrade from a later 3.x keeps working (minor bumps are
        backward compatible) and is not rewritten."""
        _set_world(hass)
        entry = _entry(hass)
        hass.config_entries.async_update_entry(
            entry, minor_version=HOUSE_ENTRY_MINOR_VERSION + 1
        )
        await _setup(hass, entry)
        assert entry.state is ConfigEntryState.LOADED
        assert (entry.version, entry.minor_version) == (
            HOUSE_ENTRY_VERSION,
            HOUSE_ENTRY_MINOR_VERSION + 1,
        )

    async def test_newer_major_version_is_refused(self, hass, cover_calls):
        # 3.x is the house since v2.1 (P8): the next major is 4.
        _set_world(hass)
        entry = _entry(hass, name="From the future")
        hass.config_entries.async_update_entry(
            entry, version=HOUSE_ENTRY_VERSION + 1, minor_version=1
        )
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.MIGRATION_ERROR


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
