"""Tilt (venetian) behavior at the service-call seam (wp8-tilt-behavior).

Drives a real venetian (``cover_tilt``) config entry through SimHouse and
asserts only on the public surfaces: the outbound service calls on the
timeline and the shades' true fields.

Mutation coverage: kills M43 (tilt entries routed to ``set_cover_position``)
and corroborates M22 (mode1/mode2 divisor swap — pinned mode2 percentages)
and M32 (climate tilt preset swap — pinned 80/45-degree preset positions)
at the service-call level. Manual tilt detection is asserted purely via
timeline ``auto_moves`` after a remote tilt change vs the landing of the
integration's own tilt command.
"""

from custom_components.adaptive_cover.const import (
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    SensorType,
)

from .harness import SimHouse

SHADE = "cover.shade"

# 3 cm slats spaced 2 cm apart, bidirectional (mode2: 0-180 deg range).
TILT_GEOMETRY = {
    CONF_TILT_DEPTH: 3,
    CONF_TILT_DISTANCE: 2,
    CONF_TILT_MODE: "mode2",
}


async def make_tilt_house(hass, freezer, *, options=None, climate=None):
    """A one-shade venetian house on the 2026 summer solstice in SLC."""
    return await SimHouse.create(
        hass,
        freezer,
        date="2026-06-21",
        cover_type=SensorType.TILT,
        options={**TILT_GEOMETRY, **(options or {})},
        climate=climate,
    )


async def test_tilt_commands_use_tilt_service(hass, freezer):
    """A full tilt day rides set_cover_tilt_position exclusively.

    Kills M43: with tilt entries routed to set_cover_position the tilt
    service is never called (and the fake position handler rejects the
    tilt_position payload), so the tilt-service timeline stays empty.

    Corroborates M22: the pinned mode2 percentages (85 at solar noon,
    calculated band capped at 99) come from dividing the slat angle by
    180; the divisor swap doubles them into the 100-clip.
    """
    house = await make_tilt_house(hass, freezer)
    await house.advance_to("21:30")

    tilt_moves = house.auto_moves(SHADE, service="set_cover_tilt_position")
    assert tilt_moves, "tilt entry never commanded the cover via tilt service"
    assert house.moves(SHADE, actor="integration", service="set_cover_position") == [], (
        "a venetian entry must never call set_cover_position"
    )
    assert all(ev.service == "set_cover_tilt_position" for ev in house.auto_moves(SHADE))

    positions = [ev.position for ev in tilt_moves]
    # Pre-dawn snap to the sunset position, then the post-sunrise default.
    assert positions[0] == 0, f"expected pre-dawn sunset position 0, got {positions}"
    assert 60 in positions, f"expected default position 60 after sunrise: {positions}"
    # Solar noon, mode2: slat angle / 180 -> 85%. The divisor swap (M22)
    # would double this into the clip at 100.
    noon = house.auto_moves(SHADE, since="12:00", until="12:10")
    assert [ev.position for ev in noon] == [85], f"solar-noon tilt: {noon}"
    calculated = [
        ev.position
        for ev in house.auto_moves(SHADE, since="09:30", until="17:25")
    ]
    assert calculated and max(calculated) == 99 and min(calculated) == 84, (
        f"mode2 calculated band should span 84-99, never clip to 100: {calculated}"
    )
    # Evening: back to default when the sun leaves the FOV, sunset close after.
    assert positions[-1] == 0, f"expected sunset close 0 last, got {positions[-1]}"
    assert house.position(SHADE, tilt=True) == 0

    # The lift field must be untouched: only tilt was ever driven.
    assert house.position(SHADE) == 100, "lift position moved on a tilt-only entry"
    await house.teardown()


async def test_tilt_manual_detection(hass, freezer):
    """A remote tilt move latches manual; our own tilt landings never do.

    Asserted purely via timeline auto_moves: the integration keeps issuing
    tilt commands all morning across its own landings (no self-latch), but
    goes silent for hours after a human tilt move lands — instead of
    reverting the human's 30 back to the calculated track.
    """
    house = await make_tilt_house(
        hass,
        freezer,
        options={CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8}},
    )
    await house.advance_to("13:00")

    # Own landings do not latch: every ~5-min command lands two minutes
    # later, and the stream of sun-tracking commands keeps flowing.
    morning = house.auto_moves(SHADE, since="09:30", until="13:00")
    assert len(morning) >= 5, (
        f"own tilt landings latched as manual — tracking stopped: {morning}"
    )

    # 13:00 is a quiet spot (calculated == last command == 84): the human
    # tilts the slats to 30 with the physical remote.
    assert house.position(SHADE, tilt=True) == 84
    await house.user_moves(SHADE, 30, via="remote", tilt=True)
    await house.advance_to("13:10")
    assert house.position(SHADE, tilt=True) == 30, "remote tilt move never landed"

    # Latched: for the rest of the afternoon (the un-overridden day has
    # moves at 14:25, 15:00, ... and a revert of the 54-point diff) the
    # integration must not command this cover.
    await house.advance_to("16:00")
    assert house.auto_moves(SHADE, since="13:01") == [], (
        "manual tilt override did not latch — integration kept commanding"
    )
    assert house.position(SHADE, tilt=True) == 30
    await house.teardown()


async def test_climate_tilt_preset_day(hass, freezer):
    """Climate tilt presets surface on the timeline as conditions change.

    mode2 percentages: 80-deg presence preset -> 44, 45-deg dim-summer
    preset -> 25, away+summer -> fully closed 0. Kills/corroborates M32:
    the preset swap trades the 44 and 25 branches.
    """
    house = await make_tilt_house(
        hass,
        freezer,
        climate={
            "temp": 26.0,  # > temp_high: summer
            "presence": "home",
            "weather": "sunny",
            "temp_low": 18.0,
            "temp_high": 23.0,
        },
    )

    # Home + sunny (summer): the 80-degree presence preset (80/180 -> 44).
    await house.advance_to("12:00")
    moves = house.auto_moves(SHADE)
    assert moves and moves[-1].position == 44, (
        f"home+sunny expected the 80-deg preset (44): {moves}"
    )
    await house.advance_to("12:04")  # let the preset move land
    assert house.position(SHADE, tilt=True) == 44

    # Clouds roll in, still summer + home: the 45-degree preset (45/180 -> 25).
    await house.set_weather("cloudy")
    await house.advance_to("12:30")
    dim = house.auto_moves(SHADE, since="12:00")
    assert dim and dim[-1].position == 25, (
        f"dim summer expected the 45-deg preset (25): {dim}"
    )
    assert house.position(SHADE, tilt=True) == 25

    # Everyone leaves on a hot day: close fully to block heat gain.
    await house.set_presence("not_home")
    await house.advance_to("13:30")
    away = house.auto_moves(SHADE, since="12:30")
    assert away and away[-1].position == 0, (
        f"away+summer expected fully closed (0): {away}"
    )
    assert house.position(SHADE, tilt=True) == 0

    # The climate path also rides the tilt service exclusively.
    assert house.moves(SHADE, actor="integration", service="set_cover_position") == []
    await house.teardown()
