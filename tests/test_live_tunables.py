"""Live tunables: number entities and gate visibility.

The Mode select moved to tests/test_mode_select.py (P5 flip).
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle, window_settings

COVER = "cover.test_cover"


def _entry(hass, climate=False, **extra):
    options = {
        **COMMON_OPTIONS,
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_ENTITIES: [COVER],
        CONF_DELTA_TIME: 0,
        **extra,
    }
    if climate:
        options.update(
            {
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: "sensor.indoor",
                CONF_TEMP_LOW: 21,
                CONF_TEMP_HIGH: 25,
            }
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Tunable Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    window = WindowHandle(hass, COVER)  # records the startup command
    hass.states.async_set(COVER, "open", {"current_position": 60})
    hass.states.async_set("sensor.indoor", "22.0")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return window


def _entity_id(hass, platform, unique_id):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


class TestNumberEntities:
    async def test_geometry_numbers_created_for_blinds(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        for key in (
            "eye_height",
            "occupied_distance",
            "overhang_depth",
            "overhang_height",
            "privacy_offset",
        ):
            assert _entity_id(hass, "number", f"{entry.entry_id}_number_{key}"), key

    async def test_temp_numbers_only_with_climate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)  # climate off
        await _setup(hass, entry)
        assert _entity_id(hass, "number", f"{entry.entry_id}_number_temp_low") is None

    async def test_temp_numbers_with_climate_show_defaults(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass, climate=True)
        await _setup(hass, entry)
        eid = _entity_id(hass, "number", f"{entry.entry_id}_number_temp_low")
        assert hass.states.get(eid).state == "21"

    async def test_unset_geometry_shows_unknown_not_zero(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _entity_id(hass, "number", f"{entry.entry_id}_number_eye_height")
        assert hass.states.get(eid).state == "unknown"

    async def test_setting_number_persists_and_reloads(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        window = await _setup(hass, entry)
        eid = _entity_id(hass, "number", f"{entry.entry_id}_number_eye_height")

        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": eid, "value": 1.2},
            blocking=True,
        )
        await hass.async_block_till_done()

        # The window's own value (P5 flip: a window override), and what
        # it now acts on.
        assert (await window_settings(hass, entry.entry_id))[CONF_EYE_HEIGHT] == 1.2
        assert entry.state is ConfigEntryState.LOADED
        assert window.available
        assert hass.states.get(eid).state == "1.2"

    @pytest.mark.parametrize(
        ("units", "low", "high", "unit", "low_range", "high_range"),
        [
            (METRIC_SYSTEM, 21, 25, "°C", (5, 30), (10, 40)),
            (US_CUSTOMARY_SYSTEM, 72, 75, "°F", (40, 90), (50, 100)),
        ],
        ids=["celsius", "fahrenheit"],
    )
    async def test_regression_threshold_numbers_follow_unit_system(
        self,
        hass,
        cover_calls_stub,
        mock_sun_entity,
        units,
        low,
        high,
        unit,
        low_range,
        high_range,
    ):
        """The threshold numbers show HA's temperature unit and fit its range.

        Thresholds are stored and compared in HA's unit (v1.13.5), but the
        Heating/Cooling threshold numbers kept a fixed °C unit and a 5-30 /
        10-40 range: a °F house read "72 °C" and could not set 70.5.
        """
        hass.config.units = units
        entry = _entry(
            hass,
            **{
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: "sensor.indoor",
                CONF_TEMP_LOW: low,
                CONF_TEMP_HIGH: high,
            },
        )
        await _setup(hass, entry)

        shown = {}
        for key in ("temp_low", "temp_high"):
            eid = _entity_id(hass, "number", f"{entry.entry_id}_number_{key}")
            state = hass.states.get(eid)
            shown[key] = (
                state.state,
                state.attributes["unit_of_measurement"],
                (state.attributes["min"], state.attributes["max"]),
                state.attributes["step"],
            )
        assert shown == {
            "temp_low": (str(low), unit, low_range, 0.5),
            "temp_high": (str(high), unit, high_range, 0.5),
        }

        # A value inside the unit's range is accepted and stored as given:
        # the entity never converts the stored system-unit value.
        new_low = low - 1.5
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": _entity_id(
                    hass, "number", f"{entry.entry_id}_number_temp_low"
                ),
                "value": new_low,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        assert (await window_settings(hass, entry.entry_id))[CONF_TEMP_LOW] == new_low


class TestGateVisibility:
    async def test_blocked_move_names_the_gate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        """Quiet hours block a tracking move -> attribute says so."""
        entry = _entry(
            hass,
            **{CONF_QUIET_START: "00:00:00", CONF_QUIET_END: "23:59:00"},
        )
        window = await _setup(hass, entry)
        # The fixed first refresh commands a startup position (it bypasses
        # the quiet-hours gate by design); land the cover on that target so
        # the in-flight travel window cannot mask the gate under test.
        hass.states.async_set(
            COVER,
            "open",
            {"current_position": window.last_command},
        )
        await hass.async_block_till_done()
        calls = async_mock_service(hass, "cover", "set_cover_position")

        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
        )
        await hass.async_block_till_done()

        assert calls == []
        assert window.move_blocked_by == "quiet_hours"

    async def test_allowed_move_clears_the_gate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        window = await _setup(hass, entry)
        # Land the startup move (fixed first refresh) so its travel window
        # clears and the nudge below is judged by the ordinary gates.
        hass.states.async_set(
            COVER,
            "open",
            {"current_position": window.last_command},
        )
        await hass.async_block_till_done()
        cover_calls_stub = async_mock_service(hass, "cover", "set_cover_position")

        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
        )
        await hass.async_block_till_done()

        assert len(cover_calls_stub) == 1
        assert window.attributes["move_blocked_by"] == {}


@pytest.fixture
def cover_calls_stub(hass):
    return async_mock_service(hass, "cover", "set_cover_position")
