"""wp2-gates-windows-switches: rate gates, timing windows, control switches.

Behavior-tier scenarios (roadmap: tests/refactor_roadmap.json) driving the
REAL integration through SimHouse: config entries, sun/sensor state events,
real switch/select service calls, and the outbound cover-command timeline.
No coordinator internals are read; blocked moves are asserted through the
position sensor's public ``move_blocked_by`` attribute.

Mutation targets: M01 (delta ``>=`` inclusive), M02 (quiet-hours snap
bypass), M03 (move-budget ``>=``), M04 (throttle unconfigured branch),
M05 (start-entity precedence), M06 (midnight end-time normalization),
M07 (gate precedence order), M13 False branch (manual toggle off clears).

Calibration notes (2026-03-20, SLC, south window, FOV +-90, h=2.1 d=0.5):
sun becomes actionable ~07:35 (position saturates at 100 on FOV entry),
descends to a 28 plateau by ~08:05, holds 28 all day, climbs briefly after
19:30 and snaps to the sunset position ~19:40.
"""

import datetime as dt

from custom_components.adaptive_cover.const import (
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_END_TIME,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MAX_MOVES_HOUR,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_RETURN_SUNSET,
    CONF_START_ENTITY,
    CONF_START_TIME,
    CONF_SUNSET_POS,
    DOMAIN,
)

from .harness import SimHouse

SHADE = "cover.shade"


def blocked_by(house, entity=SHADE):
    """The gate currently blocking this cover, from the public attribute."""
    return house.sensor_attr("cover_position", "move_blocked_by").get(entity)


# ------------------------------------------------------------ position delta


async def test_delta_gate_blocks_drift_snap_passes(hass, freezer):
    """Sub-threshold drift commands nothing; the sunset snap still fires.

    delta_position=60: after the morning descent lands (~38), the entire
    plateau and the evening climb (27/29/50 — deltas 1..12) stay blocked.
    The sunset snap to 0 has |38-0| = 38 < 60 too, so ONLY the snap bypass
    can explain the close command that must still arrive.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_DELTA_POSITION: 60,
            CONF_DELTA_TIME: 0,
            CONF_DEFAULT_HEIGHT: 0,
        },
    )
    await house.advance_to("12:00")
    assert house.auto_moves(SHADE), "no morning commands at all"

    # Midday drift never reaches the 60 threshold: total silence.
    assert house.auto_moves(SHADE, since="08:30", until="17:00") == [], (
        "plateau drift below delta_position still commanded the cover"
    )
    assert blocked_by(house) == "position_delta"

    await house.advance_to("22:00")
    evening = house.auto_moves(SHADE, since="17:00")
    closes = [m for m in evening if m.position == 0]
    assert closes, f"sunset snap swallowed by the delta gate; evening: {evening}"
    assert [m.position for m in evening] == [0] * len(evening), (
        f"sub-threshold evening drift was commanded: {evening}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_delta_gate_threshold_is_inclusive(hass, freezer):
    """A change of EXACTLY delta_position moves; one less does not (M01).

    Manual detection is switched off so a human can park the shade at a
    precise offset from the computed plateau (28 all midday): 19 away is
    ignored for half an hour, 20 away is corrected on the next update.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        start_at="09:00",
        step_minutes=1,
        options={CONF_DELTA_POSITION: 20, CONF_DELTA_TIME: 0},
    )
    await house.toggle("manual_override", False)
    await house.advance_to("11:00")
    base = int(house.sensor_value())
    assert 0 < base < 80, f"expected a mid-range plateau, got {base}"

    await house.user_moves(SHADE, base + 19, via="remote")
    await house.advance_to("11:30")
    assert house.auto_moves(SHADE, since="11:01") == [], (
        "a 19-point offset (< delta_position 20) was corrected"
    )
    assert blocked_by(house) == "position_delta"

    await house.user_moves(SHADE, base + 20, via="remote")
    await house.advance_to("11:40")
    moves = house.auto_moves(SHADE, since="11:30")
    assert moves and moves[-1].position == base, (
        f"a change of exactly delta_position must move (>= not >): {moves}"
    )
    await house.teardown()


# ------------------------------------------------------------- timing window


