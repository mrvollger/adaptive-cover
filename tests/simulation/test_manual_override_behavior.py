"""Behavior-tier manual-override and multi-day scenarios (wp6).

Everything drives the REAL integration through public seams only: the
simulated house (state events, service calls), real switch/button entities,
the manual-override binary sensor, and the solar-time sensors. Override
state is never read from coordinator.manager — latching and clearing are
proven via subsequent auto_moves on the timeline and entity states.

Roadmap: wp6-manual-override-multiday. Kills mutations M08-M12.
"""

import datetime as dt

from custom_components.adaptive_cover.const import (
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
)

from .harness import SimHouse

SHADE = "cover.shade"

LONG_OVERRIDE = {CONF_MANUAL_OVERRIDE_DURATION: {"hours": 4}}


async def settle(house, ticks: int = 2) -> None:
    """Let any in-flight travel land (travel is 120s; ticks are >=1 min)."""
    for _ in range(ticks):
        await house.tick()


def manual_binary(house) -> str:
    """State of the manual-override binary sensor ("on"/"off")."""
    return house.entity("binary_sensor", "manual_override").state


def manual_list(house):
    """The manual_controlled attribute of the binary sensor."""
    return house.entity("binary_sensor", "manual_override").attributes.get(
        "manual_controlled"
    )


def moves_on_or_after(house, entity_id, when: dt.datetime):
    """Integration moves at/after a tz-aware datetime (multi-day safe)."""
    return [ev for ev in house.auto_moves(entity_id) if ev.time >= when]


# ------------------------------------------------------- manual threshold


async def test_manual_threshold_small_nudge_keeps_auto(hass, freezer):
    """A remote nudge below the threshold must NOT stop auto control.

    ignore_intermediate isolates the landing-mismatch latch path, where the
    manual threshold applies (motion-start latching ignores magnitude by
    design — a motor spinning IS a human act; magnitude only exists once
    the landing report arrives).
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_MANUAL_IGNORE_INTERMEDIATE: True,
            CONF_MANUAL_THRESHOLD: 10,
            **LONG_OVERRIDE,
        },
    )
    await house.advance_to("11:30")
    await settle(house)

    computed = int(house.sensor_value())
    nudge = computed + 6 if computed <= 80 else computed - 6
    await house.user_moves(SHADE, nudge, via="remote")
    nudged_at = house.now

    await house.advance_to("12:10")
    assert moves_on_or_after(house, SHADE, nudged_at), (
        "a below-threshold nudge stopped auto control: no integration "
        f"command followed it; timeline tail: {house.timeline[-8:]}"
    )
    assert manual_binary(house) == "off", (
        "a below-threshold nudge latched a manual override"
    )
    await house.teardown()


async def test_manual_threshold_large_move_latches(hass, freezer):
    """A remote move beyond the threshold latches: auto stands down."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_MANUAL_IGNORE_INTERMEDIATE: True,
            CONF_MANUAL_THRESHOLD: 10,
            **LONG_OVERRIDE,
        },
    )
    await house.advance_to("13:00")
    await settle(house)

    computed = int(house.sensor_value())
    target = computed + 15 if computed <= 80 else computed - 15
    await house.user_moves(SHADE, target, via="remote")
    await settle(house)  # landing report arrives -> latch
    latched_at = house.now

    assert manual_binary(house) == "on", (
        "an above-threshold remote move never latched a manual override"
    )
    await house.advance_to("14:30")
    reverts = moves_on_or_after(house, SHADE, latched_at)
    assert reverts == [], (
        f"auto control moved the shade during a latched override: {reverts}"
    )
    assert house.position(SHADE) == target
    await house.teardown()


# ------------------------------------------- manual switch off / reloads


async def test_manual_switch_off_clears_override(hass, freezer):
    """Turning the Manual Override switch entity off clears the latch."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", options=LONG_OVERRIDE
    )
    await house.advance_to("11:10")
    await settle(house)

    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now
    await house.advance_to("11:40")
    assert moves_on_or_after(house, SHADE, latched_at) == [], (
        "override never latched before the switch test could run"
    )
    assert manual_binary(house) == "on"

    await house.toggle("manual_override", False)
    cleared_at = house.now
    await house.advance_to("12:10")
    resumed = moves_on_or_after(house, SHADE, cleared_at)
    assert resumed, (
        "turning the manual-override switch off did not clear the "
        "override: auto control never re-commanded the cover"
    )
    assert manual_binary(house) == "off"
    assert house.position(SHADE) == resumed[-1].position
    await house.teardown()


async def test_reload_preserves_override(hass, freezer):
    """An options reload must NOT clear a live override (startup None state).

    During a reload the rebuilt coordinator sees the manual toggle as None
    (switches restore after the first refresh); only an EXPLICIT off may
    clear overrides. Pins the None branch a restart/toggle-off swap breaks.
    """
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", options=LONG_OVERRIDE
    )
    await house.advance_to("11:00")
    await settle(house)

    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now
    await house.advance_to("11:20")
    assert manual_binary(house) == "on"

    await house.set_options()  # the user saves the options dialog unchanged

    await house.advance_to("12:00")
    bulldozed = moves_on_or_after(house, SHADE, latched_at)
    assert bulldozed == [], (
        f"an options reload wiped a live manual override: {bulldozed}"
    )
    assert manual_binary(house) == "on"
    assert house.position(SHADE) == 100
    await house.teardown()


# ----------------------------------------------------------- reset button


async def test_reset_button_resumes_auto_control(hass, freezer):
    """Pressing the real button entity re-commands the overridden cover."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", options=LONG_OVERRIDE
    )
    await house.advance_to("11:10")
    await settle(house)

    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now
    await house.advance_to("11:30")
    assert moves_on_or_after(house, SHADE, latched_at) == []
    assert manual_binary(house) == "on"

    await house.press()  # Reset Manual Override
    resumed = moves_on_or_after(house, SHADE, latched_at)
    assert resumed, "reset button never re-commanded the overridden cover"
    await settle(house)
    assert house.position(SHADE) == resumed[-1].position
    assert manual_binary(house) == "off"
    await house.teardown()


