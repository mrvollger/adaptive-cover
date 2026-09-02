"""wp5-transforms: output transforms observed only through commanded positions.

Behavior-tier simulation days for the coordinator's output-transform
pipeline (interpolation, inversion, min/max clamp), asserting exclusively
on timeline service-call values (`house.auto_moves`) and true shade
positions — never on coordinator internals.

Mutation kills (roadmap tests/refactor_roadmap.json, package wp5-transforms):

- M35 (inverse_state -> identity): test_inverse_state_commands mirrors a
  baseline day against an inverse day command-for-command.
- M36 (np.interp xp/fp swap): remapped-range asserts in the interp days
  plus the exact end-time snap value in test_end_time_snap_is_transformed.
- M37 (endpoint snap-to-0/100 removed): the pre-dawn snap and the end-time
  close must command 0, not the remapped low endpoint.
- M38 (apply both transforms when interp+inverse): the end-time close in
  test_interp_wins_over_inverse would invert 0 -> 100.
- M15 (end-time close skips the transform pipeline): the inverse close must
  command 100 and the interpolated close must command the remapped sunset
  position, not the raw option value.
- M31 corroboration (engine max clamp flip): test_max_position_never_exceeded.

All configs reuse the harness default geometry (South window, h=2.1,
d=0.5, SLC 2026-03-20) whose raw day positions are pinned by the golden
`house_equinox_privacy_basic.txt` (night sunset position 0, daytime
tracking in the low-to-mid 20s), so raw values stay comfortably below the
interpolation range's low endpoint — any un-remapped command is visible.
"""

import logging

import numpy as np

