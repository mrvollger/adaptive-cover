"""Smoke tests for the harness extensions: one minimal scenario per API.

Each test proves the MECHANISM works (the harness package's own acceptance);
the behavior work packages (wp2-wp8) build the real scenarios on top.
"""

from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_cover.const import (
    CONF_DELTA_TIME,
    CONF_END_TIME,
    CONF_IRRADIANCE_ENTITY,
    CONF_LUX_ENTITY,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    DOMAIN,
    SensorType,
)

from .harness import SimHouse

SHADE = "cover.shade"


# ------------------------------------------------------- entity accessors


async def test_eid_entity_sensor_accessors(hass, freezer):
    """eid/entity/sensor_value/sensor_attr resolve through the registry."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("12:00")

    eid = house.eid("sensor", "cover_position")
    assert eid.startswith("sensor.")
    state = house.entity("sensor", "cover_position")
    assert state is hass.states.get(eid)
    assert house.sensor_value() == state.state
    assert state.state.isdigit()
    assert isinstance(house.sensor_attr("cover_position", "move_blocked_by"), dict)
    assert house.entity("binary_sensor", "sun_infront").state in ("on", "off")
    assert house.entity("switch", "toggle_control").state == "on"
    await house.teardown()


# --------------------------------------------------- switch/select/button


async def test_toggle_flips_real_switch_entity(hass, freezer):
    """toggle() drives the control switch via a real service call."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("10:00")

    await house.toggle("toggle_control", False)
    assert house.entity("switch", "toggle_control").state == "off"
    before = len(house.auto_moves(SHADE))
    await house.advance_to("11:00")
    assert len(house.auto_moves(SHADE)) == before, (
        "auto moves while the control switch entity is off"
    )
    await house.toggle("toggle_control", True)
    assert house.entity("switch", "toggle_control").state == "on"
    await house.teardown()


async def test_select_option_drives_mode(hass, freezer):
    """select_option() flips the underlying control switch."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("10:00")

    await house.select_option("mode_select", "Manual")
    assert house.entity("switch", "toggle_control").state == "off"
    assert house.entity("select", "mode_select").state == "Manual"
    await house.select_option("mode_select", "Sun tracking")
    assert house.entity("switch", "toggle_control").state == "on"
    await house.teardown()


async def test_press_reset_button_resumes_auto(hass, freezer):
    """press() drives the real button entity; auto control resumes."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:10")
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("11:15")
    latched_at = "11:15"
    assert house.auto_moves(SHADE, since="11:11") == []

    await house.press()  # default: reset_manual_override
    moves = house.auto_moves(SHADE, since=latched_at)
    assert moves, "reset button never re-commanded the overridden cover"
    assert house.position(SHADE) == moves[-1].position
    await house.teardown()


# ------------------------------------------------------------- lifecycle


async def test_set_options_survives_reload(hass, freezer):
    """set_options() reloads the entry, re-wins services, re-points coordinator."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:00")
    old_coordinator = house.coordinator

    await house.set_options(**{CONF_DELTA_TIME: 5})

    assert house.entry.options[CONF_DELTA_TIME] == 5
    assert house.coordinator is not old_coordinator
    assert house.coordinator is hass.data[DOMAIN][house.entry.entry_id]
    # the afternoon is a delta-gated plateau; the sunset snap is the next
    # guaranteed command and proves the fake services were re-won
    await house.advance_to("20:00")  # sunset ~19:33
    closes = [m for m in house.auto_moves(SHADE, since="19:30") if m.position == 0]
    assert closes, "no sunset close after reload: fake services were not re-won"
    await house.teardown()


async def test_restart_preserves_timeline_and_restores_switches(hass, freezer):
    """restart() keeps the timeline and restores captured switch states."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:00")
    await house.toggle("toggle_control", False)
    events_before = len(house.timeline)

    await house.restart(at="11:30")

    assert len(house.timeline) >= events_before, "restart wiped the timeline"
    assert house.entity("switch", "toggle_control").state == "off", (
        "restart lost the captured switch state"
    )
    assert house.coordinator is hass.data[DOMAIN][house.entry.entry_id]

    # seed_states overrides the capture: force the control switch back on.
    await house.restart(
        seed_states={house.eid("switch", "toggle_control"): "on"}
    )
    assert house.entity("switch", "toggle_control").state == "on"
    await house.teardown()