async def test_reset_button_with_jammed_shade_returns_promptly(hass, freezer):
    """A jammed shade must not stall the reset past the travel timeout."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", options=LONG_OVERRIDE
    )
    await house.advance_to("12:00")
    await settle(house)

    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now
    await settle(house)  # the human move lands
    assert manual_binary(house) == "on"
    house.jam(SHADE)

    pressed_at = house.now
    await house.press()
    assert house.now - pressed_at <= dt.timedelta(minutes=6), (
        "reset press stalled far past the coordinator's travel timeout"
    )
    commanded = moves_on_or_after(house, SHADE, latched_at)
    assert commanded, "reset never sent a command to the jammed cover"
    await settle(house)
    assert manual_binary(house) == "off", (
        "override survived the reset because the jammed cover never landed"
    )
    # Auto control is back: the stuck shade keeps being (re-)commanded.
    resumed_from = house.now
    await house.advance_to("13:00")
    assert moves_on_or_after(house, SHADE, resumed_from), (
        "auto control never resumed after resetting a jammed cover"
    )
    await house.teardown()


# ------------------------------------------------- binary sensor & expiry


async def test_manual_override_binary_sensor(hass, freezer):
    """Binary sensor: off through normal tracking, on after a remote move,
    off (and auto resumed) once the configured duration expires.

    The morning checkpoints also pin that the integration's OWN landings
    never read as manual (an own-landing comparison flip lights the sensor
    all morning).
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    for checkpoint in ("08:00", "09:00", "10:00"):
        await house.advance_to(checkpoint)
        assert manual_binary(house) == "off", (
            f"manual override on at {checkpoint} with no human move: the "
            "integration's own landings are latching as manual"
        )
    assert manual_list(house) == []
    assert house.auto_moves(SHADE), "no morning tracking commands at all"

    await settle(house)
    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now
    await house.tick()
    assert manual_binary(house) == "on"
    assert manual_list(house) == [SHADE]

    # Default duration is 15 minutes; by 10:45 it expired and auto resumed.
    await house.advance_to("10:45")
    assert manual_binary(house) == "off", (
        "manual override still on 40+ minutes after a 15-minute duration"
    )
    assert manual_list(house) == []
    resumed = [
        ev
        for ev in moves_on_or_after(house, SHADE, latched_at)
        if ev.time >= latched_at + dt.timedelta(minutes=15)
    ]
    assert resumed, "auto control never resumed after the override expired"
    await house.teardown()


# ------------------------------------------------- ignore-intermediate


async def test_ignore_intermediate_option(hass, freezer):
    """Default: a foreign motion START latches. Option on: only the landing
    mismatch may latch — mid-travel the cover still reads auto-controlled.
    """
    # Default behavior: latch the moment the motor spins.
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        travel_seconds=600,
        options=LONG_OVERRIDE,
    )
    await house.advance_to("13:30")
    await settle(house)
    start = house.position(SHADE)
    await house.user_moves(SHADE, 100 if start < 70 else 0, via="remote")
    assert manual_binary(house) == "on", (
        "default config did not latch at motion start"
    )
    await house.teardown()
    # The harness's service re-win guard keeps its bus listener after
    # teardown; disarm it so the dead house cannot steal the cover
    # services back from the second house created next.
    house._registering_services = True

    # ignore_intermediate: the opening transition alone must NOT latch.
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        travel_seconds=600,
        options={CONF_MANUAL_IGNORE_INTERMEDIATE: True, **LONG_OVERRIDE},
    )
    await house.advance_to("13:30")
    await settle(house)
    start = house.position(SHADE)
    await house.user_moves(SHADE, 100 if start < 70 else 0, via="remote")
    assert manual_binary(house) == "off", (
        "ignore_intermediate still latched at motion start"
    )
    await house.tick()  # 5 min: still mid-travel (10-min journey)
    assert manual_binary(house) == "off", (
        "ignore_intermediate latched before any landing report"
    )
    await house.tick()  # 10 min: the landing mismatch arrives
    assert manual_binary(house) == "on", (
        "the landing mismatch never latched with ignore_intermediate on"
    )
    await house.teardown()


