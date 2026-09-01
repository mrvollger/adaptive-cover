"""Scenario tests for the two reported house symptoms.

1. Manual overrides must survive sun-angle-driven updates for the whole
   configured override duration.
2. Shades must reach the sunset/end-of-schedule position every evening.

These run the REAL integration against the simulated house (see harness.py).
"""

from custom_components.adaptive_cover.const import (
    CONF_END_TIME,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

SHADE = "cover.shade"


async def make_house(hass, freezer, *, options=None, step_minutes=5):
    return await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options=options,
        step_minutes=step_minutes,
    )


# --------------------------------------------------------------- symptom 1


async def test_remote_override_respected_for_duration(hass, freezer):
    """A remote-initiated move must block auto control for the duration."""
    house = await make_house(hass, freezer)
    await house.advance_to("11:00")
    await house.advance_to("11:10")  # let any in-flight travel settle

    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:20")  # override duration is 15 min

    moves = house.auto_moves(SHADE, since="11:10")
    assert moves == [], f"auto moves during manual override: {moves}"
    assert house.position(SHADE) == 100
    await house.teardown()


async def test_dashboard_override_respected_for_duration(hass, freezer):
    """Same but the human used the HA dashboard (user context)."""
    house = await make_house(hass, freezer)
    await house.advance_to("11:10")

    await house.user_moves(SHADE, 100, via="dashboard")
    await house.advance_to("11:20")

    moves = house.auto_moves(SHADE, since="11:10")
    assert moves == [], f"auto moves during manual override: {moves}"
    await house.teardown()


async def test_override_during_travel_window_not_swallowed(hass, freezer):
    """A human move right after an integration command must still latch.

    The integration sends a command; while the shade is still travelling
    (wait_for_target window) the human grabs the remote and moves it
    somewhere else. That human move must latch a manual override — it must
    not be misread as the motor echo of the integration's own command.
    """
    house = await make_house(hass, freezer, step_minutes=1)
    await house.advance_to("07:00")

    # Find a fresh integration command, then interrupt it mid-travel
    # (travel takes 120s; ticks are 1 min, so the shade is still moving).
    # Sunrise-era moves are frequent, so one arrives within the sweep.
    before = len(house.auto_moves(SHADE))
    for _ in range(180):
        await house.tick()
        if len(house.auto_moves(SHADE)) > before:
            break
    assert len(house.auto_moves(SHADE)) > before, "no integration move by 10:00"
    await house.user_moves(SHADE, 100, via="remote")
    start = house.now

    # From the human act on, auto control must stand down for 15 minutes.
    for _ in range(15):
        await house.tick()
    moves = [m for m in house.auto_moves(SHADE) if m.time > start]
    assert moves == [], f"override was swallowed as motor echo; auto moves: {moves}"
    await house.teardown()


async def test_override_expires_after_configured_duration(hass, freezer):
    """The override holds for the configured duration, then auto resumes.

    User intent: a manual move wins for ~the configured window (their
    house: 1.5-2 h), after which adaptive control takes back over.
    """
    house = await make_house(
        hass,
        freezer,
        options={
            CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 30},
            CONF_MANUAL_OVERRIDE_RESET: False,
        },
    )
    await house.advance_to("11:10")
    await house.user_moves(SHADE, 100, via="remote")

    # Inside the 30-minute window: hands off.
    await house.advance_to("11:35")
    assert house.auto_moves(SHADE, since="11:10") == [], (
        "auto control moved the shade during the override window"
    )

    # Past expiry: adaptive control resumes and repositions the shade.
    await house.advance_to("13:00")
    resumed = house.auto_moves(SHADE, since="11:45")
    assert resumed, "auto control never resumed after the override expired"
    assert house.position(SHADE) == resumed[-1].position
    await house.teardown()


# --------------------------------------------------------------- symptom 2


async def test_end_time_close_fires(hass, freezer):
    """With a configured end time (before sunset) the shade must close then.

    End time 18:00 is well before sunset (~19:33 on the equinox in SLC), so
    the timed close is the only thing that can drive the shade to 0 then.
    """
    house = await make_house(
        hass,
        freezer,
        options={
            CONF_END_TIME: "18:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("19:00")
    closes = [
        m for m in house.auto_moves(SHADE, since="17:55") if m.position == 0
    ]
    assert closes, (
        "no close command at the configured end time; evening timeline: "
        f"{[e for e in house.timeline if e.time.hour >= 17]}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_sunset_close_fires_without_end_time(hass, freezer):
    """Without an end time, the shade must reach sunset_pos after sunset."""
    house = await make_house(hass, freezer)
    await house.advance_to("23:00")  # sunset 2026-03-20 SLC ~19:33
    assert house.position(SHADE) == 0, (
        f"shade at {house.position(SHADE)} after sunset; "
        f"evening moves: {house.auto_moves(SHADE, since='18:00')}"
    )
    await house.teardown()


async def test_end_time_close_fires_despite_manual_override(hass, freezer):
    """An afternoon manual override must not eat the end-of-day close.

    Override duration is 15 min; by 20:00 it long expired. Whatever the
    override history, the schedule close is the one move that must happen.
    """
    house = await make_house(
        hass,
        freezer,
        options={
            CONF_END_TIME: "20:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
            CONF_MANUAL_OVERRIDE_DURATION: {"minutes": 15},
            CONF_MANUAL_OVERRIDE_RESET: False,
        },
    )
    await house.advance_to("17:00")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("21:00")
    assert house.position(SHADE) == 0, (
        f"end-time close missed after manual override; evening timeline: "
        f"{[e for e in house.timeline if e.time.hour >= 19]}"
    )
    await house.teardown()


# The former test_end_time_close_retries_after_unavailable was vacuous: the
# fake cover service never raised for unavailable shades, so the pending-snap
# retry path it claimed to pin was never exercised. Its real replacement is
# tests/simulation/test_device_failures.py::test_pending_end_snap_real_retry,
# which makes the service call genuinely raise (kills mutation M16).