async def test_time_window_gates_tracking(hass, freezer):
    """start 10:00 / end 15:00: zero commands outside, prompt entry at 10:00.

    The 15:00 boundary also gates the evening snaps: with the window shut,
    the shade holds its daytime position all night. The first 10:00 command
    is a cover never commanded before, killing the unconfigured-throttle
    branch (M04) as well.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={CONF_START_TIME: "10:00:00", CONF_END_TIME: "15:00:00"},
    )
    await house.advance_to("09:55")
    assert house.auto_moves(SHADE) == [], (
        "commands before the start time (sun actionable from ~07:35)"
    )
    assert blocked_by(house) == "outside_time_window"

    await house.advance_to("10:10")
    first = house.auto_moves(SHADE)
    assert first, "no command once the window opened"
    daytime = first[0].position
    assert daytime == int(house.sensor_value())

    await house.advance_to("23:00")
    assert house.auto_moves(SHADE, since="15:01") == [], (
        "commands after the end time (even snaps must respect the window)"
    )
    assert house.position(SHADE) == daytime, (
        "the shade should hold its last daytime position all night"
    )
    await house.teardown()


async def test_time_window_start_entity_precedence(hass, freezer):
    """A configured start-time ENTITY wins over the static option (M05)."""
    hass.states.async_set("input_datetime.sim_start_time", "12:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_START_TIME: "08:00:00",
            CONF_START_ENTITY: "input_datetime.sim_start_time",
        },
    )
    await house.advance_to("11:55")
    assert house.auto_moves(SHADE) == [], (
        "the static 08:00 start won over the 12:00 start entity"
    )
    await house.advance_to("12:15")
    moves = house.auto_moves(SHADE)
    assert moves, "no command after the entity start time passed"
    await house.teardown()


# ------------------------------------------------------------- time throttle


async def test_time_delta_throttle(hass, freezer):
    """Tracking commands are spaced by delta_time from OUR last command.

    The second command lands exactly 30 minutes after the first — counted
    from the command, not from the device's landing report two minutes
    later. The evening sunset snap fires within the throttle window of the
    preceding command.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        step_minutes=1,
        options={
            CONF_DELTA_TIME: 30,
            CONF_DELTA_POSITION: 1,
            CONF_DEFAULT_HEIGHT: 0,
        },
    )
    await house.advance_to("09:00")
    moves = house.auto_moves(SHADE, since="07:00")
    assert len(moves) >= 2, f"expected FOV-entry snap + throttled follow-up: {moves}"
    t0, t1 = moves[0], moves[1]
    assert t0.position == 100, f"first actionable command should saturate: {t0}"
    assert t1.time - t0.time == dt.timedelta(minutes=30), (
        "second command must come exactly delta_time after our first "
        f"command (landing reports must not restart the clock): {moves}"
    )
    await house.advance_to("20:00")
    evening = house.auto_moves(SHADE, since="18:30")
    closes = [m for m in evening if m.position == 0]
    assert closes, f"no sunset close: {evening}"
    close = closes[0]
    everything = house.auto_moves(SHADE)
    prev = [m for m in everything if m.time < close.time][-1]
    assert close.time - prev.time < dt.timedelta(minutes=30), (
        "the sunset snap should ignore the 30-min throttle "
        f"(prev {prev}, close {close})"
    )
    await house.teardown()


# ----------------------------------------------------------- midnight end


