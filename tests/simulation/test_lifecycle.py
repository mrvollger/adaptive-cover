"""End-time, restart, and reload lifecycle behavior (wp4).

Pins, at the behavior tier (timeline service calls + entity states only):

- the on-time end-of-day close beats a LIVE manual override, while a
  catch-up close (armed past its moment, after a restart/reload) skips
  manually overridden covers;
- a close delivered late by the event loop still closes;
- changing the end time re-arms the close (earlier, later, and
  moved-later-while-the-timer-was-withheld), through the end-time entity
  and through the real ``adaptive_cover.change_settings`` service;
- a daytime startup / options reload immediately positions the covers
  (provenance ``startup``);
- switches restore their prior state across a restart (and fall back to
  documented defaults without restore data), and a latched manual
  override survives a restart.

Every restart goes through ``house.restart()`` and every options change
through ``house.set_options()`` or the production settings service.
"""

import pytest

from custom_components.adaptive_cover.const import (
    CONF_DISTANCE,
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
    DOMAIN,
)

from .harness import SimHouse

SHADE = "cover.shade"
END_SENSOR = "sensor.sim_end_time"

# 2026-03-20 (equinox) in SLC: sunrise ~07:35, sunset ~19:33 local.
DATE = "2026-03-20"


def end_time_options(end="20:00:00", **extra):
    """Options enabling the timed end-of-day close at ``end``."""
    return {
        CONF_END_TIME: end,
        CONF_RETURN_SUNSET: True,
        CONF_SUNSET_POS: 0,
        **extra,
    }


def closes(house, *, since, until=None):
    """Integration close commands (position 0) for the shade."""
    return [
        m
        for m in house.auto_moves(SHADE, since=since, until=until)
        if m.position == 0
    ]


# ------------------------------------------------------- end-time close


