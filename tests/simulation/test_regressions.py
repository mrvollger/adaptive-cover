"""Simulation regressions for coordinator fixes (2026-09 bug hunt)."""

import datetime as dt

from astral import sun as astral_sun
from homeassistant.util import dt as dt_util

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
