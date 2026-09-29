"""Pure-engine regression tests for verified live-house bugs.

Each test names the fix it pins; see the matching commit for the incident
details. All inputs are explicit — no HA, no wall clock.
"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from custom_components.adaptive_cover.engine import (
    ClimateInputs,
    CoverConfig,
    Intent,
    SunSnapshot,
    TimeContext,
    evaluate,
    geometry,
)


def vertical_config(**kw):
    defaults = dict(
        cover_type="vertical",
        window_azimuth=180,
        fov_left=90,
        fov_right=90,
        default_position=60,
        sunset_position=0,
        distance_shaded_area=0.5,
        window_height=2.1,
    )
    defaults.update(kw)
    return CoverConfig(**defaults)


class TestRegressionMaxElevationNightFov:
    """valid_elevation dropped the horizon floor when only max_elevation was
    set, so 'sun in FOV' held true all night and winter climate branches kept
    covers open in the dark."""

    def test_regression_max_elevation_only_keeps_horizon_floor(self):
        # Night: sun below the horizon must never be 'valid', band or not.
        assert geometry.valid_elevation(-10, None, 50) is False
        assert geometry.valid_elevation(-0.001, None, 50) is False
        # Daytime inside the band still valid; above the cap invalid.
        assert geometry.valid_elevation(30, None, 50) is True
        assert geometry.valid_elevation(60, None, 50) is False

    def test_regression_max_elevation_only_unchanged_cases(self):
        # No band: horizon floor as before.
        assert geometry.valid_elevation(-1, None, None) is False
        assert geometry.valid_elevation(1, None, None) is True
        # Explicit min below the horizon is still honored (deliberate config).
        assert geometry.valid_elevation(-3, -5, None) is True
        assert geometry.valid_elevation(-6, -5, None) is False
        # Both bounds: unchanged.
        assert geometry.valid_elevation(10, 5, 50) is True
        assert geometry.valid_elevation(4, 5, 50) is False
        assert geometry.valid_elevation(51, 5, 50) is False

    def test_regression_sun_not_in_fov_at_night_with_max_only(self):
        config = vertical_config(max_elevation=40)
        night_sun = SunSnapshot(azimuth=180, elevation=-20)
        assert geometry.sun_in_fov(config, night_sun) is False

    def test_regression_winter_climate_closes_at_night_with_max_only(self):
        """End-to-end symptom: winter + presence + max-only band at night
        must land on the sunset position, not CLIMATE_OPEN_HEAT 100."""
        config = vertical_config(max_elevation=40, sunset_position=0)
        night_sun = SunSnapshot(azimuth=180, elevation=-20)
        ctx = TimeContext(
            now_utc=datetime(2026, 1, 15, 3, 0),
            sunrise_utc=datetime(2026, 1, 15, 14, 45),
            sunset_utc=datetime(2026, 1, 15, 0, 5),
        )
        climate = ClimateInputs(presence=True, is_winter=True, is_sunny=True)
        decision = evaluate(config, night_sun, ctx, climate)
        assert decision.intent != Intent.CLIMATE_OPEN_HEAT
        assert decision.position == config.sunset_position


class TestRegressionTiltSqrtNegative:
    """slat_distance > slat_depth (UI allows it) made the tilt discriminant
    negative -> sqrt -> NaN -> round(NaN) ValueError killed the update loop."""

    def make_config(self, slat_distance=0.15, slat_depth=0.10, mode="mode2"):
        return CoverConfig(
            cover_type="tilt",
            window_azimuth=180,
            fov_left=90,
            fov_right=90,
            default_position=60,
            sunset_position=0,
            slat_distance=slat_distance,
            slat_depth=slat_depth,
            tilt_mode=mode,
        )

    def test_regression_tilt_discriminant_clamped_no_nan(self):
        config = self.make_config()
        low_sun = SunSnapshot(azimuth=180, elevation=5)
        angle = geometry.tilt_slat_angle(config, low_sun)
        assert np.isfinite(angle)
        # round() must not raise (this was the crash).
        pct = geometry.tilt_percentage(config, low_sun)
        assert 0 <= pct <= 100

    @pytest.mark.parametrize("elevation", [0.5, 2, 5, 10, 20, 45, 80])
    @pytest.mark.parametrize("ratio", [(0.2, 0.1), (0.15, 0.1), (2.0, 1.0)])
    def test_regression_tilt_finite_for_all_ratios(self, elevation, ratio):
        slat_distance, slat_depth = ratio
        config = self.make_config(slat_distance, slat_depth)
        sun = SunSnapshot(azimuth=180, elevation=elevation)
        assert np.isfinite(geometry.tilt_slat_angle(config, sun))

    def test_regression_tilt_unaffected_when_depth_covers_distance(self):
        """ratio <= 1 keeps the historical formula bit-for-bit."""
        config = self.make_config(slat_distance=2, slat_depth=3)
        sun = SunSnapshot(azimuth=180, elevation=45)
        beta = geometry.tilt_beta(config, sun)
        ratio = 2 / 3
        expected = np.rad2deg(
            2
            * np.arctan(
                (np.tan(beta) + np.sqrt((np.tan(beta) ** 2) - (ratio**2) + 1))
                / (1 + ratio)
            )
        )
        assert geometry.tilt_slat_angle(config, sun) == pytest.approx(expected)


class TestRegressionAwningOverflow:
    """awning_angle=0 with elevation exactly 0.0 divided by sin(0) -> inf;
    round(inf) raised OverflowError in the update loop."""

    def make_config(self, awning_angle=0.0, awning_length=2.1):
        return CoverConfig(
            cover_type="awning",
            window_azimuth=180,
            fov_left=90,
            fov_right=90,
            default_position=60,
            sunset_position=0,
            distance_shaded_area=0.5,
            window_height=2.1,
            awning_length=awning_length,
            awning_angle=awning_angle,
        )

    def test_regression_awning_zero_elevation_returns_full_length(self):
        config = self.make_config(awning_angle=0.0)
        horizon_sun = SunSnapshot(azimuth=180, elevation=0.0)
        extension = geometry.awning_extension(config, horizon_sun)
        assert extension == config.awning_length
        # round() must not raise (this was the crash).
        assert geometry.awning_percentage(config, horizon_sun) == 100

    @pytest.mark.parametrize("elevation", [0.0, 0.001, 0.5, 5, 30, 60, 89])
    def test_regression_awning_extension_clipped(self, elevation):
        config = self.make_config(awning_angle=0.0)
        sun = SunSnapshot(azimuth=180, elevation=elevation)
        extension = geometry.awning_extension(config, sun)
        assert np.isfinite(extension)
        assert 0 <= extension <= config.awning_length

    def test_regression_awning_typical_geometry_unchanged(self):
        """Mid-range geometry keeps the historical sine-rule value."""
        config = self.make_config(awning_angle=0.0)
        sun = SunSnapshot(azimuth=180, elevation=45)
        vertical = geometry.vertical_blind_height(config, sun)
        a_angle = 90 - 45
        c_angle = 45.0
        expected = (
            (config.window_height - vertical) * np.sin(np.radians(a_angle))
        ) / np.sin(np.radians(c_angle))
        assert geometry.awning_extension(config, sun) == pytest.approx(
            float(np.clip(expected, 0, config.awning_length))
        )


class TestRegressionDuskOpenThenClose:
    """The sun left the window shortly before the sunset position began, so
    the cover opened to the default and closed again minutes later
    (Leanne's door, summer: 97% at 20:15, 5% at 20:35; Master trap with a
    +15 min offset: 99% at sunset, 0% at sunset+15). When the sun leaves
    less than DUSK_LEAD before the sunset position begins, the sunset
    position starts right away. A sun that left earlier keeps the
    configured sunset time."""

    # Naive UTC, a June evening in Denver: sunset 03:02Z (21:02 MDT).
    SUNRISE = datetime(2026, 6, 21, 11, 57)
    SUNSET = datetime(2026, 6, 22, 3, 2)
    OUT_OF_WINDOW = SunSnapshot(azimuth=296.0, elevation=6.0)  # left the FOV
    IN_WINDOW = SunSnapshot(azimuth=280.0, elevation=8.0)

    def config(self, **kw):
        base = dict(
            window_azimuth=235,
            fov_left=60,
            fov_right=60,
            default_position=97,
            sunset_position=5,
            sunset_offset_min=-30,  # sunset position from 02:32Z
            max_elevation=50,
        )
        base.update(kw)
        return vertical_config(**base)

    def ctx(self, minutes_before, config, sun_at_lead):
        start = self.SUNSET + timedelta(minutes=config.sunset_offset_min)
        return TimeContext(
            now_utc=start - timedelta(minutes=minutes_before),
            sunrise_utc=self.SUNRISE,
            sunset_utc=self.SUNSET,
            sun_at_dusk_lead=sun_at_lead,
        )

    def test_regression_dusk_lead_is_thirty_minutes(self):
        assert geometry.DUSK_LEAD.total_seconds() == 30 * 60

    @pytest.mark.parametrize(
        ("minutes", "position", "intent"),
        [(29, 5, Intent.SUNSET), (31, 97, Intent.DEFAULT)],
        ids=["29_min_before", "31_min_before"],
    )
    def test_regression_dusk_lead_boundary(self, minutes, position, intent):
        """Sun in the window when the lead began, gone now."""
        config = self.config()
        ctx = self.ctx(minutes, config, sun_at_lead=self.IN_WINDOW)
        decision = evaluate(config, self.OUT_OF_WINDOW, ctx)
        assert (decision.position, decision.intent) == (position, intent)

    @pytest.mark.parametrize(
        ("minutes", "position"), [(29, 5), (31, 97)], ids=["29_min", "31_min"]
    )
    def test_regression_dusk_lead_boundary_climate_default(self, minutes, position):
        """Climate branches that rest at the default follow the same lead."""
        config = self.config()
        away = ClimateInputs(presence=False, is_summer=False, is_winter=False)
        ctx = self.ctx(minutes, config, sun_at_lead=self.IN_WINDOW)
        decision = evaluate(config, self.OUT_OF_WINDOW, ctx, away)
        assert decision.position == position

    def test_regression_dusk_lead_master_trap_positive_offset(self):
        """Master trap: the sun sets in the window; sunset position at +15."""
        config = self.config(
            window_azimuth=240,
            fov_left=90,
            fov_right=90,
            default_position=99,
            sunset_position=0,
            sunset_offset_min=15,
            max_elevation=None,
        )
        at_sunset = self.ctx(15, config, sun_at_lead=SunSnapshot(296.0, 2.5))
        set_sun = SunSnapshot(azimuth=300.0, elevation=-0.8)
        decision = evaluate(config, set_sun, at_sunset)
        assert (decision.position, decision.intent) == (0, Intent.SUNSET)

    def test_regression_dusk_lead_keeps_sunset_time_when_sun_left_early(self):
        """An east window the sun left at noon keeps its configured close."""
        config = self.config(window_azimuth=100, fov_left=90, fov_right=44)
        gone_since_noon = SunSnapshot(azimuth=290.0, elevation=9.0)
        ctx = self.ctx(10, config, sun_at_lead=gone_since_noon)
        decision = evaluate(config, SunSnapshot(azimuth=296.0, elevation=6.0), ctx)
        assert (decision.position, decision.intent) == (97, Intent.DEFAULT)

    def test_regression_dusk_lead_unknown_sun_never_engages(self):
        config = self.config()
        ctx = self.ctx(10, config, sun_at_lead=None)
        decision = evaluate(config, self.OUT_OF_WINDOW, ctx)
        assert (decision.position, decision.intent) == (97, Intent.DEFAULT)

    def test_regression_dusk_lead_keeps_tracking_sun_in_window(self):
        """Daytime rule unchanged: sun still in the window keeps tracking."""
        config = self.config()
        ctx = self.ctx(10, config, sun_at_lead=self.IN_WINDOW)
        decision = evaluate(config, self.IN_WINDOW, ctx)
        assert decision.intent == Intent.CALCULATED

    def test_regression_dusk_lead_leaves_morning_alone(self):
        """Out of the window 10 min after the morning start: still default."""
        config = self.config()
        morning = TimeContext(
            now_utc=self.SUNRISE + timedelta(minutes=10),
            sunrise_utc=self.SUNRISE,
            sunset_utc=self.SUNSET,
            sun_at_dusk_lead=self.IN_WINDOW,
        )
        decision = evaluate(config, SunSnapshot(azimuth=60.0, elevation=2.0), morning)
        assert (decision.position, decision.intent) == (97, Intent.DEFAULT)