async def test_close_beats_live_override(hass, freezer):
    """The ON-TIME end close fires even while a manual override is LIVE.

    Override duration is 8 hours and the remote move happens at 19:50,
    ten minutes before the 20:00 end time: whatever the override state,
    the scheduled close is the one move that must happen.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options=end_time_options(
            "20:00:00",
            **{
                CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8},
                CONF_MANUAL_OVERRIDE_RESET: False,
            },
        ),
    )
    await house.advance_to("19:50")
    await house.user_moves(SHADE, 100, via="remote")

    # The override holds until the end time: no auto command reverts it.
    await house.advance_to("19:58")
    assert house.auto_moves(SHADE, since="19:51", until="19:59") == [], (
        "auto control fought a live manual override before the end time"
    )

    await house.advance_to("20:10")
    assert closes(house, since="19:59", until="20:10"), (
        "the on-time end close was swallowed by a live manual override; "
        f"evening timeline: {[e for e in house.timeline if e.time.hour >= 19]}"
    )
    await house.advance_to("20:15")
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_late_fired_close_still_closes(hass, freezer):
    """A close delivered 40 minutes late by the event loop still closes.

    End time 18:00 is well before sunset (~19:33), so after 18:00 the
    adaptive path is outside the time window and ONLY the (late) timed
    close can drive the shade to 0.
    """
    house = await SimHouse.create(
        hass, freezer, date=DATE, options=end_time_options("18:00:00")
    )
    await house.advance_to("17:50")
    house.hold_timers()
    await house.advance_to("18:40")
    assert closes(house, since="17:55", until="18:38") == [], (
        "close delivered while the 18:00 listener was withheld"
    )

    await house.release_timers()
    assert closes(house, since="18:38"), (
        "the late-delivered end-time listener never closed the shade"
    )
    await house.advance_to("18:50")
    assert house.position(SHADE) == 0
    await house.teardown()


# --------------------------------------------------- end-time re-arming


async def test_end_time_rearm_earlier_via_entity(hass, freezer):
    """Moving the end time EARLIER mid-day re-arms: close at 18:00, not 20:00."""
    hass.states.async_set(END_SENSOR, "20:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_END_ENTITY: END_SENSOR,
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("14:00")
    hass.states.async_set(END_SENSOR, "18:00:00")
    await hass.async_block_till_done()

    await house.advance_to("19:00")
    assert closes(house, since="14:05", until="17:50") == [], (
        "a close fired before the (new) end time"
    )
    assert closes(house, since="17:55", until="18:05"), (
        "end time moved 20:00 -> 18:00 but no close fired at 18:00 "
        "(stale timer kept?); evening timeline: "
        f"{[e for e in house.timeline if e.time.hour >= 17]}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_end_time_rearm_later_no_stale_close(hass, freezer):
    """Moving the end time LATER cancels the earlier arm: no 18:00 close."""
    hass.states.async_set(END_SENSOR, "18:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_END_ENTITY: END_SENSOR,
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("14:00")
    hass.states.async_set(END_SENSOR, "21:00:00")
    await hass.async_block_till_done()

    await house.advance_to("20:00")
    # Around 18:00 the sun still tracks (~50%): a 0-command there could
    # only be the stale, cancelled 18:00 close.
    assert closes(house, since="17:50", until="18:20") == [], (
        "the stale 18:00 arm fired after the end time moved to 21:00"
    )
    # The sunset return (~19:33) closes INSIDE the extended window —
    # proving the system is alive and the window followed the new end
    # time (with the old 18:00 window this close could not fire at all).
    assert closes(house, since="19:30", until="20:00"), (
        "no sunset-return close inside the extended window; the "
        "no-stale-close assert above may be vacuous"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_end_time_moved_later_while_withheld_waits(hass, freezer):
    """A withheld 18:00 close whose end time moved to 19:00 waits for 19:00.

    The 18:00 listener is delivered late (18:30) after the end time was
    moved to 19:00: it must NOT close at delivery. 19:00 is still before
    sunset, so the 19:00 close is unambiguously the re-armed timer.
    """
    hass.states.async_set(END_SENSOR, "18:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_END_ENTITY: END_SENSOR,
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("17:50")
    house.hold_timers()
    await house.advance_to("18:10")
    hass.states.async_set(END_SENSOR, "19:00:00")
    await hass.async_block_till_done()
    await house.advance_to("18:30")
    await house.release_timers()

    assert closes(house, since="17:55", until="18:40") == [], (
        "the withheld 18:00 close fired although the end time moved to 19:00"
    )
    await house.advance_to("19:10")
    assert closes(house, since="18:55", until="19:10"), (
        "the close never fired at the NEW 19:00 end time; evening timeline: "
        f"{[e for e in house.timeline if e.time.hour >= 18]}"
    )
    await house.advance_to("19:15")
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_end_time_rearm_via_settings_service(hass, freezer):
    """adaptive_cover.change_settings moves the end time and re-arms.

    Drives the real inbound service surface: the option change must land
    in entry.options (options win over the previous value) and the close
    must follow the NEW end time after the reload.
    """
    house = await SimHouse.create(
        hass, freezer, date=DATE, options=end_time_options("20:00:00")
    )
    await house.advance_to("14:00")
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": house.entry.entry_id, CONF_END_TIME: "18:00:00"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert house.entry.options[CONF_END_TIME] == "18:00:00", (
        "change_settings did not update the entry options"
    )
    # Re-point the harness at the reloaded entry (models the user saving
    # the options dialog unchanged; still only public lifecycle APIs).
    await house.set_options()

    await house.advance_to("19:00")
    assert closes(house, since="17:55", until="18:05"), (
        "no close at the end time set through the settings service; "
        f"evening timeline: {[e for e in house.timeline if e.time.hour >= 17]}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


# ----------------------------------------------------- catch-up close


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PROD BUG: the catch-up end-time close is dropped on a late setup. "
        "async_config_entry_first_refresh arms the past end time, whose "
        "listener fires BEFORE the switch platform restores the control "
        "switch; async_handle_timed_refresh then sees control_toggle=None "
        "(falsy), logs 'Timed refresh but control toggle is off', and "
        "consumes timed_refresh/_end_time_is_catchup without closing. "
        "After a real HA restart landing past the end time the shades "
        "stay up all night."
    ),
)
async def test_catchup_close_on_late_setup(hass, freezer):
    """HA starting at 21:00 with end time 20:00 closes immediately (catch-up)."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        start_at="21:00",
        options=end_time_options("20:00:00"),
    )
    await house.advance_to("21:10")
    catchup = closes(house, since="21:00", until="21:10")
    assert catchup, (
        "no catch-up close after a setup landing past the end time; "
        f"timeline: {house.timeline}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_catchup_close_when_end_moved_past(hass, freezer):
    """Moving the end time into the past fires the close as a catch-up NOW.

    At 18:30 the end-time entity jumps from 20:00 back to 18:00: the
    re-arm lands on a past point and must deliver the close immediately.
    The 18:00 window is already shut, so the 18:3x close is unambiguously
    the catch-up fire, not the adaptive path.
    """
    hass.states.async_set(END_SENSOR, "20:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_END_ENTITY: END_SENSOR,
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("18:30")
    hass.states.async_set(END_SENSOR, "18:00:00")
    await hass.async_block_till_done()
    await house.advance_to("18:40")

    assert closes(house, since="18:25", until="18:40"), (
        "no catch-up close after the end time moved into the past; "
        f"timeline: {[e for e in house.timeline if e.time.hour >= 18]}"
    )
    await house.advance_to("18:45")
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_catchup_skips_overridden_cover(hass, freezer):
    """A catch-up close (unlike the on-time close) respects manual overrides.

    Same catch-up as above (end time moved past its moment), but the
    shade was manually reopened at 17:00 with an 8-hour override: the
    catch-up must NOT bulldoze it. The companion test above proves the
    catch-up does fire and close a non-overridden shade.
    """
    hass.states.async_set(END_SENSOR, "20:00:00")
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_END_ENTITY: END_SENSOR,
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8},
            CONF_MANUAL_OVERRIDE_RESET: False,
        },
    )
    await house.advance_to("17:00")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("18:30")
    hass.states.async_set(END_SENSOR, "18:00:00")
    await hass.async_block_till_done()

    await house.advance_to("19:00")
    assert house.auto_moves(SHADE, since="17:01") == [], (
        "the catch-up close bulldozed a live manual override; timeline: "
        f"{[e for e in house.timeline if e.time.hour >= 17]}"
    )
    assert house.position(SHADE) == 100
    assert house.entity("binary_sensor", "manual_override").state == "on"
    await house.teardown()


