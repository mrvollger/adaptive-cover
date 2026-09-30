"""Device-failure scenarios: the integration versus misbehaving hardware.

Work package wp7-device-failures (tests/refactor_roadmap.json). Gap ids:

- delivery-failure-non-fatal: one cover's service call raising must not
  break the update loop for the others, and the failed cover must be
  re-commanded at the next eligible tick.
- unknown-position-commands-anyway: a shade whose state carries no
  current_position must still receive the end-of-day close.
- no-position-no-latch: a daytime state event without a position must
  never latch a manual override.

Plus the REAL pending-end-snap retry (a service call that genuinely
raises at the end time), replacing the historically vacuous
test_symptoms.py::test_end_time_close_retries_after_unavailable — under
the old harness the fake service never raised for unavailable shades, so
the retry bookkeeping was dead code there. The control-on case is the
designated killer of mutation M16 (retry condition on control inverted).

Every scenario drives the real integration only through public seams:
window settings, state events, service calls, and entity states.
"""

import datetime as dt

import pytest

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_END_TIME,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

SHADE = "cover.shade"


async def settle_idle(house, entity_id=SHADE, max_ticks=12):
    """Tick until the shade is idle (no travel in flight), with a guard.

    Idle means the entity reports a resting state ("open"/"closed"), not
    an opening/closing intermediate — i.e. the last command has landed
    and no new one went out on the most recent tick.
    """
    for _ in range(max_ticks):
        if house.hass.states.get(entity_id).state in ("open", "closed"):
            return
        await house.tick()
    raise AssertionError(
        f"{entity_id} never settled to an idle state within {max_ticks} ticks"
    )


# ------------------------------------------------- delivery-failure-non-fatal


async def test_service_raise_non_fatal(hass, freezer, caplog):
    """One cover's raising service call must not starve the others.

    A warning is logged, the healthy cover keeps being commanded on the
    same update loop, and the failed cover is re-commanded (its in-flight
    latch cleared) at the next eligible tick — with no manual override
    latched by the failure.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        covers=["cover.left", "cover.right"],
    )
    # Just after sunrise the sun tracks fast enough that successive
    # 5-min ticks each produce a new eligible position for both covers
    # (later in the day this geometry plateaus and commands stop).
    await house.advance_to("07:40")
    left_before = len(house.auto_moves("cover.left"))
    right_before = len(house.auto_moves("cover.right"))
    house.fail_next_command("cover.left")

    await house.advance_to("08:30")

    assert house.shades["cover.left"].fail_next is None, (
        "the injected failure was never consumed: no command ever "
        "reached the failing cover"
    )
    assert "Could not deliver" in caplog.text, (
        "delivery failure was not logged as a warning"
    )
    assert len(house.auto_moves("cover.right")) > right_before, (
        "healthy cover starved after the other cover's delivery failure"
    )
    assert len(house.auto_moves("cover.left")) > left_before, (
        "failed cover was never re-commanded after the one-shot failure"
    )
    assert house.entity("binary_sensor", "manual_override").state == "off", (
        "a delivery failure must not latch a manual override"
    )
    await house.teardown()


async def test_regression_late_delivery_not_manual(hass, freezer):
    """A send that raises but still reaches the motor is our move, not a human's.

    House, 2026-09-29 07:23: at sunrise the command to Leanne's door raised
    (Zigbee congestion, lost acknowledgement), the motor started toward the
    commanded 97% 30 s later, and that motion latched a 2 h manual override
    on the integration's own move.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20", step_minutes=1)
    # After sunrise the target keeps changing, so a command arrives soon.
    await house.advance_to("07:40")
    await settle_idle(house)
    house.fail_next_command(SHADE, deliver_after=dt.timedelta(minutes=1))
    for _ in range(120):
        await house.tick()
        if house.shades[SHADE].fail_next is None:
            break
    assert house.shades[SHADE].fail_next is None, "no command was attempted"
    # The motor starts a minute later on its own (device context) and lands.
    for _ in range(5):
        await house.tick()

    assert house.entity("binary_sensor", "manual_override").state == "off", (
        "the late start of our own failed-but-delivered command was "
        "latched as a manual override"
    )
    await house.teardown()


