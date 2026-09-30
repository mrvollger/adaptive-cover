"""A restart or reload in the middle of a move (house, 2026-09-30).

At the 07:23 sunrise the integration told the Den southwest shade 5 -> 97.
ZHA reported ``opening`` (still at 5) and Home Assistant restarted seconds
later for an upgrade, which cut the move short. After the restart ZHA
reported ``opening`` again and then ``open`` at 5. The new coordinator had
not sent that command, read the landing as a person's move ("manual change
detected") and put the window on Hold for 2 h.

Pins, through the timeline and entity states only:

- a move under way when the window (re)starts has unknown provenance: its
  reports and its landing are never a manual move, whatever the boot order
  of Zigbee and the integration, and the window decides again at once;
- a person is still seen right after a restart: a remote move of a shade
  at rest, a move against the direction of the move under way, and a move
  after a stale restored ``opening``/``closing`` has timed out all latch.
"""

import pytest

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_DEFAULT_HEIGHT,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

DEN_SW = "cover.den_southwest_shades"
DATE = "2026-09-30"
# The Den southwest window: it faces 235 degrees, rests at 97 by day and 5
# by night, and holds a manual move for 2 h.
OPTIONS = {
    CONF_AZIMUTH: 235,
    CONF_DEFAULT_HEIGHT: 97,
    CONF_SUNSET_POS: 5,
    CONF_MANUAL_OVERRIDE_DURATION: {"hours": 2},
}


async def sunrise_open(hass, freezer) -> SimHouse:
    """The house at the 2026-09-30 sunrise: the window has just sent 5 -> 97."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        covers=[DEN_SW],
        step_minutes=1,
        initial_position=5,
        options=OPTIONS,
    )
    await house.advance_to("07:15")
    assert house.auto_moves(DEN_SW) == [], "moved before sunrise"
    for _ in range(30):
        await house.tick()
        if house.auto_moves(DEN_SW):
            break
    assert [move.position for move in house.auto_moves(DEN_SW)] == [97]
    assert hass.states.get(DEN_SW).state == "opening"
    return house


def assert_not_held(house: SimHouse) -> None:
    """The window is not under manual control."""
    window = house.window(DEN_SW)
    assert not window.is_manual, "a move the window did not see start was latched"
    assert not window.manual_override
    assert window.mode == "auto"


@pytest.mark.parametrize(
    "boot",
    [
        # The house on 2026-09-30: Zigbee came up after Home Assistant had
        # started, so the cover held HA's unavailable placeholder first.
        "zigbee_after_ha_start",
        # Zigbee came up after the integration, before HA's placeholder.
        "zigbee_before_ha_start",
        # The cover already read "opening" when the window set up (Zigbee
        # first, or an entry reload).
        "cover_moving_at_setup",
        # The motor carried on across the restart and reported on its way.
        "motor_carries_on",
    ],
)
async def test_regression_restart_mid_travel_not_manual(hass, freezer, boot):
    """A restart in the middle of the window's own move is not a manual move.

    House, 2026-09-30 07:23 (see the module docstring): the landing of a
    move the new coordinator had not sent held the window for 2 h.
    """
    house = await sunrise_open(hass, freezer)
    if boot != "motor_carries_on":
        house.stop_motor(DEN_SW)  # the restart cut the journey short
    if boot == "cover_moving_at_setup":
        await house.restart(cold=True)
    else:
        await house.restart(cold=True, covers_late=True)
        if boot != "zigbee_before_ha_start":
            await house.shade_goes_unavailable(DEN_SW)  # HA's placeholder
        # ZHA restores the state it had before the restart.
        await house.device_reports(DEN_SW, "opening")

    if boot == "motor_carries_on":
        await house.device_reports(DEN_SW, "opening", position=50)
        assert_not_held(house)
        await house.advance_to("07:27")
        assert house.position(DEN_SW) == 97
    else:
        sent = len(house.auto_moves(DEN_SW))
        await house.device_reports(DEN_SW)  # stopped where it started: 5
        assert_not_held(house)
        if boot == "zigbee_after_ha_start":
            # Nothing was sent since the restart (the cover was away): the
            # landing makes the window decide again, at once.
            assert [m.position for m in house.auto_moves(DEN_SW)[sent:]] == [97]
        await house.advance_to("07:30")
        assert house.position(DEN_SW) == 97, "the shade was left short of 97"
    assert_not_held(house)
    await house.teardown()


async def advance_until_idle(house: SimHouse) -> None:
    """Tick until the shade rests (bounded)."""
    for _ in range(10):
        if house.hass.states.get(DEN_SW).state in ("open", "closed"):
            return
        await house.tick()
    raise AssertionError(f"{DEN_SW} never came to rest")


@pytest.mark.parametrize(
    "case",
    [
        # The shade rests when HA comes back; a person closes it at once.
        "remote_right_after_restart",
        # A person closes the shade the restart caught opening.
        "against_the_move_under_way",
        # ZHA restored a stale "closing"; minutes later a person closes it.
        "after_a_stale_motion_state",
    ],
)
async def test_manual_move_right_after_restart_still_latches(hass, freezer, case):
    """A person moving a shade right after a restart is still a manual move.

    Only the move under way when the window started is excused, while it
    runs in its own direction and for at most the travel time.
    """
    house = await sunrise_open(hass, freezer)
    if case == "against_the_move_under_way":
        house.stop_motor(DEN_SW)
    else:
        await advance_until_idle(house)
        assert house.position(DEN_SW) == 97
    await house.restart(cold=True, covers_late=True)
    await house.shade_goes_unavailable(DEN_SW)  # HA's placeholder
    if case == "remote_right_after_restart":
        await house.device_reports(DEN_SW)  # ZHA restores: open at 97
    elif case == "against_the_move_under_way":
        await house.device_reports(DEN_SW, "opening")
    else:
        await house.device_reports(DEN_SW, "closing")
        await house.advance_to("07:40")  # longer than any travel

    await house.user_moves(DEN_SW, 0, via="remote")
    if case == "after_a_stale_motion_state":
        # The "closing" repeats the restored state (HA sends no event), so
        # the landing is the first sign of the person.
        await advance_until_idle(house)
    window = house.window(DEN_SW)
    assert window.is_manual, "a person's move right after a restart was missed"
    assert window.mode == "hold"
    sent = len(house.auto_moves(DEN_SW))
    await house.advance_to("08:30")
    assert house.auto_moves(DEN_SW)[sent:] == [], "the person was reverted"
    assert house.position(DEN_SW) == 0
    await house.teardown()
