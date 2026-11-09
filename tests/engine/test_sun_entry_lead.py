"""Sun entry lead: act on a window a few minutes before the sun enters it.

``TimeContext.sun_ahead`` is the sun one ``sun_entry_lead`` from now. When
the sun is outside the window now but inside it then, the engine decides
on that sun; leaving is never led. Pure engine, explicit inputs.
"""

from datetime import datetime, timedelta

import pytest

from custom_components.adaptive_cover.engine import (
    ClimateInputs,
    CoverConfig,
    GlareModel,
    Intent,
    SunSnapshot,
    TimeContext,
    evaluate,
    geometry,
)

SUNRISE = datetime(2026, 11, 9, 14, 0)
SUNSET = datetime(2026, 11, 10, 0, 10)
NOW = datetime(2026, 11, 9, 14, 40)

# A south-east glass door: azimuth 145, 40 deg either side, sun 5-40 deg up.
OUTSIDE = SunSnapshot(azimuth=118.0, elevation=4.6)  # below min_elevation
INSIDE = SunSnapshot(azimuth=119.0, elevation=5.6)  # five minutes later
WINTER_SUNNY_HOME = ClimateInputs(presence=True, is_winter=True, is_sunny=True)


def door(**kw):
    defaults = dict(
        cover_type="vertical",
        window_azimuth=145,
        fov_left=40,
        fov_right=40,
        default_position=100,
        sunset_position=3,
        min_elevation=5,
        max_elevation=40,
        distance_shaded_area=0.1,
        window_height=2.0,
        glare=GlareModel(eye_height=1.0, occupied_distance=2.0),
    )
    defaults.update(kw)
    return CoverConfig(**defaults)


def ctx(sun_ahead):
    return TimeContext(
        now_utc=NOW, sunrise_utc=SUNRISE, sunset_utc=SUNSET, sun_ahead=sun_ahead
    )


def test_sun_entering_needs_sun_outside_now_and_inside_ahead():
    config = door()
    assert geometry.sun_entering(config, OUTSIDE, ctx(INSIDE))
    assert not geometry.sun_entering(config, INSIDE, ctx(INSIDE))
    assert not geometry.sun_entering(config, OUTSIDE, ctx(OUTSIDE))
    assert not geometry.sun_entering(config, OUTSIDE, ctx(None))


def test_lead_acts_on_the_arriving_sun():
    """Basic strategy: the cover is at the entry position before the beam."""
    config = door(glare=None)
    led = evaluate(config, OUTSIDE, ctx(INSIDE))
    at_entry = evaluate(config, INSIDE, ctx(None))
    assert led.position == at_entry.position
    assert led.intent == at_entry.intent == Intent.CALCULATED
    assert led.trace[0].startswith("sun enters the window within the entry lead")


def test_lead_engages_the_winter_glare_band_early():
    """Winter, sunny, someone home: admit warmth to the eye band, early."""
    config = door()
    led = evaluate(config, OUTSIDE, ctx(INSIDE), WINTER_SUNNY_HOME)
    at_entry = evaluate(config, INSIDE, ctx(None), WINTER_SUNNY_HOME)
    assert led.intent == at_entry.intent == Intent.ADMIT_NO_GLARE
    assert led.position == at_entry.position


def test_no_lead_keeps_the_default_until_the_sun_arrives():
    config = door()
    decision = evaluate(config, OUTSIDE, ctx(None), WINTER_SUNNY_HOME)
    assert (decision.position, decision.intent) == (100, Intent.DEFAULT)


@pytest.mark.parametrize("ahead", [OUTSIDE, None], ids=["sun_ahead_out", "no_lead"])
def test_leaving_is_not_led(ahead):
    """A sun still in the window is decided on as it is now."""
    config = door(glare=None)
    decision = evaluate(config, INSIDE, ctx(ahead))
    assert decision.intent == Intent.CALCULATED
    assert decision.trace == evaluate(config, INSIDE, ctx(None)).trace


def test_lead_still_respects_the_sunrise_offset():
    """Before sunrise + offset the sunset position holds, lead or not."""
    config = door(glare=None, sunrise_offset_min=60)
    decision = evaluate(config, OUTSIDE, ctx(INSIDE))
    assert decision.intent == Intent.SUNSET


def test_forecast_style_step_sees_entry_one_lead_early():
    """Sweep a sun table: with the lead the change point comes earlier."""
    config = door(glare=None)
    times = [NOW + timedelta(minutes=5 * i) for i in range(4)]
    suns = [
        SunSnapshot(117.0, 3.6),
        OUTSIDE,
        INSIDE,
        SunSnapshot(120.0, 6.6),
    ]

    def first_calculated(lead_steps):
        for i, when in enumerate(times):
            ahead = suns[min(i + lead_steps, len(suns) - 1)] if lead_steps else None
            ctx_i = TimeContext(
                now_utc=when, sunrise_utc=SUNRISE, sunset_utc=SUNSET, sun_ahead=ahead
            )
            if evaluate(config, suns[i], ctx_i).intent == Intent.CALCULATED:
                return when
        return None

    assert first_calculated(0) == times[2]
    assert first_calculated(1) == times[1]
