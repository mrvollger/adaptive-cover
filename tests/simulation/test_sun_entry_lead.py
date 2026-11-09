"""Sun entry lead: the shade moves before the sun reaches the window.

A south window that sees the sun from azimuth 135 (FOV 45 deg east of
the normal, 90 west) on 2026-03-20 in SLC: with no lead the first sun
move comes when the sun crosses the FOV edge; with a 20-minute lead it
comes at least 15 minutes earlier (one 5-minute sim step of slack), to
the same entry position. Leaving the window is not led.
"""

import pytest

from custom_components.adaptive_cover.const import (
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_TIME,
    CONF_FOV_LEFT,
    CONF_SUN_ENTRY_LEAD,
)

from .harness import SimHouse

SHADE = "cover.shade"
OPTIONS = {CONF_FOV_LEFT: 45, CONF_DEFAULT_HEIGHT: 100, CONF_DELTA_TIME: 0}


async def _first_sun_move(hass, freezer, lead):
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={**OPTIONS, CONF_SUN_ENTRY_LEAD: lead},
    )
    await house.advance_to("13:00")
    moves = house.auto_moves(SHADE, since="06:00")
    entry = next((m for m in moves if m.position < 100), None)
    start_sun = house.sensor_value("start_sun")
    await house.teardown()
    return entry, start_sun


@pytest.mark.parametrize("lead", [20])
async def test_sun_entry_lead_moves_the_shade_early(hass, freezer, lead):
    plain, plain_start = await _first_sun_move(hass, freezer, 0)
    early, early_start = await _first_sun_move(hass, freezer, lead)

    assert plain is not None, "no sun move without a lead"
    assert early is not None, "no sun move with the lead"
    # The window's sun times are the sun's, lead or not.
    assert early_start == plain_start
    gained = (plain.time - early.time).total_seconds() / 60
    assert lead - 5 <= gained <= lead + 5, (plain.time, early.time)
