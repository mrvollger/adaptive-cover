"""Live tunables: gate visibility.

The Mode select moved to tests/test_mode_select.py and the numbers to the
house (tests/test_house_settings.py) in the P5 flip.
"""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
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

from .house_model import mock_window_entry
from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle

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
    entry = mock_window_entry(
        hass,
        data={"name": "Tunable Test", CONF_SENSOR_TYPE: SensorType.BLIND},
        options=options,
    )
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
