"""Privacy rule + glare-wired winter branch + overhang intent labeling."""

from datetime import datetime


from custom_components.adaptive_cover.engine import (
    ClimateInputs,
    CoverConfig,
    GlareModel,
    Intent,
    Overhang,
    PositionLimits,
    PrivacyConfig,
    SunSnapshot,
    TimeContext,
    evaluate,
)

H_WIN = 2.44
OVERHANG = Overhang(depth=1.22, height_above_sill=3.05)
GLARE = GlareModel(eye_height=1.22, occupied_distance=0.91)

# A winter day in naive UTC: sunrise 07:30Z-ish equivalents; times chosen
# so day/dusk/night cases are unambiguous.
SUNRISE = datetime(2026, 12, 21, 14, 50)
SUNSET = datetime(2026, 12, 22, 0, 3)

DAY = TimeContext(datetime(2026, 12, 21, 19, 0), SUNRISE, SUNSET)
DUSK_25M = TimeContext(datetime(2026, 12, 22, 0, 28), SUNRISE, SUNSET)
DUSK_35M = TimeContext(datetime(2026, 12, 22, 0, 38), SUNRISE, SUNSET)

WINTER_SUN = SunSnapshot(azimuth=180.0, elevation=26.0)
NIGHT_SUN = SunSnapshot(azimuth=300.0, elevation=-10.0)

COLD_HOME_CLOUDY = ClimateInputs(
    presence=True, is_summer=False, is_winter=True, is_sunny=False
)
COLD_HOME_SUNNY = ClimateInputs(
    presence=True, is_summer=False, is_winter=True, is_sunny=True
)


def make_config(**kw):
    defaults = dict(
        cover_type="vertical",
        window_azimuth=180,
        fov_left=90,
        fov_right=90,
        default_position=60,
        sunset_position=0,
        distance_shaded_area=0.5,
        window_height=H_WIN,
    )
    defaults.update(kw)
    return CoverConfig(**defaults)


class TestPrivacy:
    def test_inactive_during_day(self):
        cfg = make_config(privacy=PrivacyConfig(enabled=True))
        d = evaluate(cfg, WINTER_SUN, DAY)
        assert d.intent != Intent.PRIVACY

    def test_not_yet_at_25_minutes_after_sunset(self):
        cfg = make_config(privacy=PrivacyConfig(enabled=True, offset_min=30))
        d = evaluate(cfg, NIGHT_SUN, DUSK_25M)
        assert d.intent == Intent.SUNSET  # still the plain sunset behavior

    def test_active_at_35_minutes_after_sunset(self):
        cfg = make_config(privacy=PrivacyConfig(enabled=True, offset_min=30))
        d = evaluate(cfg, NIGHT_SUN, DUSK_35M)
        assert d.intent == Intent.PRIVACY
        assert d.position == 0

    def test_custom_position(self):
        cfg = make_config(
            privacy=PrivacyConfig(enabled=True, offset_min=30, position=10)
        )
        d = evaluate(cfg, NIGHT_SUN, DUSK_35M)
        assert d.position == 10

    def test_overrides_climate_winter_open(self):
        """Privacy beats 'winter: open fully' - the aquarium problem."""
        cfg = make_config(privacy=PrivacyConfig(enabled=True, offset_min=30))
        d = evaluate(cfg, NIGHT_SUN, DUSK_35M, COLD_HOME_SUNNY)
        assert d.intent == Intent.PRIVACY
        assert d.position == 0

    def test_respects_min_position_limit(self):
        """A configured floor (e.g. pet door) still applies to privacy."""
        cfg = make_config(
            privacy=PrivacyConfig(enabled=True, offset_min=30),
            limits=PositionLimits(min_position=9),
        )
        d = evaluate(cfg, NIGHT_SUN, DUSK_35M)
        assert d.position == 9

    def test_disabled_is_inert(self):
        cfg = make_config(privacy=PrivacyConfig(enabled=False))
        d = evaluate(cfg, NIGHT_SUN, DUSK_35M)
        assert d.intent == Intent.SUNSET

    def test_active_before_dawn(self):
        before_dawn = TimeContext(datetime(2026, 12, 21, 14, 0), SUNRISE, SUNSET)
        cfg = make_config(privacy=PrivacyConfig(enabled=True))
        d = evaluate(cfg, NIGHT_SUN, before_dawn)
        assert d.intent == Intent.PRIVACY

    def test_regression_privacy_dawn_honors_sunrise_offset(self):
        """Privacy must release at sunrise + sunrise_offset_min, not bare sunrise.

        2026-07-02..09: south shades (privacy on, sunrise_offset -20) stayed
        pinned at privacy position until exact sunrise, opening 20 min after
        their east/door siblings whose night hold released at sunrise - 20.
        """
        cfg = make_config(
            privacy=PrivacyConfig(enabled=True), sunrise_offset_min=-20
        )
        # sunrise - 15: past the offset dawn, both night holds must be off.
        released = TimeContext(datetime(2026, 12, 21, 14, 35), SUNRISE, SUNSET)
        d = evaluate(cfg, NIGHT_SUN, released)
        assert d.intent not in (Intent.PRIVACY, Intent.SUNSET)
        assert d.position == 60  # default_position

    def test_regression_privacy_dawn_still_held_before_offset(self):
        """Before sunrise + (negative) offset the cover stays on night hold."""
        cfg = make_config(
            privacy=PrivacyConfig(enabled=True), sunrise_offset_min=-20
        )
        held = TimeContext(datetime(2026, 12, 21, 14, 25), SUNRISE, SUNSET)
        d = evaluate(cfg, NIGHT_SUN, held)
        assert d.position == 0