async def test_midnight_end_time(hass, freezer):
    """end_time 00:00:00 means NEXT midnight, not day start (M06).

    Tracking must run all day (a start-of-day 00:00 would shut the window
    immediately and fire a catch-up close at setup), and the on-time close
    must fire at the following midnight — bulldozing the late-evening
    manual override, as on-time closes do by design.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_END_TIME: "00:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8},
        },
    )
    await house.advance_to("12:00")
    assert house.auto_moves(SHADE, since="06:00"), (
        "no daytime tracking: the 00:00 end time closed the window all day"
    )

    await house.advance_to("22:30")
    await house.user_moves(SHADE, 100, via="remote")  # long override, held
    await house.advance_to("23:55")
    assert house.auto_moves(SHADE, since="22:35") == [], (
        "auto control ignored the late-evening override"
    )

    await house.advance_to("00:30")  # crosses local midnight
    closes = [
        m for m in house.auto_moves(SHADE, since="23:55") if m.position == 0
    ]
    assert closes, "no close at the NEXT midnight"
    assert closes[0].time.day == 21, f"close fired on the wrong day: {closes}"
    assert house.position(SHADE) == 0
    await house.teardown()


# -------------------------------------------------------------- quiet hours


async def test_quiet_hours_midnight_span_snap_bypass(hass, freezer):
    """A quiet window spanning midnight blocks tracking; snaps pass (M02).

    Quiet 17:00 -> 09:00. Morning: only the 100 FOV-entry snap (and the
    pre-dawn default snap) may fire before 09:00; the 38..28 descent is
    swallowed. Evening: the 27/29/50 climb is swallowed but the sunset
    close to 0 must arrive.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={CONF_QUIET_START: "17:00:00", CONF_QUIET_END: "09:00:00"},
    )
    await house.advance_to("08:55")
    early = house.auto_moves(SHADE)
    assert early, "even snap positions were blocked before 09:00"
    assert all(m.position in (0, 60, 100) for m in early), (
        f"non-snap tracking commanded inside the quiet window: {early}"
    )
    assert blocked_by(house) == "quiet_hours"

    await house.advance_to("09:10")
    tracked = house.auto_moves(SHADE, since="09:00")
    assert tracked and tracked[0].position == int(house.sensor_value()), (
        "tracking did not resume when the quiet window ended"
    )

    await house.advance_to("23:00")
    evening = house.auto_moves(SHADE, since="17:00")
    assert evening and {m.position for m in evening} == {0}, (
        "expected exactly the sunset snap (and nothing else) after 17:00; "
        f"got {evening}"
    )
    assert house.position(SHADE) == 0, "the quiet window swallowed the close"
    await house.teardown()


# -------------------------------------------------------------- move budget


async def test_move_budget(hass, freezer):
    """max_moves_hour=2: the third correction in an hour waits; snaps don't.

    Manual detection is off so a human can repeatedly park the shade off
    the plateau; each parking provokes one correction. The third within an
    hour is blocked (M03: >= not >), resumes when the window rolls off,
    and the evening sunset snap fires with the budget freshly exhausted.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_MAX_MOVES_HOUR: 2,
            CONF_DELTA_TIME: 0,
            CONF_DELTA_POSITION: 1,
        },
    )
    await house.toggle("manual_override", False)
    await house.advance_to("11:00")
    base = int(house.sensor_value())

    await house.user_moves(SHADE, base + 12, via="remote")
    await house.advance_to("11:10")
    assert house.auto_moves(SHADE, since="11:01"), "first correction missing"

    await house.user_moves(SHADE, base + 22, via="remote")
    await house.advance_to("11:18")
    assert house.auto_moves(SHADE, since="11:11"), "second correction missing"

    await house.user_moves(SHADE, base + 32, via="remote")
    await house.advance_to("11:50")
    assert house.auto_moves(SHADE, since="11:19") == [], (
        "a third tracking move fired inside the rolling hour"
    )
    assert blocked_by(house) == "move_budget"

    # The rolling window empties: the pending correction goes through.
    await house.advance_to("12:40")
    assert house.auto_moves(SHADE, since="12:00"), (
        "the budget never released the pending correction"
    )

    # Exhaust the budget right before sunset; the snap is exempt.
    await house.advance_to("19:00")
    await house.user_moves(SHADE, base + 42, via="remote")
    await house.advance_to("19:10")
    await house.user_moves(SHADE, base + 52, via="remote")
    await house.advance_to("19:20")
    assert len(house.auto_moves(SHADE, since="18:55")) >= 2, (
        "expected two corrections right before sunset"
    )
    await house.advance_to("20:30")
    closes = [
        m for m in house.auto_moves(SHADE, since="19:20") if m.position == 0
    ]
    assert closes, "the sunset snap must bypass an exhausted move budget"
    assert house.position(SHADE) == 0
    await house.teardown()


# ---------------------------------------------------------- gate precedence


async def test_gate_precedence_order(hass, freezer):
    """move_blocked_by names the FIRST failing gate in documented order (M07).

    With an all-day quiet window, midday tracking reports quiet_hours.
    After a human parks the shade 10 off the computed state (below the
    25 delta), manual_override + position_delta + quiet_hours all fail —
    and the attribute must name manual_override, the earliest gate.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_DELTA_POSITION: 25,
            CONF_QUIET_START: "00:00:00",
            CONF_QUIET_END: "23:59:59",
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8},
        },
    )
    await house.advance_to("12:00")
    assert blocked_by(house) == "quiet_hours"

    state = int(house.sensor_value())
    await house.user_moves(SHADE, state + 10, via="remote")
    await house.advance_to("12:15")
    assert blocked_by(house) == "manual_override", (
        "manual override must be named before position_delta/quiet_hours; "
        f"got {blocked_by(house)}"
    )
    assert house.auto_moves(SHADE, since="12:00") == []
    await house.teardown()