# ------------------------------------- takeover inside the travel window


async def test_takeover_during_travel_latches_at_motion_start(hass, freezer):
    """A cover reversing AGAINST our in-flight command is a human act NOW.

    Our motor cannot reverse on its own: the wrong-direction transition
    must latch immediately, not minutes later at the landing report.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        step_minutes=1,
        travel_seconds=600,
        options=LONG_OVERRIDE,
    )
    await house.advance_to("07:00")

    # Sweep for a fresh integration command whose direction we can oppose.
    counter = None
    for _ in range(240):
        before = len(house.auto_moves(SHADE))
        await house.tick()
        fresh = house.auto_moves(SHADE)[before:]
        if not fresh:
            continue
        origin = house.position(SHADE)  # field updates only at landing
        target = fresh[-1].position
        if target > origin and origin >= 10:
            counter = origin - 10  # ours opens; the human closes
        elif target < origin and origin <= 90:
            counter = origin + 10  # ours closes; the human opens
        if counter is not None:
            break
    assert counter is not None, "never caught an opposable in-flight command"

    await house.user_moves(SHADE, counter, via="remote")
    assert manual_binary(house) == "on", (
        "a counter-direction move inside the travel window did not latch "
        "at motion start"
    )
    takeover_at = house.now
    for _ in range(8):  # still inside the 10-minute travel window
        await house.tick()
    reverts = moves_on_or_after(house, SHADE, takeover_at + dt.timedelta(minutes=1))
    assert reverts == [], (
        f"auto control fought the human takeover mid-travel: {reverts}"
    )
    await house.teardown()


# ------------------------------------------------------ multi-day behavior


async def test_rollover_resumes_auto_moves(hass, freezer):
    """A deliberate long override ends at the solar-day boundary.

    Latched in the evening with a 24h duration, the override blocks auto
    control all night — but the new solar day clears it, and day-two
    commands reposition the shade without any human intervention.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        start_at="15:00",
        options={
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 24},
            CONF_MANUAL_OVERRIDE_RESET: False,
        },
    )
    await house.advance_to("17:00")
    await settle(house)
    await house.user_moves(SHADE, 100, via="remote")
    latched_at = house.now

    await house.advance_to("23:55")
    held = moves_on_or_after(house, SHADE, latched_at)
    assert held == [], f"auto moves during the evening override: {held}"
    assert manual_binary(house) == "on"

    await house.advance_to("09:00")  # crosses local midnight into day two
    day_two = house.tz.localize(dt.datetime(2026, 3, 21, 0, 0))
    resumed = moves_on_or_after(house, SHADE, day_two)
    assert resumed, (
        "day rollover never cleared the override: no day-two auto moves "
        f"by 09:00; timeline tail: {house.timeline[-8:]}"
    )
    assert manual_binary(house) == "off"
    assert house.position(SHADE) == resumed[-1].position
    await house.teardown()


async def test_day_two_solar_schedule(hass, freezer):
    """Day-two solar-time sensors and sunset close use day-two astral data."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20", start_at="18:00")
    await house.advance_to("18:10")
    start_day1 = house.sensor_value("start_sun")
    end_day1 = house.sensor_value("end_sun")
    assert start_day1 not in ("unknown", "unavailable")
    sunset_day1 = house.sun_data.sunset()

    await house.advance_to("12:00")  # crosses midnight into day two
    start_day2 = house.sensor_value("start_sun")
    end_day2 = house.sensor_value("end_sun")
    assert start_day2 not in ("unknown", "unavailable")
    assert (start_day2, end_day2) != (start_day1, end_day1), (
        "solar-time sensors still report day-one times on day two"
    )
    for label, value in (("start", start_day2), ("end", end_day2)):
        when = dt.datetime.fromisoformat(value).astimezone(house.tz)
        assert when.date() == dt.date(2026, 3, 21), (
            f"day-two {label} sun sensor reads {value}: not day-two data"
        )

    # The regenerated table carries real day-two astral data: in late
    # March the sunset drifts about a minute later per day.
    sunset_day2 = house.sun_data.sunset()
    drift = sunset_day2 - sunset_day1
    assert dt.timedelta(hours=23, minutes=50) < drift < dt.timedelta(hours=24, minutes=10)

    # Day two runs a full schedule: the shade reopens during the day and
    # closes again after the DAY-TWO sunset.
    day_two = house.tz.localize(dt.datetime(2026, 3, 21, 0, 0))
    sunset_local = sunset_day2.astimezone(house.tz)
    await house.advance_to("21:00")
    reopened = [
        ev
        for ev in moves_on_or_after(house, SHADE, day_two)
        if ev.position > 0 and ev.time < sunset_local
    ]
    assert reopened, "no day-two daytime tracking commands"
    closes = [
        ev
        for ev in moves_on_or_after(house, SHADE, sunset_local)
        if ev.position == 0
    ]
    assert closes, (
        "no close after the day-two sunset; day-two evening timeline: "
        f"{[ev for ev in house.timeline if ev.time >= sunset_local]}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()