async def test_late_delivery_window_still_sees_humans(hass, freezer):
    """After a failed send, a human moving the other way is still manual.

    Late-delivery adoption only covers motion TOWARD the failed target;
    it must not swallow a person grabbing the remote in that window.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20", step_minutes=1)
    await house.advance_to("07:40")
    await settle_idle(house)
    house.fail_next_command(SHADE)
    for _ in range(120):
        await house.tick()
        if house.shades[SHADE].fail_next is None:
            break
    assert house.shades[SHADE].fail_next is None, "no command was attempted"
    target = int(float(house.entity("sensor", "cover_position").state))
    here = house.position(SHADE)
    assert target != here, "the failed command was a no-op"
    away = 0 if target > here else 100
    await house.user_moves(SHADE, away, via="remote")
    await house.tick()

    assert house.entity("binary_sensor", "manual_override").state == "on", (
        "a human move against the failed target was adopted as ours"
    )
    await house.teardown()


async def test_regression_missing_cover_not_commanded(hass, freezer, caplog):
    """A window whose cover entity no longer exists sends it nothing.

    House, 2026-09-29: while a physical cover was being renamed, its window
    still named the old id and commanded it on the next state change
    ("Referenced entities ... are missing"). The guard meant to stop this
    compared get_safe_state() - which maps missing to None - against
    "unavailable"/"unknown", so it never fired.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("07:40")
    await settle_idle(house)  # a landing report would re-create the entity
    removed_at = house.now
    hass.states.async_remove(SHADE)
    await hass.async_block_till_done()

    await house.advance_to("10:00")

    calls = [
        e
        for e in house.timeline
        if e.kind == "service_call" and e.entity_id == SHADE and e.time > removed_at
    ]
    assert calls == [], f"commanded a cover that does not exist: {calls}"
    assert caplog.text.count("no such entity") == 1, (
        "the missing cover should be reported once, not on every tick"
    )
    await house.teardown()


async def test_regression_late_cover_positioned_when_it_appears(hass, freezer, caplog):
    """A cover whose integration starts after ours is positioned on arrival.

    House, 2026-09-29 19:16: at boot the windows set up before Zigbee had
    created their covers, so every window logged "no such entity (renamed
    or removed?)" and skipped its command until the next sun update - a
    false alarm for a registered cover, and a slow recovery at night.
    """
    from homeassistant.helpers import entity_registry as er

    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("10:00")
    await settle_idle(house)
    hass.states.async_remove(SHADE)  # the cover's integration isn't up yet...
    er.async_get(hass).async_get_or_create(
        "cover", "zha", "late-shade", suggested_object_id=SHADE.split(".", 1)[1]
    )  # ...but the cover is registered
    await hass.async_block_till_done()
    gone_at = house.now
    await house.advance_to("10:30")
    assert not [
        e
        for e in house.timeline
        if e.kind == "service_call" and e.entity_id == SHADE and e.time > gone_at
    ], "commanded a cover that has no state yet"
    assert "no such entity" not in caplog.text, (
        "a registered cover was reported as missing"
    )

    back_at = house.now
    target = int(float(house.entity("sensor", "cover_position").state))
    away = 0 if target > 50 else 100
    house.shades[SHADE].position = away
    hass.states.async_set(
        SHADE,
        "closed" if away == 0 else "open",
        {"current_position": away, "supported_features": 15},
    )
    await hass.async_block_till_done()
    calls = [
        e
        for e in house.timeline
        if e.kind == "service_call" and e.entity_id == SHADE and e.time >= back_at
    ]
    assert calls, "the cover was not positioned when its first state arrived"
    await house.teardown()


# --------------------------------------------- unknown-position-commands-anyway


