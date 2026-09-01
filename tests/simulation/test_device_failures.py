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
config entry options, state events, service calls, and entity states.
"""

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


@pytest.mark.parametrize(
    "control_on", [True, False], ids=["control-on", "control-off"]
)
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
            ev
            for ev in house.auto_moves(SHADE, since="18:05")
            if ev.position == 0
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
        assert house.position(SHADE) != 0, (
            "shade closed although control is off"
        )
    await house.teardown()
