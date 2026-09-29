"""Simulation regressions for coordinator fixes (2026-09 bug hunt)."""

import datetime as dt

import pytest
from astral import sun as astral_sun
from homeassistant.util import dt as dt_util

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_MAX_ELEVATION,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

A = "cover.left"
B = "cover.right"


async def test_regression_group_remote_latches_both_covers(hass, freezer):
    """Two covers moved in the same instant must BOTH latch manual.

    A single shared state_change_data slot dropped one event when a
    room-group remote moved several covers at once.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20", covers=[A, B])
    await house.advance_to("11:10")

    await house.user_moves(A, 100, via="remote")
    await house.user_moves(B, 100, via="remote")
    await house.advance_to("11:20")

    assert house.window(A).is_manual, "left cover override dropped"
    assert house.window(B).is_manual, "right cover override dropped"
    assert house.auto_moves(A, since="11:10") == []
    assert house.auto_moves(B, since="11:10") == []
    await house.teardown()


async def test_regression_override_clears_on_new_day(hass, freezer):
    """Day rollover is a safety net: even an absurdly long override
    duration cannot carry a stale override into the next solar day."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={"manual_override_duration": {"hours": 48}},
    )
    await house.advance_to("15:00")
    await house.user_moves("cover.shade", 100, via="remote")
    await house.advance_to("23:00")
    assert house.window("cover.shade").is_manual

    # Cross midnight into the next solar day: auto control resumes.
    await house.advance_to("10:00")  # next day
    assert not house.window("cover.shade").is_manual
    await house.teardown()


async def test_regression_overrides_survive_entry_reload(hass, freezer):
    """Options reloads rebuild the coordinator; overrides must survive."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:10")
    await house.user_moves("cover.shade", 100, via="remote")
    assert house.window("cover.shade").is_manual

    # The user opens the options dialog and saves it unchanged: the entry
    # reloads and the coordinator is rebuilt.
    await house.set_options()

    assert house.window("cover.shade").is_manual, (
        "entry reload wiped the manual override"
    )
    await house.advance_to("11:25")
    assert house.auto_moves("cover.shade", since="11:10") == []
    await house.teardown()


async def test_regression_next_change_uses_local_date(hass, freezer):
    """Evening Next State Change names TOMORROW's sunrise, not the day after.

    "Tomorrow" was derived from the UTC date. From 18:00 MDT on the UTC
    date is already tomorrow, so at 21:11 the sensor named the sunrise two
    local days out. Tomorrow is the configured local date plus one.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("21:10")  # 03:10 UTC on 03-21

    attrs = house.window().state("next_change").attributes
    tomorrow_sunrise = astral_sun.sunrise(house.sun_data.observer, dt.date(2026, 3, 21))
    assert attrs["event"] == "Sunrise + offset"
    expected = dt_util.parse_datetime(attrs["expected_time"])
    assert dt_util.as_local(expected).date() == dt.date(2026, 3, 21)
    assert expected == tomorrow_sunrise
    await house.teardown()


@pytest.mark.parametrize(
    ("start", "snap"), [(99, 100), (1, 0)], ids=["99_to_100", "1_to_0"]
)
async def test_regression_small_snap_move_sent_once(hass, freezer, start, snap):
    """A small move to a snap position is commanded exactly once.

    The shade's 'opening'/'closing' report still carries the OLD position,
    which is within TARGET_TOLERANCE of a 1% target. That intermediate
    report cleared the in-flight latch as "arrived", so the next refresh
    (a sun tick one minute later) re-sent the same target: snap positions
    bypass the delta and time gates. Arrival needs a settled report.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        start_at="10:00",
        step_minutes=1,  # sun ticks land inside the 120 s travel window
        initial_position=start,
        # A north window: the sun never enters, the default rules all day.
        options={
            CONF_AZIMUTH: 0,
            CONF_FOV_LEFT: 10,
            CONF_FOV_RIGHT: 10,
            CONF_DEFAULT_HEIGHT: snap,
        },
    )
    await house.advance_to("10:10")

    commands = [ev.position for ev in house.auto_moves("cover.shade")]
    assert commands == [snap]
    assert house.position("cover.shade") == snap
    await house.teardown()


async def test_regression_dusk_no_open_then_close(hass, freezer):
    """Leanne's door, summer solstice: no open-then-close at dusk.

    The sun leaves the 235° window at about 20:15 MDT; the sunset position
    (5%) begins at sunset - 30 min, about 20:32. The shade used to open to
    the 97% default at 20:15 and close to 5% at 20:35. With the sun gone
    and dusk less than DUSK_LEAD away, it goes straight to the sunset
    position.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-06-21",
        start_at="16:00",
        initial_position=97,
        options={
            CONF_AZIMUTH: 235,
            CONF_FOV_LEFT: 60,
            CONF_FOV_RIGHT: 60,
            CONF_MAX_ELEVATION: 50,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.2,
            CONF_DEFAULT_HEIGHT: 97,
            CONF_SUNSET_POS: 5,
            CONF_SUNSET_OFFSET: -30,
        },
    )
    await house.advance_to("19:45")
    assert house.window().target < 10  # tracking the low evening sun
    await house.advance_to("21:30")

    evening = [ev.position for ev in house.auto_moves("cover.shade", since="19:50")]
    assert 97 not in evening, f"opened to the default before dusk: {evening}"
    assert evening[-1] == 5
    assert house.window().target == 5
    await house.teardown()


async def test_regression_unload_cancels_arrival_poll(hass, freezer):
    """Unloading an entry cancels its arrival poll.

    Every command arms a 125 s poll. Unload never cancelled it, so a
    removed or reloading entry still polled the cover two minutes later
    (and HA 2026.8's test harness reported ~105 lingering timers).
    """
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", start_at="10:00", initial_position=100
    )
    assert house.auto_moves("cover.shade"), "no startup command, no poll armed"
    await hass.config_entries.async_unload(house.entry.entry_id)
    await hass.async_block_till_done()

    await house.advance_to("10:10")  # past the 125 s poll
    polls = [ev for ev in house.timeline if ev.kind == "poll"]
    assert polls == []
    await house.teardown()