async def test_unknown_position_still_commanded(hass, freezer):
    """A shade reporting no position must still get the end-time close.

    Unknown position means the integration cannot prove the cover is in
    place — the close must be sent anyway, not silently dropped.
    """
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
    await house.advance_to("17:30")
    house.strip_position_attr(SHADE)
    # A device re-report drops current_position from hass.states.
    await house.shade_returns(SHADE)
    assert "current_position" not in hass.states.get(SHADE).attributes

    await house.advance_to("18:10")

    closes = [
        ev
        for ev in house.auto_moves(SHADE, since="18:00", until="18:10")
        if ev.position == 0
    ]
    assert closes, (
        "no close was sent at the end time to the position-less shade; "
        f"timeline: {[e for e in house.timeline if e.time.hour >= 17]}"
    )
    assert house.position(SHADE) == 0, "the shade never reached the close"
    await house.teardown()


# ----------------------------------------------------- no-position-no-latch


async def test_no_position_event_no_latch(hass, freezer):
    """A daytime state event without current_position must not latch manual.

    A report with no position (device glitch) is not evidence of a human
    move: the override sensor stays off and auto control keeps commanding
    the shade afterwards.
    """
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    # Near solar noon the position plateaus, so the shade settles idle.
    await house.advance_to("13:00")
    await settle_idle(house)
    assert house.entity("binary_sensor", "manual_override").state == "off"

    house.strip_position_attr(SHADE)
    # The device fires a state event carrying NO position attribute.
    await house.shade_returns(SHADE)
    assert "current_position" not in hass.states.get(SHADE).attributes
    assert house.entity("binary_sensor", "manual_override").state == "off", (
        "a position-less state event latched a manual override"
    )

    before = len(house.auto_moves(SHADE))
    await house.advance_to("15:00")
    assert house.entity("binary_sensor", "manual_override").state == "off", (
        "a manual override latched during position-less operation"
    )
    assert len(house.auto_moves(SHADE)) > before, (
        "auto control stopped after a position-less state event"
    )
    await house.teardown()


# ------------------------------------------------- pending end-snap retry


@pytest.mark.parametrize("control_on", [True, False], ids=["control-on", "control-off"])
async def test_pending_end_snap_real_retry(hass, freezer, caplog, control_on):
    """An end-time close whose service call RAISES is retried on return.

    The close's cover.set_cover_position genuinely raises
    (fail_next_command), the shade then drops off the network and comes
    back: with control on the missed close must be re-delivered; with
    control off it must NOT be. The control-on case kills mutation M16
    (pending-snap retry control condition inverted).

    The window faces east so the sun leaves its FOV around solar noon and
    the shade sits untouched at the default height all evening — no
    adaptive move can consume the injected failure before the end time,
    and after the end time only the retry path can close the shade.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_AZIMUTH: 90,
            CONF_END_TIME: "18:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
        },
    )
    await house.advance_to("17:50")
    assert hass.states.get(SHADE).state in ("open", "closed"), (
        "shade unexpectedly still moving before the end time"
    )
    assert house.position(SHADE) != 0, "shade must not be closed yet"

    house.fail_next_command(SHADE)
    await house.advance_to("18:05")
    assert house.shades[SHADE].fail_next is None, (
        "the end-time close never attempted a service call"
    )
    assert "Could not deliver" in caplog.text, (
        "the raising close was not logged as a delivery failure"
    )
    assert house.position(SHADE) != 0, (
        "the close was delivered despite the service call raising"
    )

    if not control_on:
        await house.toggle("toggle_control", False)

    await house.shade_goes_unavailable(SHADE)
    await house.advance_to("18:15")
    await house.shade_returns(SHADE)
    await house.advance_to("18:30")

    if control_on:
        retries = [
            ev for ev in house.auto_moves(SHADE, since="18:05") if ev.position == 0
        ]
        assert retries, (
            "missed end-of-day close was not re-delivered after the shade "
            "returned; timeline: "
            f"{[e for e in house.timeline if e.time.hour >= 17]}"
        )
        assert house.position(SHADE) == 0, "shade never closed after retry"
    else:
        assert house.auto_moves(SHADE, since="18:05") == [], (
            "the missed close was re-delivered although control is off"
        )
        assert house.position(SHADE) != 0, "shade closed although control is off"
    await house.teardown()
