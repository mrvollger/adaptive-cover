"""wp3-climate-matrix: climate-mode behavior driven through public seams only.

Every scenario runs the REAL integration inside SimHouse and asserts only
via commanded positions on the timeline, the shades' landed positions, and
entity states (control-method sensor, real toggle switches). No coordinator
internals, no manager reads, no private attributes.

Season/presence/weather semantics under test (the climate matrix):

- away + summer + sun in FOV  -> close fully (0)
- away + winter + sun in FOV  -> open fully (100)
- away + intermediate         -> default position (sunset position after dark)
- home + intermediate + sunny -> climate-neutral: identical to basic mode
- home + winter + dim/cloudy  -> open fully; sunny -> glare tracking
- is_summer is an AND of inside temp > temp_high and outside temp > outside
  threshold (when configured)
- lux/irradiance below threshold count as "dim" only while their toggle
  switches are on; the Outside Temperature switch swaps the season input
"""

import pytest

from custom_components.adaptive_cover.const import (
    CONF_TILT_DEPTH,
    CONF_TILT_DISTANCE,
    CONF_TILT_MODE,
    CONF_WEATHER_ENTITY,
    SensorType,
)

from .harness import SimHouse

SHADE = "cover.shade"
DATE = "2026-03-20"  # spring equinox in SLC: sunrise ~07:33, sunset ~19:33
DEFAULT_POS = 60  # CONF_DEFAULT_HEIGHT in COMMON_OPTIONS
SUNSET_POS = 0  # CONF_SUNSET_POS in COMMON_OPTIONS


def _tracking(position: int) -> bool:
    """True for a glare-tracking position: partial, neither snap endpoint."""
    return 0 < position < 100


# --------------------------------------------------------- away branches


async def test_away_summer_closes(hass, freezer):
    """Hot day, nobody home, sunny: close fully while the sun is in the FOV."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={"temp": 26.0, "presence": "not_home", "weather": "sunny"},
    )
    await house.advance_to("12:00")

    assert house.position(SHADE) == 0, (
        f"away+summer+sun in FOV must close fully; "
        f"moves: {house.auto_moves(SHADE)}"
    )
    closes = [m for m in house.auto_moves(SHADE) if m.position == 0]
    assert closes, "no close command was ever issued"

    # Midday stays closed: no command reopens while conditions hold.
    await house.advance_to("14:00")
    assert house.position(SHADE) == 0
    reopen = [
        m for m in house.auto_moves(SHADE, since="12:00") if m.position != 0
    ]
    assert reopen == [], f"away+summer reopened mid-day: {reopen}"
    await house.teardown()


async def test_away_cloudy_default_then_sunset(hass, freezer):
    """Intermediate temp, nobody home: default all day, sunset position after dark."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 22.0,  # between temp_low 21 and temp_high 23
            "presence": "not_home",
            "weather": "cloudy",
        },
    )
    await house.advance_to("12:00")
    assert house.position(SHADE) == DEFAULT_POS, (
        f"away+intermediate day must rest at the default position; "
        f"moves: {house.auto_moves(SHADE)}"
    )

    # The whole afternoon holds the default: no tracking, no close.
    await house.advance_to("19:00")
    daytime = house.auto_moves(SHADE, since="10:00", until="19:00")
    assert all(m.position == DEFAULT_POS for m in daytime), (
        f"non-default daytime moves for an away+cloudy intermediate day: {daytime}"
    )

    await house.advance_to("20:00")  # sunset ~19:33
    assert house.position(SHADE) == SUNSET_POS, (
        "after dark the away house must sit at the sunset position"
    )
    await house.teardown()


# --------------------------------------------- climate-neutral fallthrough


