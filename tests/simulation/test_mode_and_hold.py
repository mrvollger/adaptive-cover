"""Mode (auto / hold / off) and Hold over a simulated day (P5 flip).

The window's Mode select is its control state: ``hold`` is a manual
override with an expiry (a detected move sets it for the override
duration; ``adaptive_cover.hold`` for a given one, optionally after moving
the covers), ``off`` means no moves and no manual-move detection.

Observed through the timeline, the Mode select (``window.mode``,
``window.hold_until``) and the Manual override sensor only.
"""

from __future__ import annotations

import datetime as dt

from custom_components.adaptive_cover.const import CONF_MANUAL_OVERRIDE_DURATION

from .harness import SimHouse

SHADE = "cover.shade"
# 2026-03-20 in SLC: the window wants 0 % until the sun comes round (~08:00)
# and ~28 % through the day.
DATE = "2026-03-20"
OFFICE = ("cover.office_east", "cover.office_north")
DEN = "cover.den_south"
TWO_HOURS = {CONF_MANUAL_OVERRIDE_DURATION: {"hours": 2}}


def _local_iso(house: SimHouse, hhmm: str) -> str:
    return house.local(hhmm).isoformat()


async def test_hold_area_office_for_four_hours(hass, freezer):
    """The plan's meeting: close the office and hold it for 4 h, in one call.

    ``adaptive_cover.hold(area: office, 4 h, position: 0)`` replaces the
    live house's close + manual-override timer in ``automation.meeting``.
    The office covers close at once and stay closed for the full 4 h, well
    past the 2 h override duration; the den is neither moved nor held. When
    the hold ends the office is back in auto and returns to its target.
    """
    house = await SimHouse.create(
        hass, freezer, date=DATE, covers=[*OFFICE, DEN], options=TWO_HOURS
    )
    office = house.place(OFFICE[0], "Office", floor="Upstairs")
    house.place(OFFICE[1], "Office", floor="Upstairs")
    house.place(DEN, "Den", floor="Downstairs")
    await house.advance_to("10:00")

    await house.hold(area_id=office, duration={"hours": 4}, position=0)

    for cover in OFFICE:
        window = house.window(cover)
        assert [m.position for m in house.auto_moves(cover, since="10:00")] == [0]
        assert window.moves[-1]["source"] == "hold"
        assert window.mode == "hold"
        assert window.hold_until == _local_iso(house, "14:00")
    assert house.window(DEN).mode == "auto"
    assert house.window(DEN).hold_until is None
    assert house.auto_moves(DEN, since="10:00") == []

    await house.advance_to("13:55")
    for cover in OFFICE:
        assert house.auto_moves(cover, since="10:01") == [], (
            "the office hold ended before its 4 h (the 2 h override duration?)"
        )
        assert house.position(cover) == 0
        assert house.window(cover).mode == "hold"
    assert house.window(DEN).mode == "auto"
    assert house.position(DEN) == house.window(DEN).target

    await house.advance_to("14:10")
    for cover in OFFICE:
        window = house.window(cover)
        assert window.mode == "auto"
        assert window.hold_until is None
        resumed = house.auto_moves(cover, since="14:00")
        assert resumed and resumed[-1].position == window.target
    await house.teardown()


async def test_detected_move_holds_until_the_override_ends(hass, freezer):
    """A remote move sets hold for the override duration; then back to auto."""
    house = await SimHouse.create(hass, freezer, date=DATE, options=TWO_HOURS)
    window = house.window()
    await house.advance_to("11:00")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:05")

    assert window.mode == "hold"
    until = dt.datetime.fromisoformat(window.hold_until)
    assert until == house.local("11:00") + dt.timedelta(hours=2)

    await house.advance_to("12:55")
    assert house.auto_moves(SHADE, since="11:01") == []
    assert window.mode == "hold"

    await house.advance_to("13:10")
    assert window.mode == "auto"
    assert not window.manual_override
    resumed = house.auto_moves(SHADE, since="13:00")
    assert resumed and resumed[-1].position == window.target
    await house.teardown()


async def test_selected_hold_keeps_the_cover_for_the_override_duration(hass, freezer):
    """Picking hold holds the cover where it is, for the override duration.

    Held at 07:30 while the window still wants 0 %; the sun comes round at
    ~08:00, but the cover stays put until the hold ends at 09:30.
    """
    house = await SimHouse.create(hass, freezer, date=DATE, options=TWO_HOURS)
    window = house.window()
    await house.advance_to("07:30")
    parked = house.position(SHADE)

    await house.select_option("mode_select", "hold")
    assert window.mode == "hold"
    assert window.hold_until == _local_iso(house, "09:30")

    await house.advance_to("09:25")
    assert window.target != parked, "the sun should have come round"
    assert house.auto_moves(SHADE, since="07:30") == []
    assert house.position(SHADE) == parked

    await house.advance_to("09:40")
    assert window.mode == "auto"
    resumed = house.auto_moves(SHADE, since="09:30")
    assert resumed and resumed[-1].position == window.target
    await house.teardown()


async def test_off_blocks_moves_and_detection(hass, freezer):
    """Off: the sun does not move the cover and a person's move is no hold."""
    house = await SimHouse.create(hass, freezer, date=DATE, options=TWO_HOURS)
    window = house.window()
    await house.advance_to("10:00")
    await house.toggle("toggle_control", False)  # Mode off (SimHouse maps it)
    assert window.mode == "off"

    await house.advance_to("10:30")
    await house.user_moves(SHADE, 20, via="remote")
    await house.advance_to("12:00")
    assert house.auto_moves(SHADE, since="10:00") == []
    assert house.position(SHADE) == 20
    assert window.mode == "off"
    assert not window.manual_override, "Mode off must not detect manual moves"

    await house.select_option("mode_select", "auto")
    moves = house.auto_moves(SHADE, since="12:00")
    assert moves and moves[-1].position == window.target, (
        "Auto from off commands the target at once"
    )
    assert window.mode == "auto"
    await house.teardown()


async def test_hold_survives_a_restart(hass, freezer):
    """A hold survives an HA restart (restored from the Mode) and ends on time.

    The restart is cold: the in-memory override store is gone, as in a real
    process restart, so the hold comes back from the Mode select's state.
    """
    house = await SimHouse.create(hass, freezer, date=DATE, options=TWO_HOURS)
    window = house.window()
    await house.advance_to("07:30")
    await house.hold(duration={"hours": 3})
    assert window.hold_until == _local_iso(house, "10:30")

    await house.restart(at="08:30", cold=True)
    assert window.mode == "hold"
    assert window.manual_override
    assert window.hold_until == _local_iso(house, "10:30")

    await house.advance_to("10:25")
    assert house.auto_moves(SHADE, since="07:30") == [], (
        "the restarted window walked the hold back"
    )

    await house.advance_to("10:40")
    assert window.mode == "auto"
    resumed = house.auto_moves(SHADE, since="10:30")
    assert resumed and resumed[-1].position == window.target
    await house.teardown()


async def test_off_survives_a_restart(hass, freezer):
    """Off comes back as off after a cold restart: no startup move."""
    house = await SimHouse.create(hass, freezer, date=DATE)
    window = house.window()
    await house.advance_to("09:00")
    await house.toggle("toggle_control", False)

    await house.restart(at="12:00", cold=True)
    assert window.mode == "off"
    await house.advance_to("13:00")
    assert house.auto_moves(SHADE, since="09:00") == []
    await house.teardown()
