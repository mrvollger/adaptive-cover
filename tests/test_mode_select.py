"""The window Mode (auto / hold / off) and the hold service.

P5 flip (refactor plan, "Entity surface" and "Services"): the Mode select
is the source of truth for a window's control state and restores its own
state. ``adaptive_cover.hold`` is an entity service on it. Since v2.1 (P8)
the six window switches (hidden aliases since the flip) are gone, and the
select no longer falls back to the Toggle Control switch or maps its
pre-flip options.

Driven through public surfaces only: entity states, the registries, the
restore cache and real service calls.
"""

from __future__ import annotations

import datetime as dt

import pytest
import voluptuous as vol
from homeassistant.core import State
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .house_model import mock_window_entry
from .window_handle import WindowHandle

COVER = "cover.test_cover"
NOW = dt.datetime(2026, 3, 20, 18, 0, tzinfo=dt.UTC)  # 12:00 in Denver
DURATION = {"hours": 2}


def _entry(hass, *, climate: bool = False, **extra) -> MockConfigEntry:
    options = {
        **COMMON_OPTIONS,
        CONF_HEIGHT_WIN: 2.1,
        CONF_DISTANCE: 0.5,
        CONF_ENTITIES: [COVER],
        CONF_DELTA_TIME: 0,
        CONF_MANUAL_OVERRIDE_DURATION: DURATION,
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
    return mock_window_entry(
        hass, {"name": "Mode Test", CONF_SENSOR_TYPE: SensorType.BLIND}, options
    )


def _registry_id(hass, domain: str, entry: MockConfigEntry, suffix: str) -> str:
    """The entity id a window's entity gets (registered before setup)."""
    return (
        er.async_get(hass)
        .async_get_or_create(
            domain, DOMAIN, f"{entry.entry_id}_{suffix}", config_entry=entry
        )
        .entity_id
    )


async def _setup(hass, entry, *, position: int = 60) -> WindowHandle:
    window = WindowHandle(hass, COVER)  # records the startup command
    hass.states.async_set(COVER, "open", {"current_position": position})
    hass.states.async_set("sensor.indoor", "22.0")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return window


async def _land(hass, window: WindowHandle) -> None:
    """Report the cover at the last commanded position (its travel ends)."""
    hass.states.async_set(COVER, "open", {"current_position": window.last_command})
    await hass.async_block_till_done()


async def _select(hass, window: WindowHandle, option: str) -> None:
    await window.select_mode(option)


async def _hold(hass, target: dict, **fields) -> None:
    await hass.services.async_call(DOMAIN, "hold", {**target, **fields}, blocking=True)
    await hass.async_block_till_done()


def _iso(value: dt.datetime) -> str:
    return dt_util.as_local(value).isoformat()


@pytest.fixture
def frozen(freezer):
    freezer.move_to(NOW)
    return freezer


@pytest.fixture(autouse=True)
def cover_service(hass):
    """A cover service to command (a test re-mocks it to count calls)."""
    return async_mock_service(hass, "cover", "set_cover_position")


# ------------------------------------------------------------ the select


class TestOptions:
    @pytest.mark.parametrize("climate", [False, True])
    async def test_options_are_auto_hold_off(self, hass, mock_sun_entity, climate):
        """Climate no longer adds an option: it is a house setting now."""
        window = await _setup(hass, _entry(hass, climate=climate))
        state = window.state("mode")
        assert state.attributes["options"] == ["auto", "hold", "off"]
        assert state.state == "auto"
        assert state.attributes["until"] is None

    async def test_off_stops_moves_and_auto_brings_them_back(
        self, hass, mock_sun_entity
    ):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)
        await _select(hass, window, "off")
        assert window.mode == "off"

        calls = async_mock_service(hass, "cover", "set_cover_position")
        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 30.0}
        )
        await hass.async_block_till_done()
        assert calls == [], "Mode off must not move the cover"

        await _select(hass, window, "auto")
        assert window.mode == "auto"
        assert [call.data["position"] for call in calls] == [window.target], (
            "Auto from off must command the target at once"
        )

    async def test_off_ignores_manual_moves(self, hass, mock_sun_entity):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)
        await _select(hass, window, "off")

        hass.states.async_set(COVER, "open", {"current_position": 5})
        await hass.async_block_till_done()
        assert window.mode == "off"
        assert not window.manual_override, "Mode off must not detect manual moves"


# ------------------------------------------------------------ hold


