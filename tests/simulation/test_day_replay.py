"""Smoke tests: the simulated house drives the real integration over a day."""

import pytest

from .harness import SimHouse  # noqa: F401  (used by climate test too)


@pytest.fixture
async def house(hass, freezer):
    """A default one-shade house on the 2026 spring equinox in SLC."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    yield house
    await house.teardown()


async def test_sun_tracking_produces_moves(house):
    """Across a sunny day the integration commands the shade at least once."""
    await house.advance_to("12:00")
    moves = house.auto_moves("cover.shade")
    assert moves, "expected at least one integration-commanded move by noon"


async def test_moves_track_calculated_position(house):
    """After the shade lands, its position matches the last command."""
    await house.advance_to("13:00")
    moves = house.auto_moves("cover.shade")
    assert moves
    assert house.position("cover.shade") == moves[-1].position


async def test_night_no_tracking_moves(house):
    """Before sunrise nothing should move except at most a snap move."""
    await house.advance_to("05:30")
    for move in house.auto_moves("cover.shade"):
        assert move.position in (0, 60, 100), f"unexpected night move: {move}"


async def test_climate_mode_reacts_to_weather_and_temp(hass, freezer):
    """Climate smoke: cloudy winter opens for heat; sunny tracks the sun.

    Pins the truth-table semantics (winter+home+CLOUDY = open fully; sunny
    = glare tracking without a glare model) and proves the harness drives
    climate mode end to end — sensor writes go through the coordinator's
    real entity listeners.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        climate={"temp": 18.0, "presence": "home", "weather": "cloudy"},
    )
    await house.advance_to("12:00")
    assert house.position("cover.shade") == 100, (
        f"winter day, home, cloudy: expected fully open for passive heating; "
        f"moves: {house.auto_moves('cover.shade')}"
    )

    await house.set_weather("sunny")  # sun comes out: glare tracking resumes
    await house.advance_to("12:30")
    assert house.position("cover.shade") < 100, (
        "sunny winter day must glare-track (no glare model configured); "
        f"moves: {house.auto_moves('cover.shade', since='12:00')}"
    )
    await house.teardown()