async def test_gate_precedence_awaiting_then_throttle(hass, freezer):
    """During travel the block is awaiting_target; after landing, throttle.

    delta_time=60: one minute after the FOV-entry command the cover is
    still travelling (awaiting_target outranks the also-failing throttle);
    once it lands and the computed state drifts, the same cover reports
    time_throttle until the hour passes.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        step_minutes=1,
        options={
            CONF_DELTA_TIME: 60,
            CONF_DELTA_POSITION: 1,
            CONF_DEFAULT_HEIGHT: 0,
        },
    )
    await house.advance_to("07:15")
    for _ in range(60):
        await house.tick()
        if any(m.position == 100 for m in house.auto_moves(SHADE)):
            break
    saturated = [m for m in house.auto_moves(SHADE) if m.position == 100]
    assert saturated, "the FOV-entry command never arrived"
    t0 = saturated[0].time

    await house.tick()  # 60s in: still travelling (120s journey)
    assert blocked_by(house) == "awaiting_target"

    for _ in range(20):
        await house.tick()
        if blocked_by(house) == "time_throttle":
            break
    assert blocked_by(house) == "time_throttle", (
        f"expected the throttle to take over after landing: {blocked_by(house)}"
    )
    assert [m for m in house.auto_moves(SHADE) if m.time > t0] == [], (
        "a command slipped through inside the 60-min throttle"
    )
    await house.teardown()


# ------------------------------------------------------------ control switch


async def test_control_off_no_calls(hass, freezer):
    """Control off: no tracking, no startup command, no end-time close."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_END_TIME: "18:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("04:30")
    parked = house.position(SHADE)
    await house.toggle("toggle_control", False)

    # Restart mid-day: the restored OFF switch must suppress the
    # first-refresh catch-up command too.
    await house.restart(at="12:00")
    assert house.entity("switch", "toggle_control").state == "off"

    await house.advance_to("21:00")  # end-time close would fire at 18:00
    assert house.auto_moves(SHADE, since="04:30") == [], (
        "service calls while the control switch entity is off"
    )
    assert house.position(SHADE) == parked
    await house.teardown()


async def test_control_on_force_apply(hass, freezer):
    """Switching control on applies computed positions NOW, bypassing gates.

    delta_position=90 and a 10-hour throttle would block any tracking
    move; the switch-on force-apply must command the healthy cover
    immediately anyway — and skip the cover whose manual override
    survived the restart (restored with the switch off, so nothing
    cleared it).
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        covers=["cover.left", "cover.right"],
        options={
            CONF_DELTA_POSITION: 90,
            CONF_DELTA_TIME: 600,
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 12},
        },
    )
    await house.advance_to("11:00")
    await house.user_moves("cover.left", 50, via="remote")
    await house.advance_to("11:05")
    assert house.entity("binary_sensor", "manual_override").state == "on"

    await house.restart(
        at="11:10",
        seed_states={house.eid("switch", "toggle_control"): "off"},
    )
    assert house.entity("switch", "toggle_control").state == "off"
    assert house.entity("binary_sensor", "manual_override").state == "on", (
        "the manual override was lost across the restart"
    )

    await house.advance_to("12:00")
    assert house.auto_moves("cover.right", since="11:10") == []

    await house.toggle("toggle_control", True)
    applied = house.auto_moves("cover.right", since="11:55")
    assert applied and applied[-1].position == int(house.sensor_value()), (
        "switch-on must force-apply the computed position despite "
        f"delta/throttle gates; moves: {applied}"
    )
    assert house.auto_moves("cover.left", since="11:00") == [], (
        "force-apply commanded a manually overridden cover"
    )
    assert house.position("cover.left") == 50
    await house.teardown()


async def test_control_on_force_apply_respects_time_window(hass, freezer):
    """Force-apply on switch-on still honors the configured start time."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={CONF_START_TIME: "14:00:00"},
    )
    await house.advance_to("09:00")
    await house.toggle("toggle_control", False)
    await house.advance_to("09:30")
    await house.toggle("toggle_control", True)
    await house.advance_to("13:55")
    assert house.auto_moves(SHADE) == [], (
        "switch-on force-applied outside the timing window"
    )
    await house.advance_to("14:15")
    moves = house.auto_moves(SHADE)
    assert moves, "tracking never started once the window opened"
    await house.teardown()