# ------------------------------------------------------------ sun & timers


async def test_day_two_sun_regeneration(hass, freezer):
    """Crossing midnight regenerates the sun table for the new date."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20", start_at="20:00")
    sunset_day_one = house.sun_data.sunset()
    assert house.sun_data.date.date().isoformat() == "2026-03-20"

    await house.advance_to("01:00")  # crosses local midnight

    assert house.sun_data.date.date().isoformat() == "2026-03-21"
    sunset_day_two = house.sun_data.sunset()
    assert sunset_day_two != sunset_day_one
    assert sunset_day_two.date() > sunset_day_one.date()
    await house.teardown()


async def test_dst_transition_day_advances(hass, freezer):
    """Ticking across the 2026-03-08 spring-forward gap must not crash."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-08", start_at="01:00",
        location=dict(lat=40.76, lon=-111.89, tz="America/Denver"),
    )
    await house.advance_to("03:30")  # 02:00-03:00 does not exist locally
    assert house.now.hour == 3
    assert house.now.utcoffset().total_seconds() == -6 * 3600  # now in MDT
    await house.teardown()


async def test_hold_release_timers_delivers_close_late(hass, freezer):
    """A withheld end-time listener fires (late) on release_timers()."""
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
    await house.advance_to("17:50")
    house.hold_timers()
    await house.advance_to("18:40")
    assert house.auto_moves(SHADE, since="17:55") == [], (
        "end-time close fired while timers were held"
    )

    await house.release_timers()
    closes = [m for m in house.auto_moves(SHADE, since="18:35") if m.position == 0]
    assert closes, "released timer never delivered the (late) close"
    await house.teardown()


# ----------------------------------------------------------- fault modes


async def test_jammed_shade_never_lands_poll_reports_stuck(hass, freezer):
    """jam(): stops mid-travel, no landing ever, poll shows the stuck spot."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", travel_seconds=600
    )
    await house.advance_to("11:00")
    start = house.position(SHADE)
    await house.user_moves(SHADE, 0, via="remote")
    jam_time = house.now
    await house.tick()  # 5 min into a 10-min journey
    house.jam(SHADE)
    stuck = house.position(SHADE)
    assert 0 < stuck < start, f"expected a mid-travel position, got {stuck}"

    await house.advance_to("11:40")
    assert house.position(SHADE) == stuck, "jammed shade landed anyway"
    landings = [
        ev for ev in house.timeline
        if ev.kind == "state" and ev.position == 0
        and ev.entity_id == SHADE and ev.time > jam_time
    ]
    assert landings == [], "jammed shade sent a landing report"

    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": SHADE}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SHADE).attributes["current_position"] == stuck
    await house.teardown()


async def test_drop_landing_report_surfaces_on_poll(hass, freezer):
    """drop_landing_report(): silent landing, truth surfaces on next poll."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:00")
    house.drop_landing_report(SHADE)
    await house.user_moves(SHADE, 0, via="remote")
    stale = hass.states.get(SHADE).attributes["current_position"]
    assert stale > 0  # the pre-travel position, reported at motion start
    await house.advance_to("11:10")  # travel done, report swallowed

    assert house.position(SHADE) == 0, "the shade itself did reach the target"
    assert hass.states.get(SHADE).attributes["current_position"] == stale, (
        "the dropped landing report leaked into hass.states"
    )

    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": SHADE}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SHADE).attributes["current_position"] == 0
    await house.teardown()


async def test_strip_position_attr_omits_position(hass, freezer):
    """strip_position_attr(): state writes carry no position attributes."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:00")
    house.strip_position_attr(SHADE)
    await house.user_moves(SHADE, 0, via="remote")
    attrs = hass.states.get(SHADE).attributes
    assert "current_position" not in attrs
    assert "current_tilt_position" not in attrs

    house.strip_position_attr(SHADE, on=False)
    await house.advance_to("11:10")  # landing report with attrs again
    assert "current_position" in hass.states.get(SHADE).attributes
    await house.teardown()


async def test_fail_next_command_raises_once_loop_survives(hass, freezer):
    """fail_next_command(): one raise, other covers commanded, retried later."""
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", covers=["cover.left", "cover.right"]
    )
    house.fail_next_command("cover.left")
    await house.advance_to("12:00")

    assert house.shades["cover.left"].fail_next is None, (
        "the injected failure was never consumed: no command ever reached "
        "the failing cover"
    )
    assert house.auto_moves("cover.right"), "healthy cover was not commanded"
    assert house.auto_moves("cover.left"), (
        "failed cover was never re-commanded after the one-shot failure"
    )
    assert house.coordinator.last_update_success
    await house.teardown()


async def test_fail_next_command_custom_exception(hass, freezer):
    """fail_next_command() accepts a custom exception instance."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    house.fail_next_command(SHADE, exc=HomeAssistantError("zigbee timeout"))
    assert isinstance(house.shades[SHADE].fail_next, HomeAssistantError)
    await house.advance_to("09:00")  # morning tracking consumes the failure
    assert house.shades[SHADE].fail_next is None
    assert house.coordinator.last_update_success
    await house.teardown()