# ------------------------------------------------- startup positioning


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PROD BUG: first-refresh startup positioning never runs. The "
        "config-entry first refresh executes before the switch platform "
        "is forwarded, so control_toggle is still None (falsy) and "
        "async_handle_first_refresh logs 'First refresh but control "
        "toggle is off' and consumes the one-shot first_refresh flag; "
        "the switch restore afterwards deliberately skips force_apply "
        "(added=True). Covers are only positioned by the NEXT sun "
        "change, with source='adaptive' instead of 'startup'."
    ),
)
async def test_daytime_startup_positions(hass, freezer):
    """HA starting mid-day immediately positions covers (source=startup)."""
    house = await SimHouse.create(hass, freezer, date=DATE, start_at="13:00")

    startup_moves = house.auto_moves(SHADE)
    assert startup_moves, "no immediate command on a daytime startup"
    first = startup_moves[0]
    assert (first.time.hour, first.time.minute) == (13, 0), (
        f"startup command did not fire at startup: {first}"
    )
    last_move_line = house.sensor_attr("cover_position", "last_moves")[SHADE]
    assert "startup" in last_move_line, (
        f"startup move provenance missing: {last_move_line}"
    )
    await house.teardown()


async def test_daytime_start_positions_within_first_tick(hass, freezer):
    """A daytime start positions the covers within the first sun tick.

    Pins today's working behavior (the deeper source=startup expectation
    is the xfail above): the shade must not sit at its stale position for
    more than a few minutes after HA comes up mid-day, and an options
    reload changing the geometry must re-position just as quickly.
    """
    house = await SimHouse.create(hass, freezer, date=DATE, start_at="13:00")
    await house.advance_to("13:10")
    moves = house.auto_moves(SHADE, until="13:10")
    assert moves, "shade never positioned within 10 minutes of a daytime start"
    assert house.position(SHADE) == moves[-1].position

    # Reload variant: moving the window geometry changes the computed
    # position; the reloaded entry must re-command promptly.
    before_reload = moves[-1].position
    await house.advance_to("13:58")
    await house.set_options(**{CONF_DISTANCE: 0.9})
    await house.advance_to("14:10")
    reload_moves = house.auto_moves(SHADE, since="13:58")
    assert reload_moves, (
        "no command within 10 minutes of a geometry-changing reload"
    )
    assert reload_moves[-1].position != before_reload, (
        "post-reload command ignored the changed geometry"
    )
    await house.teardown()


# ------------------------------------------------------ switch restore


async def test_switch_restore_captured_states(hass, freezer):
    """Switches restore their pre-restart states across restart()."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={"temp": 22.0, "presence": "home", "weather": "sunny"},
    )
    await house.advance_to("10:00")
    await house.toggle("toggle_control", False)
    await house.toggle("climate_mode", False)

    await house.restart(at="10:30")

    assert house.entity("switch", "toggle_control").state == "off", (
        "control switch did not restore its captured off state"
    )
    assert house.entity("switch", "climate_mode").state == "off", (
        "climate mode switch did not restore its captured off state"
    )
    assert house.entity("switch", "manual_override").state == "on", (
        "untouched manual override switch lost its on state"
    )
    await house.teardown()


async def test_switch_defaults_without_prior_state(hass, freezer):
    """A brand-new entry's switches start at their documented defaults.

    No prior state exists at first setup, so RestoreEntity falls back to
    the initial states: control ON, manual override ON, climate mode ON,
    outside temperature OFF.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 22.0,
            "presence": "home",
            "weather": "sunny",
            "outside_temp": 28.0,
        },
    )
    assert house.entity("switch", "toggle_control").state == "on"
    assert house.entity("switch", "manual_override").state == "on"
    assert house.entity("switch", "climate_mode").state == "on"
    assert house.entity("switch", "outside_temperature").state == "off"
    await house.teardown()


async def test_restart_preserves_latched_override(hass, freezer):
    """A latched manual override survives an HA restart.

    During startup the manual toggle is still unrestored (None) — that
    must PRESERVE overrides, not clear them like an explicit off does.
    After the configured duration expires, auto control resumes,
    proving the post-restart system is alive (the earlier no-moves
    assert is not vacuous).
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        options={
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 2},
            CONF_MANUAL_OVERRIDE_RESET: False,
        },
    )
    await house.advance_to("11:00")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:10")

    await house.restart(at="11:20")

    await house.advance_to("12:30")  # still inside the 2 h override
    assert house.auto_moves(SHADE, since="11:21", until="12:30") == [], (
        "restart cleared the latched manual override"
    )
    assert house.position(SHADE) == 100
    assert house.entity("binary_sensor", "manual_override").state == "on"

    await house.advance_to("13:30")  # override (11:00 + 2 h) expired
    assert house.auto_moves(SHADE, since="13:00"), (
        "auto control never resumed after the override expired post-restart"
    )
    await house.teardown()
