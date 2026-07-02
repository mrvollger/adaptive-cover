"""Live tunables: number entities, the mode select, and gate visibility."""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er
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
    hass.states.async_set(COVER, "open", {"current_position": 60})
    hass.states.async_set("sensor.indoor", "22.0")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass, platform, unique_id):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


class TestNumberEntities:
    async def test_geometry_numbers_created_for_blinds(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        for key in ("eye_height", "occupied_distance", "overhang_depth",
                    "overhang_height", "privacy_offset"):
            assert _entity_id(hass, "number", f"{entry.entry_id}_number_{key}"), key

    async def test_temp_numbers_only_with_climate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)  # climate off
        await _setup(hass, entry)
        assert (
            _entity_id(hass, "number", f"{entry.entry_id}_number_temp_low") is None
        )

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
        await _setup(hass, entry)
        eid = _entity_id(hass, "number", f"{entry.entry_id}_number_eye_height")

        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": eid, "value": 1.2},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert entry.options[CONF_EYE_HEIGHT] == 1.2
        # Entry reloaded: the new coordinator sees the option too
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.config_entry.options[CONF_EYE_HEIGHT] == 1.2
        assert hass.states.get(eid).state == "1.2"


class TestModeSelect:
    async def test_options_without_climate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _entity_id(hass, "select", f"{entry.entry_id}_mode_select")
        state = hass.states.get(eid)
        assert state.attributes["options"] == ["Manual", "Sun tracking"]
        assert state.state == "Sun tracking"  # control restores on

    async def test_options_with_climate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass, climate=True)
        await _setup(hass, entry)
        eid = _entity_id(hass, "select", f"{entry.entry_id}_mode_select")
        state = hass.states.get(eid)
        assert state.attributes["options"] == [
            "Manual",
            "Sun tracking",
            "Sun + climate",
        ]
        assert state.state == "Sun + climate"  # climate switch restores on

    async def test_manual_mode_turns_control_off(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _entity_id(hass, "select", f"{entry.entry_id}_mode_select")

        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": eid, "option": "Manual"},
            blocking=True,
        )
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.control_toggle is False
        assert hass.states.get(eid).state == "Manual"

    async def test_sun_tracking_mode_disables_climate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass, climate=True)
        await _setup(hass, entry)
        eid = _entity_id(hass, "select", f"{entry.entry_id}_mode_select")

        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": eid, "option": "Sun tracking"},
            blocking=True,
        )
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.control_toggle is True
        assert coordinator.switch_mode is False
        assert hass.states.get(eid).state == "Sun tracking"


class TestGateVisibility:
    async def test_blocked_move_names_the_gate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        """Quiet hours block a tracking move -> attribute says so."""
        entry = _entry(
            hass,
            **{CONF_QUIET_START: "00:00:00", CONF_QUIET_END: "23:59:00"},
        )
        await _setup(hass, entry)

        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
        )
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert cover_calls_stub == []
        assert (
            coordinator.data.attributes["move_blocked_by"].get(COVER)
            == "quiet_hours"
        )

    async def test_allowed_move_clears_the_gate(
        self, hass, cover_calls_stub, mock_sun_entity
    ):
        entry = _entry(hass)
        await _setup(hass, entry)
        cover_calls_stub = async_mock_service(hass, "cover", "set_cover_position")

        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 44.0}
        )
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert len(cover_calls_stub) == 1
        assert coordinator.data.attributes["move_blocked_by"] == {}


@pytest.fixture
def cover_calls_stub(hass):
    return async_mock_service(hass, "cover", "set_cover_position")