from custom_components.adaptive_cover.const import (
    CONF_ENABLE_MAX_POSITION,
    CONF_END_TIME,
    CONF_INTERP,
    CONF_INTERP_END,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_INTERP_START,
    CONF_INVERSE_STATE,
    CONF_MAX_POSITION,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

SHADE = "cover.shade"

# End time well before sunset (~19:33 on the equinox in SLC): at 18:00 the
# shade still sits at a daytime tracking position, so the timed close must
# actually deliver a command — the transform-on-snap path is exercised for
# real instead of being a no-op against an already-closed shade.
END_OF_DAY = {CONF_END_TIME: "18:00:00", CONF_RETURN_SUNSET: True}


async def make_house(hass, freezer, *, options, **kwargs):
    """One-shade house on the 2026 spring equinox in SLC."""
    return await SimHouse.create(
        hass, freezer, date="2026-03-20", options=options, **kwargs
    )


def command_positions(house, **kwargs) -> list[int]:
    """Positions of every integration command for the shade, in order."""
    return [m.position for m in house.auto_moves(SHADE, **kwargs)]


async def test_interpolation_remaps_all_commands(hass, freezer):
    """Interp 20-80: every command is remapped; full close snaps to 0.

    Kills M36 (xp/fp swap would emit raw-minus-offset values far below 20)
    and M37 (without the endpoint snap the pre-dawn and end-time closes
    would command 20 instead of 0).
    """
    house = await make_house(
        hass,
        freezer,
        options={
            **END_OF_DAY,
            CONF_INTERP: True,
            CONF_INTERP_START: 20,
            CONF_INTERP_END: 80,
        },
    )
    await house.advance_to("18:30")

    positions = command_positions(house)
    assert positions, "expected integration commands across the day"
    allowed = set(range(20, 81)) | {0, 100}
    assert all(p in allowed for p in positions), (
        f"commands escaped the remapped range [20, 80] + snaps: {positions}"
    )
    tracking = [p for p in positions if p not in (0, 100)]
    assert tracking, (
        f"expected daytime tracking commands inside (20, 80): {positions}"
    )

    # The pre-dawn snap: raw sunset position 0 maps onto the range's low
    # endpoint (20) and the endpoint rule snaps it back to a true 0.
    pre_dawn = command_positions(house, until="07:00")
    assert pre_dawn and all(p == 0 for p in pre_dawn), (
        f"pre-dawn snap must command a true full close (0): {pre_dawn}"
    )

    # The end-of-day close goes through the same transform + snap.
    evening = house.auto_moves(SHADE, since="17:50")
    assert evening, "no end-time close command on the timeline"
    assert evening[-1].position == 0, (
        f"end-time close must snap to a true 0, got {evening[-1]}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_interpolation_list_endpoint_snap(hass, freezer):
    """Paired-list interp: same remap + endpoint-snap rules on the timeline."""
    house = await make_house(
        hass,
        freezer,
        options={
            **END_OF_DAY,
            CONF_INTERP: True,
            CONF_INTERP_LIST: [0, 50, 100],
            CONF_INTERP_LIST_NEW: [20, 50, 90],
        },
    )
    await house.advance_to("18:30")

    positions = command_positions(house)
    assert positions, "expected integration commands across the day"
    allowed = set(range(20, 91)) | {0, 100}
    assert all(p in allowed for p in positions), (
        f"commands escaped the remapped range [20, 90] + snaps: {positions}"
    )
    assert [p for p in positions if p not in (0, 100)], (
        f"expected daytime tracking commands inside the list range: {positions}"
    )

    # Raw 0 maps exactly onto new_list[0]=20 and must snap to a true 0 —
    # both at the pre-dawn snap and at the end-time close.
    pre_dawn = command_positions(house, until="07:00")
    assert pre_dawn and all(p == 0 for p in pre_dawn), (
        f"pre-dawn snap must command a true full close (0): {pre_dawn}"
    )
    evening = house.auto_moves(SHADE, since="17:50")
    assert evening and evening[-1].position == 0, (
        f"end-time close must snap to a true 0, got {evening}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_end_time_snap_is_transformed(hass, freezer):
    """A non-endpoint sunset position is remapped on the end-time close.

    sunset_pos=10 with interp 20-80 must close to int(np.interp(10)) = 26:
    - M15 (transform skipped on the timed refresh) would command the raw 10;
    - M36 (xp/fp swap) would command 0 (10 sits below the swapped range).
    Geometry-free: 10 is the option value, not a computed sun position.
    """
    expected = int(np.interp(10, [0, 100], [20, 80]))  # = 26, as production
    house = await make_house(
        hass,
        freezer,
        options={
            **END_OF_DAY,
            CONF_SUNSET_POS: 10,
            CONF_INTERP: True,
            CONF_INTERP_START: 20,
            CONF_INTERP_END: 80,
        },
    )
    await house.advance_to("18:30")

    evening = house.auto_moves(SHADE, since="17:50")
    assert evening, "no end-time close command on the timeline"
    assert evening[-1].position == expected, (
        f"end-time close must command the REMAPPED sunset position "
        f"{expected}, got {evening[-1]}"
    )
    assert house.position(SHADE) == expected
    await house.teardown()


async def test_inverse_state_commands(hass, freezer):
    """Inverse on: every commanded position is 100 - the computed one.

    A baseline day and an inverse day (identical config otherwise, both
    starting at 50 so the startup snap fires in each) must produce command
    streams that are exact mirrors: same times, positions summing to 100.
    Kills M35 (identity inverse: streams become equal, not mirrored) and
    M15 (transform skipped on the timed refresh: the inverse close would
    command 0 instead of 100).
    """
    baseline = await make_house(
        hass, freezer, options={**END_OF_DAY}, initial_position=50
    )
    await baseline.advance_to("18:30")
    base_moves = [
        (m.time, m.position) for m in baseline.auto_moves(SHADE)
    ]
    await baseline.teardown()
    # The harness's service re-win guard keeps its bus listener after
    # teardown; disarm it so the dead house cannot steal the cover
    # services back from the inverse house created next.
    baseline._registering_services = True

    inverse = await make_house(
        hass,
        freezer,
        options={**END_OF_DAY, CONF_INVERSE_STATE: True},
        initial_position=50,
    )
    await inverse.advance_to("18:30")
    inv_moves = [
        (m.time, m.position) for m in inverse.auto_moves(SHADE)
    ]

    assert base_moves, "baseline day produced no integration commands"
    assert any(p != 50 for _, p in base_moves), (
        "baseline commands all 50: mirror assertion would be vacuous"
    )
    assert len(inv_moves) == len(base_moves), (
        f"command streams diverged: baseline {base_moves} vs inverse {inv_moves}"
    )
    for (base_time, base_pos), (inv_time, inv_pos) in zip(
        base_moves, inv_moves, strict=True
    ):
        assert inv_time == base_time, (
            f"command times diverged: {base_time} vs {inv_time}"
        )
        assert inv_pos == 100 - base_pos, (
            f"at {inv_time}: inverse commanded {inv_pos}, "
            f"expected {100 - base_pos} (baseline {base_pos})"
        )

    # The end-time close is inverted too: sunset_pos 0 -> commanded 100.
    evening = inverse.auto_moves(SHADE, since="17:50")
    assert evening and evening[-1].position == 100, (
        f"inverse end-time close must command 100, got {evening}"
    )
    assert inverse.position(SHADE) == 100
    await inverse.teardown()


async def test_interp_wins_over_inverse(hass, freezer, caplog):
    """Interp + inverse: inversion is skipped and the conflict is logged.

    Kills M38 (applying both transforms would invert the snapped end-time
    close from 0 to 100) and pins the explanatory log line.
    """
    caplog.set_level(logging.INFO)
    house = await make_house(
        hass,
        freezer,
        options={
            **END_OF_DAY,
            CONF_INTERP: True,
            CONF_INTERP_START: 20,
            CONF_INTERP_END: 80,
            CONF_INVERSE_STATE: True,
        },
    )
    await house.advance_to("18:30")

    assert "Inverse state is not supported with interpolation" in caplog.text, (
        "expected the interp-beats-inverse explanation in the log"
    )

    # Commands follow the interpolation-only mapping: remapped range plus
    # true snaps; the close is 0 (interp + endpoint snap, NOT inverted).
    positions = command_positions(house)
    assert positions, "expected integration commands across the day"
    allowed = set(range(20, 81)) | {0, 100}
    assert all(p in allowed for p in positions), (
        f"commands escaped the interp-only mapping: {positions}"
    )
    evening = house.auto_moves(SHADE, since="17:50")
    assert evening and evening[-1].position == 0, (
        f"close must be interp-snapped 0, not inverted to 100: {evening}"
    )
    assert house.position(SHADE) == 0
    await house.teardown()


async def test_max_position_never_exceeded(hass, freezer):
    """A max_position below the day's raw positions caps every command.

    Sim corroboration of the engine clamp (M31): with max_position=20 and
    the sun-conditional flag off, no command all day may exceed 20, and the
    daytime tracking commands (raw low-to-mid 20s) land exactly ON the cap.
    """
    house = await make_house(
        hass,
        freezer,
        options={
            CONF_MAX_POSITION: 20,
            CONF_ENABLE_MAX_POSITION: False,  # clamp applies regardless of sun
        },
    )
    await house.advance_to("14:00")

    positions = command_positions(house)
    assert positions, "expected integration commands by mid-day"
    assert all(p <= 20 for p in positions), (
        f"commands exceeded max_position=20: {positions}"
    )
    assert 20 in positions, (
        f"expected the clamp to engage (a command at exactly 20): {positions}"
    )
    assert house.position(SHADE) == 20
    await house.teardown()