async def test_intermediate_temp_equals_basic(hass, freezer):
    """Home + intermediate + sunny commands exactly what basic mode commands."""
    climate_house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={"temp": 22.0, "presence": "home", "weather": "sunny"},
    )
    await climate_house.advance_to("14:00")
    climate_cmds = [
        (ev.time, ev.position) for ev in climate_house.auto_moves(SHADE)
    ]
    await climate_house.teardown()
    # The harness's service re-win guard keeps its bus listener after
    # teardown; disarm it so the dead house cannot steal the cover
    # services back from the basic house created next.
    climate_house._registering_services = True

    basic_house = await SimHouse.create(hass, freezer, date=DATE)
    await basic_house.advance_to("14:00")
    basic_cmds = [
        (ev.time, ev.position) for ev in basic_house.auto_moves(SHADE)
    ]
    await basic_house.teardown()

    assert climate_cmds, "climate-neutral day produced no commands at all"
    assert climate_cmds == basic_cmds, (
        "home+intermediate+sunny must fall through to the basic strategy: "
        f"climate={climate_cmds} basic={basic_cmds}"
    )


# ------------------------------------------------- season from thresholds


async def test_season_flips_across_thresholds(hass, freezer):
    """Driving temp across the thresholds flips default->open->close.

    Away keeps the three seasons distinguishable by position alone:
    intermediate=default, winter=fully open, summer=fully closed. The
    control-method sensor reads intermediate/winter/summer at each stage.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 22.0,  # intermediate: between 21 and 23
            "presence": "not_home",
            "weather": "sunny",
        },
    )
    await house.advance_to("11:00")
    assert house.position(SHADE) == DEFAULT_POS
    assert house.sensor_value("control_method") == "intermediate"

    await house.set_temperature(18.0)  # below temp_low -> winter
    await house.advance_to("11:20")
    assert house.position(SHADE) == 100, (
        f"winter+away must open fully; moves: {house.auto_moves(SHADE, since='11:00')}"
    )
    assert house.sensor_value("control_method") == "winter"

    await house.set_temperature(26.0)  # above temp_high -> summer
    await house.advance_to("11:40")
    assert house.position(SHADE) == 0, (
        f"summer+away must close fully; moves: {house.auto_moves(SHADE, since='11:20')}"
    )
    assert house.sensor_value("control_method") == "summer"
    await house.teardown()


async def test_outside_temp_and_rule(hass, freezer):
    """is_summer requires BOTH inside > temp_high AND outside > threshold."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 26.0,  # inside says summer
            "presence": "not_home",
            "weather": "sunny",
            "outside_temp": 15.0,  # outside says no
            "outside_threshold": 20.0,
        },
    )
    await house.advance_to("12:00")
    assert house.position(SHADE) == DEFAULT_POS, (
        "hot inside but cool outside is NOT summer (AND rule): expected the "
        f"intermediate default; moves: {house.auto_moves(SHADE)}"
    )
    assert house.sensor_value("control_method") == "intermediate"

    await house.set_outside_temp(30.0)  # now both sides of the AND hold
    await house.advance_to("12:20")
    assert house.position(SHADE) == 0, (
        f"summer close missing once outside crossed the threshold; "
        f"moves: {house.auto_moves(SHADE, since='12:00')}"
    )
    assert house.sensor_value("control_method") == "summer"
    await house.teardown()


# --------------------------------------------------- sensor resilience