class TestHold:
    async def test_selecting_hold_holds_in_place_for_the_override_duration(
        self, hass, mock_sun_entity, frozen
    ):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)
        calls = async_mock_service(hass, "cover", "set_cover_position")

        await _select(hass, window, "hold")

        assert calls == [], "Hold keeps the cover where it is"
        assert window.mode == "hold"
        assert window.manual_override
        assert window.hold_until == _iso(NOW + dt.timedelta(**DURATION))
        assert window.attributes["override_until"] == window.hold_until

    async def test_a_detected_move_is_a_hold_until_the_override_ends(
        self, hass, mock_sun_entity, frozen
    ):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)

        hass.states.async_set(COVER, "open", {"current_position": 5})
        await hass.async_block_till_done()

        assert window.mode == "hold"
        assert window.hold_until == _iso(NOW + dt.timedelta(**DURATION))

    async def test_hold_service_moves_then_holds_for_its_duration(
        self, hass, mock_sun_entity, frozen
    ):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)
        calls = async_mock_service(hass, "cover", "set_cover_position")

        await _hold(
            hass,
            {"entity_id": window.entity_id("mode")},
            duration={"hours": 4},
            position=0,
        )

        assert [call.data["position"] for call in calls] == [0]
        assert window.moves[-1]["source"] == "hold"
        assert window.mode == "hold"
        assert window.hold_until == _iso(NOW + dt.timedelta(hours=4))

        # Landing on the position we commanded is not a manual move, and
        # the sun does not walk the hold back.
        hass.states.async_set(COVER, "closed", {"current_position": 0})
        hass.states.async_set(
            "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 30.0}
        )
        await hass.async_block_till_done()
        assert [call.data["position"] for call in calls] == [0]
        assert window.hold_until == _iso(NOW + dt.timedelta(hours=4))

    async def test_hold_service_targets_an_area(self, hass, mock_sun_entity, frozen):
        entry = _entry(hass)
        window = await _setup(hass, entry)
        area = ar.async_get(hass).async_create("Office")
        devices = dr.async_get(hass)
        device = devices.async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), config_entry_id=entry.entry_id
        )
        devices.async_update_device(device.id, area_id=area.id)

        await _hold(hass, {"area_id": area.id}, duration={"minutes": 30})

        assert window.mode == "hold"
        assert window.hold_until == _iso(NOW + dt.timedelta(minutes=30))

    async def test_hold_from_off_comes_back_in_auto(
        self, hass, mock_sun_entity, frozen
    ):
        window = await _setup(hass, _entry(hass))
        await _select(hass, window, "off")
        await _hold(hass, {"entity_id": window.entity_id("mode")})
        assert window.mode == "hold"
        assert window.hold_until == _iso(NOW + dt.timedelta(**DURATION))

    @pytest.mark.parametrize(
        "fields",
        [{"position": 101}, {"position": -1}, {"duration": "-01:00:00"}],
    )
    async def test_hold_service_rejects_bad_input(self, hass, mock_sun_entity, fields):
        window = await _setup(hass, _entry(hass))
        with pytest.raises(vol.Invalid):
            await _hold(hass, {"entity_id": window.entity_id("mode")}, **fields)
        assert window.mode == "auto"

    async def test_return_to_auto_ends_a_hold_and_turns_off_into_auto(
        self, hass, mock_sun_entity
    ):
        window = await _setup(hass, _entry(hass))
        await _land(hass, window)
        await _select(hass, window, "hold")
        # Someone moves the held shade away from the target.
        hass.states.async_set(COVER, "open", {"current_position": 5})
        await hass.async_block_till_done()
        assert window.mode == "hold"
        calls = async_mock_service(hass, "cover", "set_cover_position")

        await window.press()
        assert window.mode == "auto"
        assert [call.data["position"] for call in calls] == [window.target]

        await _select(hass, window, "off")
        await window.press()
        assert window.mode == "auto", "Return to auto turns an off window on"


# ------------------------------------------------------------ restore


class TestRestore:
    async def test_an_old_toggle_control_state_is_not_read(self, hass, mock_sun_entity):
        """No Mode state: auto, whatever the gone Toggle Control switch had (P8)."""
        entry = _entry(hass)
        switch = _registry_id(hass, "switch", entry, "Toggle Control")
        mock_restore_cache(hass, [State(switch, "off")])

        window = await _setup(hass, entry)

        assert window.mode == "auto"
        assert window.last_command == window.target

    async def test_a_restored_off_does_not_move_at_startup(self, hass, mock_sun_entity):
        entry = _entry(hass)
        mode = _registry_id(hass, "select", entry, "mode_select")
        mock_restore_cache(hass, [State(mode, "off")])
        calls = async_mock_service(hass, "cover", "set_cover_position")

        window = await _setup(hass, entry)

        assert window.mode == "off"
        assert calls == [], "a window restored off must not move at startup"

    async def test_the_mode_wins_over_the_switch(self, hass, mock_sun_entity):
        entry = _entry(hass)
        switch = _registry_id(hass, "switch", entry, "Toggle Control")
        mode = _registry_id(hass, "select", entry, "mode_select")
        mock_restore_cache(hass, [State(switch, "off"), State(mode, "auto")])

        window = await _setup(hass, entry)
        assert window.mode == "auto"

    async def test_a_restored_hold_lasts_until_its_end(
        self, hass, mock_sun_entity, frozen
    ):
        entry = _entry(hass)
        mode = _registry_id(hass, "select", entry, "mode_select")
        until = NOW + dt.timedelta(minutes=45)
        mock_restore_cache(hass, [State(mode, "hold", {"until": _iso(until)})])
        calls = async_mock_service(hass, "cover", "set_cover_position")

        window = await _setup(hass, entry)

        assert window.mode == "hold"
        assert window.hold_until == _iso(until)
        assert calls == [], "a held window must not move at startup"

    async def test_a_hold_that_ended_while_down_restores_as_auto(
        self, hass, mock_sun_entity, frozen
    ):
        entry = _entry(hass)
        mode = _registry_id(hass, "select", entry, "mode_select")
        until = NOW - dt.timedelta(minutes=1)
        mock_restore_cache(hass, [State(mode, "hold", {"until": _iso(until)})])

        window = await _setup(hass, entry)
        assert window.mode == "auto"
        assert window.last_command == window.target


# ------------------------------------------------------------ no switches


class TestNoSwitches:
    async def test_a_window_has_no_switch_entities(self, hass, mock_sun_entity):
        """The six switch aliases are gone (P8): Mode and the house settings."""
        entry = _entry(hass, climate=True)
        window = await _setup(hass, entry)
        prefix = f"{window.window_key}_"
        switches = [
            row.entity_id
            for row in er.async_get(hass).entities.values()
            if row.platform == DOMAIN
            and row.domain == "switch"
            and row.unique_id.startswith(prefix)
        ]
        assert switches == []