async def test_shade_unavailable_and_returns(hass, freezer):
    """shade_goes_unavailable()/shade_returns(): outage stops commands."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:00")
    await house.shade_goes_unavailable(SHADE)
    assert hass.states.get(SHADE).state == "unavailable"
    before = len(house.auto_moves(SHADE))
    await house.advance_to("11:30")
    assert len(house.auto_moves(SHADE)) == before, (
        "commands recorded while the shade was unavailable"
    )

    await house.shade_returns(SHADE)
    assert hass.states.get(SHADE).state in ("open", "closed")
    # the afternoon is a delta-gated plateau; the sunset snap is the next
    # guaranteed command and proves auto control resumed after the outage
    await house.advance_to("20:00")  # sunset ~19:33
    closes = [m for m in house.auto_moves(SHADE, since="19:30") if m.position == 0]
    assert closes, "auto control never resumed after the shade returned"
    await house.teardown()


# -------------------------------------------------------------- aux climate


async def test_aux_climate_entities_wired(hass, freezer):
    """create(climate={lux/irradiance/outside_temp/presence_domain}) wiring."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        climate={
            "temp": 18.0,
            "presence": "on",
            "presence_domain": "binary_sensor",
            "weather": "sunny",
            "lux": 450,
            "lux_threshold": 1000,
            "irradiance": 250,
            "irradiance_threshold": 300,
            "outside_temp": 28.0,
        },
    )
    opts = house.entry.options
    assert opts[CONF_LUX_ENTITY] == house.LUX_SENSOR
    assert opts[CONF_IRRADIANCE_ENTITY] == house.IRRADIANCE_SENSOR
    assert opts[CONF_OUTSIDETEMP_ENTITY] == house.OUTSIDE_TEMP_SENSOR
    assert house.presence_entity == "binary_sensor.sim_presence"
    # the aux toggle switches exist for this entry
    assert house.entity("switch", "lux") is not None
    assert house.entity("switch", "irradiance") is not None
    assert house.entity("switch", "outside_temperature") is not None

    await house.advance_to("11:00")
    await house.set_lux("unavailable")  # garbage must not kill the loop
    await house.set_irradiance(500)
    await house.set_outside_temp(30.0)
    await house.set_presence("off")
    await house.advance_to("12:00")
    assert house.coordinator.last_update_success
    assert hass.states.get(house.LUX_SENSOR).state == "unavailable"
    await house.teardown()


# ------------------------------------------------------------ tilt fidelity


async def test_tilt_house_uses_tilt_field_and_service(hass, freezer):
    """Tilt commands move FakeShade.tilt via set_cover_tilt_position only."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        cover_type=SensorType.TILT,
        options={
            CONF_TILT_DEPTH: 3,
            CONF_TILT_DISTANCE: 2,
            CONF_TILT_MODE: "mode2",
        },
    )
    await house.advance_to("12:00")
    all_moves = house.auto_moves(SHADE)
    tilt_moves = house.auto_moves(SHADE, service="set_cover_tilt_position")
    assert all_moves, "tilt entry never commanded the cover"
    assert tilt_moves == all_moves, (
        "some tilt-entry commands used set_cover_position"
    )
    assert house.position(SHADE, tilt=True) == tilt_moves[-1].position
    assert house.position(SHADE) == 100, "a tilt command moved the lift field"
    assert (
        hass.states.get(SHADE).attributes["current_tilt_position"]
        == tilt_moves[-1].position
    )
    await house.teardown()