async def test_control_off_on_clears_overrides(hass, freezer):
    """Toggling control off wipes manual overrides; on re-commands at once."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8}},
    )
    await house.advance_to("11:00")
    tracked = int(house.sensor_value())
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:15")
    assert house.auto_moves(SHADE, since="11:01") == []
    assert house.entity("binary_sensor", "manual_override").state == "on"

    await house.toggle("toggle_control", False)
    assert house.entity("binary_sensor", "manual_override").state == "off", (
        "control-off must clear manual overrides"
    )
    await house.toggle("toggle_control", True)
    moves = house.auto_moves(SHADE, since="11:10")
    assert moves and moves[-1].position == tracked, (
        "the previously overridden cover was not re-commanded on switch-on"
    )
    await house.advance_to("11:30")
    assert house.position(SHADE) == tracked
    await house.teardown()


async def test_manual_switch_off_clears_overrides_reload_preserves(
    hass, freezer
):
    """Reload preserves overrides; ONLY an explicit manual-off clears (M13).

    Saving the options dialog unchanged reloads the entry: the active
    override must survive (the toggle is None during startup). Turning the
    Manual Override switch off is the explicit act that clears it, after
    which tracking resumes.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8}},
    )
    await house.advance_to("11:00")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:15")
    assert house.entity("binary_sensor", "manual_override").state == "on"

    await house.set_options()  # user saves the dialog unchanged -> reload
    await house.advance_to("11:45")
    assert house.entity("binary_sensor", "manual_override").state == "on", (
        "an options reload wiped the manual override"
    )
    assert house.auto_moves(SHADE, since="11:01") == [], (
        "auto control moved an overridden cover after a reload"
    )

    await house.toggle("manual_override", False)
    await house.advance_to("12:15")
    assert house.entity("binary_sensor", "manual_override").state == "off"
    moves = house.auto_moves(SHADE, since="11:45")
    assert moves, "tracking never resumed after the explicit manual-off"
    assert house.position(SHADE) == moves[-1].position
    await house.teardown()


# ------------------------------------------------------------- climate mode


async def test_climate_switch_flips_live(hass, freezer):
    """The climate-mode switch flips strategy live, without a reload.

    Cold CLOUDY day at home: climate mode opens fully (winter passive
    heating, no beam so no glare) while basic mode keeps tracking the sun
    (weather-blind). Toggling the switch mid-day swaps between the two on
    the next update. (A cold SUNNY day at home falls through to the basic
    strategy unless a glare model is configured, so it cannot disagree.)
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        climate={
            "temp": 15.0,
            "presence": "home",
            "weather": "cloudy",
            "temp_low": 21.0,
            "temp_high": 23.0,
        },
    )
    await house.advance_to("12:00")
    coordinator_before = hass.data[DOMAIN][house.entry.entry_id]
    assert house.position(SHADE) == 100, (
        "climate mode on a cold cloudy day at home should open fully"
    )

    await house.toggle("climate_mode", False)
    await house.advance_to("12:20")
    basic = house.auto_moves(SHADE, since="12:00")
    assert basic and basic[-1].position < 100, (
        f"basic mode should track the sun after the flip: {basic}"
    )
    assert basic[-1].position == int(house.sensor_value())
    assert house.position(SHADE) == basic[-1].position

    await house.toggle("climate_mode", True)
    await house.advance_to("12:40")
    assert house.position(SHADE) == 100, (
        "flipping climate mode back on should re-open fully"
    )
    assert hass.data[DOMAIN][house.entry.entry_id] is coordinator_before, (
        "the mode flip must not reload the entry"
    )
    await house.teardown()
