"""The season's hysteresis: a temperature hovering at a threshold.

The owner's house (°F; heating below 72, cooling above 75): the thermostat
holds the room at 72, so the indoor reading wobbles 71.9 <-> 72.1 °F. The
plain rule flips the season with every reading, and the shades follow; an
away house makes that visible by position alone (winter + sun: open fully;
intermediate: the default position). With the house's hysteresis set to
1 °F (the hub's number, no reload) the season holds until the reading is a
full degree past the threshold.

The hysteresis memory lives in memory only: after a restart the first
decision uses the plain rule.
"""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.adaptive_cover.const import CONF_TEMP_HYSTERESIS, DOMAIN
from custom_components.adaptive_cover.entity_surface import HUB_UNIQUE_ID

from .harness import SimHouse

SHADE = "cover.shade"
DATE = "2026-03-20"  # spring equinox: the sun is on the south glass all morning
DEFAULT_POS = 60  # CONF_DEFAULT_HEIGHT in COMMON_OPTIONS
OPEN = 100  # away + winter + sun on the glass: let the heat in
# (time, indoor reading): 10 minutes apart, so no gate holds a move back.
HOVER = [
    ("11:00", 72.1),
    ("11:10", 71.9),
    ("11:20", 72.1),
    ("11:30", 71.9),
    ("11:40", 72.1),
    ("11:50", 71.9),
    ("12:00", 72.1),
]


async def _fahrenheit_house(hass, freezer, *, temp: float = 71.9) -> SimHouse:
    hass.config.units = US_CUSTOMARY_SYSTEM
    return await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        start_at="10:00",
        climate={
            "temp": temp,
            "presence": "not_home",
            "weather": "sunny",
            "temp_low": 72.0,
            "temp_high": 75.0,
        },
    )


async def _set_house_hysteresis(hass, value: float) -> None:
    """The owner sets the hysteresis on the hub device (a house setting)."""
    number = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{HUB_UNIQUE_ID}_{CONF_TEMP_HYSTERESIS}"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": value}, blocking=True
    )
    await hass.async_block_till_done()


async def _hover(house: SimHouse) -> tuple[list[str], list[int]]:
    """Drive the wobbling reading; the season and the shade after each."""
    seasons, positions = [], []
    for hhmm, temp in HOVER:
        await house.set_temperature(temp)
        await house.advance_to(hhmm)
        seasons.append(house.sensor_value("control_method"))
        positions.append(house.position(SHADE))
    return seasons, positions


async def test_hovering_at_the_heating_threshold_flips_the_season_today(hass, freezer):
    """Without hysteresis (the default) every wobble flips the season."""
    house = await _fahrenheit_house(hass, freezer)
    await house.advance_to("10:30")
    assert house.sensor_value("control_method") == "winter"
    assert house.position(SHADE) == OPEN

    seasons, positions = await _hover(house)

    assert seasons == ["intermediate", "winter"] * 3 + ["intermediate"]
    assert positions == [DEFAULT_POS, OPEN] * 3 + [DEFAULT_POS]
    commanded = [m.position for m in house.auto_moves(SHADE, since="10:30")]
    assert commanded.count(OPEN) >= 3
    assert commanded.count(DEFAULT_POS) >= 3
    await house.teardown()


async def test_a_one_degree_hysteresis_holds_the_season(hass, freezer):
    """1 °F on the hub: the wobble moves nothing; a real change still does."""
    house = await _fahrenheit_house(hass, freezer)
    await house.advance_to("10:30")
    teardowns = house.window().teardowns
    await _set_house_hysteresis(hass, 1.0)
    assert (await house.window().settings())[CONF_TEMP_HYSTERESIS] == 1.0

    seasons, positions = await _hover(house)

    assert seasons == ["winter"] * len(HOVER)
    assert positions == [OPEN] * len(HOVER)
    assert house.auto_moves(SHADE, since="10:30") == []

    # low + hysteresis: winter ends.
    await house.set_temperature(72.9)
    await house.advance_to("12:10")
    assert house.sensor_value("control_method") == "winter"
    await house.set_temperature(73.0)
    await house.advance_to("12:20")
    assert house.sensor_value("control_method") == "intermediate"
    assert house.position(SHADE) == DEFAULT_POS

    # And back: winter again only below low - hysteresis.
    await house.set_temperature(71.5)
    await house.advance_to("12:30")
    assert house.sensor_value("control_method") == "intermediate"
    await house.set_temperature(70.9)
    await house.advance_to("12:40")
    assert house.sensor_value("control_method") == "winter"
    assert house.position(SHADE) == OPEN

    assert house.window().teardowns == teardowns, "a hysteresis change reloaded"
    await house.teardown()


async def test_the_first_decision_after_a_restart_uses_the_plain_rule(hass, freezer):
    """The memory is not restored: 72.5 °F is winter before, plain after."""
    house = await _fahrenheit_house(hass, freezer)
    await _set_house_hysteresis(hass, 1.0)
    await house.advance_to("10:30")
    await house.set_temperature(72.5)
    await house.advance_to("10:40")
    assert house.sensor_value("control_method") == "winter"  # held

    await house.restart(at="11:00")
    await house.advance_to("11:10")
    assert house.sensor_value("control_method") == "intermediate"
    assert house.position(SHADE) == DEFAULT_POS
    await house.teardown()


async def test_a_celsius_house_holds_the_season_by_half_a_degree(hass, freezer):
    """°C (HA's unit here): 21 °C heating threshold, 0.5 °C hysteresis."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        start_at="10:00",
        climate={
            "temp": 20.9,
            "presence": "not_home",
            "weather": "sunny",
            "temp_low": 21.0,
            "temp_high": 23.0,
        },
    )
    await _set_house_hysteresis(hass, 0.5)
    await house.advance_to("10:30")
    assert house.sensor_value("control_method") == "winter"
    for hhmm, temp in [("10:40", 21.1), ("10:50", 20.9), ("11:00", 21.4)]:
        await house.set_temperature(temp)
        await house.advance_to(hhmm)
        assert house.sensor_value("control_method") == "winter", hhmm
    await house.set_temperature(21.5)
    await house.advance_to("11:10")
    assert house.sensor_value("control_method") == "intermediate"
    assert house.position(SHADE) == DEFAULT_POS
    await house.teardown()
