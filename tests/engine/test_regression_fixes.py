"""Pure-engine regression tests for verified live-house bugs.

Each test names the fix it pins; see the matching commit for the incident
details. All inputs are explicit — no HA, no wall clock.
"""

from datetime import datetime

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