async def test_sensor_garbage_resilience(hass, freezer):
    """Garbage/unavailable climate inputs mid-day never stop the update loop."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 18.0,  # winter
            "presence": "home",
            "weather": "sunny",
            "lux": 2000,  # bright: not dim
            "lux_threshold": 1000,
        },
    )
    await house.advance_to("13:00")
    assert house.auto_moves(SHADE), "no moves before the garbage even arrived"

    await house.set_temperature("borked")
    await house.set_weather("unknown")
    await house.set_lux("unavailable")
    await house.advance_to("13:30")
    assert house.coordinator.last_update_success, (
        "garbage climate inputs killed the coordinator update loop"
    )
    assert house.auto_moves(SHADE, since="13:00"), (
        "no commands at all after garbage sensor values"
    )

    # The day still ends properly: the sunset snap goes out after dark.
    await house.advance_to("20:00")
    closes = [
        m for m in house.auto_moves(SHADE, since="19:30") if m.position == 0
    ]
    assert closes, "the sunset close never fired after garbage inputs"
    assert house.coordinator.last_update_success
    await house.teardown()


# --------------------------------------------------- presence domains


@pytest.mark.parametrize(
    ("domain", "state", "home"),
    [
        ("zone", "0", False),
        ("zone", "2", True),
        ("binary_sensor", "off", False),
        ("binary_sensor", "on", True),
        ("input_boolean", "on", True),
        # An unavailable presence entity defaults to "someone is home".
        ("device_tracker", "unavailable", True),
    ],
)
async def test_presence_domains(hass, freezer, domain, state, home):
    """Each presence domain resolves home/away, asserted via positions.

    Summer + sunny separates the branches: home glare-tracks (partial
    position), away closes fully.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 26.0,
            "presence": state,
            "presence_domain": domain,
            "weather": "sunny",
        },
    )
    await house.advance_to("12:00")
    position = house.position(SHADE)
    if home:
        assert _tracking(position), (
            f"{domain}={state} must count as home (glare tracking), got "
            f"{position}; moves: {house.auto_moves(SHADE)}"
        )
    else:
        assert position == 0, (
            f"{domain}={state} must count as away (summer close), got "
            f"{position}; moves: {house.auto_moves(SHADE)}"
        )
    await house.teardown()


# --------------------------------------------------- weather tri-state


async def test_weather_no_entity_always_sunny(hass, freezer):
    """Without a weather entity the sky counts as sunny: winter glare-tracks."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={"temp": 18.0, "presence": "home", "weather": "cloudy"},
        options={CONF_WEATHER_ENTITY: None},
    )
    await house.advance_to("12:00")
    assert _tracking(house.position(SHADE)), (
        "no weather entity means always-sunny: a winter day must glare-track, "
        f"not open fully; moves: {house.auto_moves(SHADE)}"
    )
    await house.teardown()


async def test_weather_empty_condition_list_never_sunny(hass, freezer):
    """An empty sunny-condition list means no condition is ever sunny."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 18.0,
            "presence": "home",
            "weather": "sunny",
            "weather_condition": [],
        },
    )
    await house.advance_to("12:00")
    assert house.position(SHADE) == 100, (
        "empty condition list: 'sunny' is not sunny, winter+cloudy opens "
        f"fully; moves: {house.auto_moves(SHADE)}"
    )
    await house.teardown()


# ------------------------------------------- lux / irradiance thresholds


async def test_lux_threshold_and_switch(hass, freezer):
    """Lux below threshold flips winter to fully-open; the Lux switch gates it."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 18.0,  # winter
            "presence": "home",
            "weather": "sunny",
            "lux": 450,  # below threshold: dim
            "lux_threshold": 1000,
        },
    )
    await house.advance_to("12:00")
    assert house.position(SHADE) == 100, (
        f"winter + dim (lux below threshold) must open fully; "
        f"moves: {house.auto_moves(SHADE)}"
    )

    await house.toggle("lux", False)  # stop consulting the lux sensor
    await house.advance_to("12:30")
    assert _tracking(house.position(SHADE)), (
        "with the Lux switch off a sunny winter day must glare-track; "
        f"moves: {house.auto_moves(SHADE, since='12:00')}"
    )

    await house.toggle("lux", True)  # dim counts again
    await house.advance_to("13:00")
    assert house.position(SHADE) == 100, (
        f"Lux switch back on: dim-open must resume; "
        f"moves: {house.auto_moves(SHADE, since='12:30')}"
    )
    await house.teardown()


async def test_irradiance_threshold_and_switch(hass, freezer):
    """Same shape through the irradiance entity and its toggle switch."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 18.0,  # winter
            "presence": "home",
            "weather": "sunny",
            "irradiance": 250,  # below threshold: dim
            "irradiance_threshold": 300,
        },
    )
    await house.advance_to("12:00")
    assert house.position(SHADE) == 100, (
        f"winter + dim (irradiance below threshold) must open fully; "
        f"moves: {house.auto_moves(SHADE)}"
    )

    await house.toggle("irradiance", False)
    await house.advance_to("12:30")
    assert _tracking(house.position(SHADE)), (
        "with the Irradiance switch off a sunny winter day must glare-track; "
        f"moves: {house.auto_moves(SHADE, since='12:00')}"
    )

    await house.toggle("irradiance", True)
    await house.advance_to("13:00")
    assert house.position(SHADE) == 100, (
        f"Irradiance switch back on: dim-open must resume; "
        f"moves: {house.auto_moves(SHADE, since='12:30')}"
    )
    await house.teardown()


