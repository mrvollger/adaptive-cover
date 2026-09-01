"""Tests closing the holes the 2026-09-01 mutation audit proved.

Four injected refactor mistakes survived the ENTIRE suite; each test here
kills one (the fourth — pending-retry — is killed by the now-faithful
unavailable-raises harness plus the existing retry scenario).
"""

from custom_components.adaptive_cover.const import (
    CONF_END_TIME,
    CONF_INTERP,
    CONF_INTERP_END,
    CONF_INTERP_START,
    CONF_INVERSE_STATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_RETURN_SUNSET,
    CONF_SUNSET_POS,
)

from .harness import SimHouse

SHADE = "cover.shade"


async def test_on_time_close_overrides_active_manual(hass, freezer):
    """The ON-TIME end close bulldozes an ACTIVE manual override.

    (Mutation survived: catch-up flag inverted, making on-time closes skip
    overridden covers — shades a human opened would stay open all night.)
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_END_TIME: "18:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
            CONF_MANUAL_OVERRIDE_DURATION: {"hours": 8},
        },
    )
    await house.advance_to("17:30")
    await house.user_moves(SHADE, 100, via="remote")
    assert house.coordinator.manager.is_cover_manual(SHADE)

    await house.advance_to("19:00")
    assert house.position(SHADE) == 0, (
        "the scheduled close must win over an active override at its "
        f"moment; evening: {[e for e in house.timeline if e.time.hour >= 17]}"
    )
    await house.teardown()


async def test_end_close_applies_inverse_transform(hass, freezer):
    """With inverse_state, the timed close sends the INVERTED sunset value.

    (Mutation survived: transform pipeline skipped on the end-of-day close,
    sending the raw configured value to inverted/interpolated covers.)
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_END_TIME: "18:00:00",
            CONF_RETURN_SUNSET: True,
            CONF_SUNSET_POS: 0,
            CONF_INVERSE_STATE: True,
        },
    )
    await house.advance_to("19:00")
    closes = list(house.auto_moves(SHADE, since="17:55"))
    assert closes and closes[-1].position == 100, (
        "inverse cover: end close must command 100 (inverse of sunset 0); "
        f"got {closes}"
    )
    await house.teardown()


async def test_interpolation_maps_tracking_commands(hass, freezer):
    """Custom interpolation range remaps every tracking command.

    (Gap: interpolation had zero tests anywhere; a swapped np.interp
    argument order survived the whole suite.)
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={
            CONF_INTERP: True,
            CONF_INTERP_START: 25,
            CONF_INTERP_END: 75,
        },
    )
    await house.advance_to("14:00")
    moves = house.auto_moves(SHADE)
    assert moves, "no tracking moves to check"
    # Endpoint quirk: values landing exactly on the range ends snap to 0/100.
    for m in moves:
        assert m.position in (0, 100) or 25 <= m.position <= 75, (
            f"command outside the interpolation range: {m}"
        )
    assert any(25 < m.position < 75 for m in moves), (
        f"no command strictly inside the remapped range: {moves}"
    )
    await house.teardown()