class TestGlareWiredWinter:
    """Glare-limited admission engages exactly where eyes meet beams:
    someone home, direct winter sun, glare model configured."""

    def test_winter_home_sunny_without_glare_blocks(self):
        """Historical quirk preserved: sunny winter day = full blocking."""
        cfg = make_config()
        d = evaluate(cfg, WINTER_SUN, DAY, COLD_HOME_SUNNY)
        assert d.intent == Intent.CALCULATED
        assert d.position < 30  # the 'cave in winter' behavior

    def test_winter_home_sunny_with_glare_admits_to_eye_band(self):
        """The fix the redesign exists for: warmth in, beam out of eyes."""
        cfg = make_config(glare=GLARE, overhang=OVERHANG)
        d = evaluate(cfg, WINTER_SUN, DAY, COLD_HOME_SUNNY)
        assert d.intent == Intent.ADMIT_NO_GLARE
        assert 65 <= d.position <= 72  # ~68%: cover the top third

    def test_winter_home_cloudy_opens_fully_even_with_glare(self):
        """No direct beam, no glare: every lumen matters on a snow day."""
        cfg = make_config(glare=GLARE, overhang=OVERHANG)
        d = evaluate(cfg, WINTER_SUN, DAY, COLD_HOME_CLOUDY)
        assert d.intent == Intent.CLIMATE_OPEN_HEAT
        assert d.position == 100

    def test_winter_away_opens_fully_even_with_glare(self):
        """Nobody home, nobody to glare: maximize gain."""
        away = ClimateInputs(
            presence=False, is_summer=False, is_winter=True, is_sunny=True
        )
        cfg = make_config(glare=GLARE)
        d = evaluate(cfg, WINTER_SUN, DAY, away)
        assert d.intent == Intent.CLIMATE_OPEN_HEAT
        assert d.position == 100

    def test_tilt_covers_unaffected_by_glare_model(self):
        cfg = make_config(
            cover_type="tilt",
            glare=GLARE,
            slat_distance=2,
            slat_depth=3,
            tilt_mode="mode2",
            window_height=None,
            distance_shaded_area=None,
        )
        d = evaluate(cfg, WINTER_SUN, DAY, COLD_HOME_SUNNY)
        assert d.intent != Intent.ADMIT_NO_GLARE  # tilt keeps its formulas


class TestOverhangIntent:
    def test_fully_shaded_labeled(self):
        cfg = make_config(overhang=OVERHANG)
        high_sun = SunSnapshot(azimuth=180.0, elevation=72.0)
        d = evaluate(cfg, high_sun, DAY)
        assert d.intent == Intent.SHADED_BY_OVERHANG
        assert d.position == 60  # default: no movement needed

    def test_without_overhang_same_sun_tracks(self):
        cfg = make_config()
        high_sun = SunSnapshot(azimuth=180.0, elevation=72.0)
        d = evaluate(cfg, high_sun, DAY)
        assert d.intent == Intent.CALCULATED
