"""Day replays for the non-vertical cover types (awning, venetian tilt)."""

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_LENGTH_AWNING,
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    SensorType,
)

from .harness import SimHouse

SHADE = "cover.shade"


async def test_awning_day_tracks_sun(hass, freezer):
    """An awning entry produces set_cover_position calls through the day."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-06-21",  # summer: high sun, awning geometry engages
        cover_type=SensorType.AWNING,
        options={CONF_LENGTH_AWNING: 2.1, CONF_AWNING_ANGLE: 0},
    )
    await house.advance_to("14:00")
    moves = house.auto_moves(SHADE)
    assert moves, "awning entry never commanded the cover"
    assert house.position(SHADE) == moves[-1].position
    await house.teardown()


async def test_tilt_day_uses_tilt_service(hass, freezer):
    """A venetian entry drives set_cover_TILT_position, not position."""
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
    await house.advance_to("14:00")
    moves = house.auto_moves(SHADE)
    assert moves, "tilt entry never commanded the cover"
    await house.teardown()