# ------------------------------------------------ outside-temp toggle


async def test_outside_temp_toggle_and_fallback(hass, freezer):
    """The Outside Temperature switch swaps the season input; unavailable
    outside readings fall back to the inside sensor."""
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        climate={
            "temp": 18.0,  # inside says winter
            "presence": "not_home",
            "weather": "sunny",
            "outside_temp": 30.0,  # outside says summer
        },
    )
    await house.advance_to("12:00")
    # The Outside Temperature switch defaults OFF: inside temp rules.
    assert house.entity("switch", "outside_temperature").state == "off"
    assert house.position(SHADE) == 100, (
        f"toggle off: inside 18 is winter, away opens fully; "
        f"moves: {house.auto_moves(SHADE)}"
    )
    assert house.sensor_value("control_method") == "winter"

    await house.toggle("outside_temperature", True)
    await house.advance_to("12:20")
    assert house.position(SHADE) == 0, (
        f"toggle on: outside 30 is summer, away closes fully; "
        f"moves: {house.auto_moves(SHADE, since='12:00')}"
    )
    assert house.sensor_value("control_method") == "summer"

    await house.set_outside_temp("unavailable")
    await house.advance_to("12:40")
    assert house.position(SHADE) == 100, (
        "outside sensor unavailable: season must fall back to the inside "
        f"reading (winter); moves: {house.auto_moves(SHADE, since='12:20')}"
    )
    assert house.sensor_value("control_method") == "winter"
    await house.teardown()


# ------------------------------------------------- tilt climate presets


async def test_climate_tilt_presence_presets(hass, freezer):
    """Tilt presets at the service-call level: presence 80 deg, summer-dim 45.

    mode1 scales over 90 deg, so the presets land at distinct positions:
    80 deg -> 89 %, 45 deg -> 50 %. Corroborates the engine preset table
    (mutation M32) through real set_cover_tilt_position commands.
    """
    house = await SimHouse.create(
        hass,
        freezer,
        date=DATE,
        cover_type=SensorType.TILT,
        options={
            CONF_TILT_DEPTH: 3,
            CONF_TILT_DISTANCE: 2,
            CONF_TILT_MODE: "mode1",
        },
        climate={
            "temp": 26.0,  # summer
            "presence": "home",
            "weather": "sunny",
            "lux": 2000,  # bright: not dim
            "lux_threshold": 1000,
        },
    )
    await house.advance_to("12:00")
    tilt_moves = house.auto_moves(SHADE, service="set_cover_tilt_position")
    assert tilt_moves == house.auto_moves(SHADE), (
        "climate tilt entry commanded through set_cover_position"
    )
    assert house.position(SHADE, tilt=True) == 89, (
        f"home + bright: expected the 80-degree preset (89 %); "
        f"moves: {tilt_moves}"
    )

    await house.set_lux(100)  # below threshold: dim summer
    await house.advance_to("12:20")
    assert house.position(SHADE, tilt=True) == 50, (
        "summer + dim: expected the 45-degree preset (50 %); moves: "
        f"{house.auto_moves(SHADE, since='12:00')}"
    )
    await house.teardown()
