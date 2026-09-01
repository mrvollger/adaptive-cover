"""Engine geometry & strategy contracts (wp1-engine-geometry).

Pins the pure-engine math and branch behavior through the frozen seams
only: ``evaluate()`` + the models.py dataclasses, plus the documented
geometry functions ``gamma`` / ``valid_elevation`` / ``tilt_percentage``.

Hand-computed expectations are ported from tests/test_calculation.py so
that legacy-adapter file can retire without losing its math pins:
  - distance=0.5, h_win=2.0, elev=45, gamma=0  -> 25%
  - distance=1.0, h_win=2.1, elev=80, max=50   -> clamped to 50 (M31)
  - h_win=1.0, elev=85                          -> clipped to window: 100%
  - gamma sign convention (left positive, right negative)
"""

from datetime import datetime, timedelta

import pytest

from custom_components.adaptive_cover.engine import (
    BlindSpot,
    ClimateInputs,
    CoverConfig,
    Intent,
    Overhang,
    PositionLimits,
    PrivacyConfig,
    SunSnapshot,
    TimeContext,
    evaluate,
    geometry,
)

# A summer day in naive UTC; times chosen so day/dusk cases are unambiguous.
SUNRISE = datetime(2026, 6, 21, 4, 30)
SUNSET = datetime(2026, 6, 21, 19, 0)
DAY = TimeContext(datetime(2026, 6, 21, 12, 0), SUNRISE, SUNSET)

SUN_FRONT_45 = SunSnapshot(azimuth=180.0, elevation=45.0)
SUN_BEHIND = SunSnapshot(azimuth=0.0, elevation=45.0)

HOME_SUNNY_SUMMER = ClimateInputs(
    presence=True, is_summer=True, is_winter=False, is_sunny=True
)
AWAY_SUNNY_SUMMER = ClimateInputs(
    presence=False, is_summer=True, is_winter=False, is_sunny=True
)
AWAY_SUNNY_WINTER = ClimateInputs(
    presence=False, is_summer=False, is_winter=True, is_sunny=True
)


def make_vertical(**kw):
    """Vertical cover mirroring tests/test_calculation.py defaults."""
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


def make_tilt(**kw):
    """Tilt cover mirroring tests/test_calculation.py defaults."""
    defaults = dict(
        cover_type="tilt",
        window_azimuth=180,
        fov_left=90,
        fov_right=90,
        default_position=60,
        sunset_position=0,
        slat_distance=2,
        slat_depth=3,
        tilt_mode="mode2",
    )
    defaults.update(kw)
    return CoverConfig(**defaults)


def at(hour, minute, day=21):
    return TimeContext(datetime(2026, 6, day, hour, minute), SUNRISE, SUNSET)


# --- gamma & FOV boundaries -------------------------------------------------


class TestGammaSignConvention:
    """Ported from TestGamma: window minus sun, wrapped to (-180, 180]."""

    def test_sun_directly_in_front(self):
        assert geometry.gamma(180, 180) == pytest.approx(0)

    def test_sun_from_left_positive(self):
        assert geometry.gamma(180, 135) == pytest.approx(45)

    def test_sun_from_right_negative(self):
        assert geometry.gamma(180, 225) == pytest.approx(-45)

    def test_sun_behind_window(self):
        assert abs(geometry.gamma(180, 0)) == pytest.approx(180)

    def test_wraparound_through_north(self):
        # NNW window, sun just east of north: 20 deg to the right.
        assert geometry.gamma(350, 10) == pytest.approx(-20)


class TestFovBoundaries:
    """The in-front predicate flips exactly at each boundary."""

    def _intent(self, config, sun, ctx=DAY):
        return evaluate(config, sun, ctx).intent

    def test_just_inside_left_edge_tracks(self):
        cfg = make_vertical(fov_left=40, fov_right=10)
        sun = SunSnapshot(azimuth=141.0, elevation=30.0)  # gamma 39
        assert self._intent(cfg, sun) == Intent.CALCULATED

    def test_exactly_at_left_edge_is_outside(self):
        cfg = make_vertical(fov_left=40, fov_right=10)
        sun = SunSnapshot(azimuth=140.0, elevation=30.0)  # gamma 40
        assert self._intent(cfg, sun) == Intent.DEFAULT

    def test_just_inside_right_edge_tracks(self):
        cfg = make_vertical(fov_left=40, fov_right=10)
        sun = SunSnapshot(azimuth=189.0, elevation=30.0)  # gamma -9
        assert self._intent(cfg, sun) == Intent.CALCULATED

    def test_exactly_at_right_edge_is_outside(self):
        cfg = make_vertical(fov_left=40, fov_right=10)
        sun = SunSnapshot(azimuth=190.0, elevation=30.0)  # gamma -10
        assert self._intent(cfg, sun) == Intent.DEFAULT

    def test_asymmetric_fov_is_not_mirrored(self):
        """gamma sign flip would swap these two (kills the operand swap)."""
        cfg = make_vertical(fov_left=40, fov_right=10)
        left = SunSnapshot(azimuth=160.0, elevation=30.0)  # gamma +20: in
        right = SunSnapshot(azimuth=200.0, elevation=30.0)  # gamma -20: out
        assert self._intent(cfg, left) == Intent.CALCULATED
        assert self._intent(cfg, right) == Intent.DEFAULT

    def test_fov_wider_than_90_is_clipped(self):
        cfg = make_vertical(fov_left=120, fov_right=120)
        beyond = SunSnapshot(azimuth=85.0, elevation=30.0)  # gamma 95
        inside = SunSnapshot(azimuth=95.0, elevation=30.0)  # gamma 85
        assert self._intent(cfg, beyond) == Intent.DEFAULT
        assert self._intent(cfg, inside) == Intent.CALCULATED

    def test_default_fov_edge_ported(self):
        """Ported from test_sun_at_fov_edge: gamma 89 valid, gamma 90 not."""
        cfg = make_vertical()
        edge = SunSnapshot(azimuth=91.0, elevation=45.0)  # gamma 89
        at_90 = SunSnapshot(azimuth=90.0, elevation=45.0)  # gamma 90
        assert self._intent(cfg, edge) == Intent.CALCULATED
        assert self._intent(cfg, at_90) == Intent.DEFAULT

    def test_elevation_exactly_zero_is_in_front(self):
        cfg = make_vertical()
        d = evaluate(cfg, SunSnapshot(azimuth=180.0, elevation=0.0), DAY)
        assert d.intent == Intent.CALCULATED
        assert d.position == 0  # tan(0): no penetration yet

    def test_elevation_below_zero_is_not(self):
        cfg = make_vertical()
        d = evaluate(cfg, SunSnapshot(azimuth=180.0, elevation=-0.1), DAY)
        assert d.intent == Intent.DEFAULT


# --- vertical blind hand-computed positions ---------------------------------


class TestVerticalPositionHandComputed:
    """evaluate() equals (d / cos g) * tan e / h * 100, rounded."""

    @pytest.mark.parametrize(
        ("azimuth", "elevation", "distance", "h_win", "expected"),
        [
            # ported: 0.5 * tan(45) = 0.5 m of 2.0 m -> 25%
            (180.0, 45.0, 0.5, 2.0, 25),
            # gamma=45 widens the path: 0.5/cos(45)*tan(45)=0.707 -> 35%
            (135.0, 45.0, 0.5, 2.0, 35),
            # ported: elev 85, h_win 1.0 -> clipped to window height -> 100%
            (180.0, 85.0, 0.5, 1.0, 100),
            # ported: 1.0 * tan(80) = 5.67 m, clipped to 2.1 -> 100%
            (180.0, 80.0, 1.0, 2.1, 100),
            # low sun: 0.5 * tan(30) = 0.289 of 2.0 -> 14%
            (180.0, 30.0, 0.5, 2.0, 14),
            # 0.5 * tan(60) = 0.866 of 2.0 -> 43%
            (180.0, 60.0, 0.5, 2.0, 43),
            # default geometry: 0.5 * tan(45) of 2.1 -> 24%
            (180.0, 45.0, 0.5, 2.1, 24),
        ],
    )
    def test_position(self, azimuth, elevation, distance, h_win, expected):
        cfg = make_vertical(distance_shaded_area=distance, window_height=h_win)
        d = evaluate(cfg, SunSnapshot(azimuth=azimuth, elevation=elevation), DAY)
        assert d.intent == Intent.CALCULATED
        assert d.position == expected

    def test_higher_elevation_covers_more(self):
        cfg = make_vertical()
        low = evaluate(cfg, SunSnapshot(180.0, 30.0), DAY).position
        high = evaluate(cfg, SunSnapshot(180.0, 60.0), DAY).position
        assert high > low


# --- blind spot -------------------------------------------------------------


class TestBlindSpotExclusion:
    """Region edges are measured from fov_left: [fov_left-left, fov_left-right]."""

    SPOT = BlindSpot(left=0, right=90, elevation=40, enabled=True)

    def test_inside_spot_gives_default(self):
        cfg = make_vertical(blind_spot=self.SPOT)
        d = evaluate(cfg, SunSnapshot(azimuth=180.0, elevation=30.0), DAY)
        assert d.intent == Intent.DEFAULT
        assert d.position == 60

    def test_outside_spot_azimuth_tracks(self):
        cfg = make_vertical(blind_spot=self.SPOT)
        # gamma -15 is outside [0, 90]
        d = evaluate(cfg, SunSnapshot(azimuth=195.0, elevation=30.0), DAY)
        assert d.intent == Intent.CALCULATED

    def test_above_elevation_cap_tracks(self):
        cfg = make_vertical(blind_spot=self.SPOT)
        d = evaluate(cfg, SunSnapshot(azimuth=180.0, elevation=50.0), DAY)
        assert d.intent == Intent.CALCULATED

    def test_disabled_spot_is_inert(self):
        spot = BlindSpot(left=0, right=90, elevation=40, enabled=False)
        cfg = make_vertical(blind_spot=spot)
        d = evaluate(cfg, SunSnapshot(azimuth=180.0, elevation=30.0), DAY)
        assert d.intent == Intent.CALCULATED


# --- elevation band ---------------------------------------------------------


class TestElevationBand:
    def test_min_only_below_band(self):
        cfg = make_vertical(min_elevation=15)
        d = evaluate(cfg, SunSnapshot(180.0, 10.0), DAY)
        assert d.intent == Intent.DEFAULT

    def test_min_only_at_boundary_tracks(self):
        cfg = make_vertical(min_elevation=15)
        d = evaluate(cfg, SunSnapshot(180.0, 15.0), DAY)
        assert d.intent == Intent.CALCULATED

    def test_full_band_inside_tracks(self):
        cfg = make_vertical(min_elevation=15, max_elevation=45)
        d = evaluate(cfg, SunSnapshot(180.0, 30.0), DAY)
        assert d.intent == Intent.CALCULATED

    def test_full_band_at_max_boundary_tracks(self):
        cfg = make_vertical(min_elevation=15, max_elevation=45)
        d = evaluate(cfg, SunSnapshot(180.0, 45.0), DAY)
        assert d.intent == Intent.CALCULATED

    def test_full_band_above_max_default(self):
        cfg = make_vertical(min_elevation=15, max_elevation=45)
        d = evaluate(cfg, SunSnapshot(180.0, 50.0), DAY)
        assert d.intent == Intent.DEFAULT

    def test_full_band_below_min_default(self):
        cfg = make_vertical(min_elevation=15, max_elevation=45)
        d = evaluate(cfg, SunSnapshot(180.0, 10.0), DAY)
        assert d.intent == Intent.DEFAULT

    @pytest.mark.parametrize(
        ("elevation", "min_e", "max_e", "expected"),
        [
            # ported from TestValidElevation
            (45, None, None, True),
            (-5, None, None, False),
            (10, 20, None, False),
            (30, 20, None, True),
            (80, None, 70, False),
            (60, None, 70, True),
            (45, 20, 70, True),
            (10, 20, 70, False),
            # horizon floor survives a max-only band (night must stay invalid)
            (-5, None, 70, False),
        ],
    )
    def test_valid_elevation_table(self, elevation, min_e, max_e, expected):
        assert geometry.valid_elevation(elevation, min_e, max_e) is expected


# --- sunset / sunrise offsets -----------------------------------------------


class TestSunsetSunriseOffsets:
    def test_positive_sunset_offset_delays_engagement(self):
        cfg = make_vertical(sunset_offset_min=30, sunset_position=15)
        below = SunSnapshot(azimuth=280.0, elevation=-3.0)
        # 19:20: past sunset but not past sunset+30 -> plain default
        d = evaluate(cfg, below, at(19, 20))
        assert d.intent == Intent.DEFAULT
        assert d.position == 60
        # 19:31: past sunset+30 -> sunset position
        d = evaluate(cfg, below, at(19, 31))
        assert d.intent == Intent.SUNSET
        assert d.position == 15

    def test_exactly_at_sunset_plus_offset_not_engaged(self):
        cfg = make_vertical(sunset_offset_min=30)
        below = SunSnapshot(azimuth=280.0, elevation=-3.0)
        d = evaluate(cfg, below, at(19, 30))  # strict >
        assert d.intent == Intent.DEFAULT

    def test_negative_sunset_offset_engages_early(self):
        cfg = make_vertical(sunset_offset_min=-30)
        sun_up = SunSnapshot(azimuth=270.0, elevation=5.0)  # gamma -90: not in FOV
        d = evaluate(cfg, sun_up, at(18, 29))
        assert d.intent == Intent.DEFAULT
        d = evaluate(cfg, sun_up, at(18, 31))
        assert d.intent == Intent.SUNSET

    def test_negative_sunset_offset_beats_direct_sun(self):
        """Once sunset+offset passes, tracking stops even with sun in FOV."""
        cfg = make_vertical(sunset_offset_min=-30)
        sun = SunSnapshot(azimuth=180.0, elevation=10.0)
        assert evaluate(cfg, sun, at(18, 29)).intent == Intent.CALCULATED
        assert evaluate(cfg, sun, at(18, 31)).intent == Intent.SUNSET

    def test_sunrise_offset_holds_until_offset_dawn(self):
        cfg = make_vertical(sunrise_offset_min=15)
        low_sun = SunSnapshot(azimuth=180.0, elevation=5.0)
        # 04:44: past sunrise, before sunrise+15 -> still night hold
        assert evaluate(cfg, low_sun, at(4, 44)).intent == Intent.SUNSET
        # 04:45 exactly: released (strict <)
        assert evaluate(cfg, low_sun, at(4, 45)).intent == Intent.CALCULATED

    def test_sunrise_offset_unset_releases_at_bare_sunrise(self):
        """Engine default sunrise_offset_min is 0: release right at sunrise.

        The unset->sunset_offset fallback itself lives in the adapter
        (coordinator resolves CONF_SUNRISE_OFFSET before building the
        engine inputs); the engine contract is the resolved value below.
        """
        assert CoverConfig.__dataclass_fields__["sunrise_offset_min"].default == 0
        cfg = make_vertical(sunset_offset_min=30)
        low_sun = SunSnapshot(azimuth=180.0, elevation=5.0)
        assert evaluate(cfg, low_sun, at(4, 29)).intent == Intent.SUNSET
        assert evaluate(cfg, low_sun, at(4, 31)).intent == Intent.CALCULATED

    def test_sunrise_offset_resolved_to_sunset_offset(self):
        """The adapter's fallback contract: sunrise offset == sunset offset."""
        cfg = make_vertical(sunset_offset_min=-20, sunrise_offset_min=-20)
        low_sun = SunSnapshot(azimuth=180.0, elevation=5.0)
        # sunrise-20 = 04:10; before it: held, after it: tracking
        assert evaluate(cfg, low_sun, at(4, 5)).intent == Intent.SUNSET
        assert evaluate(cfg, low_sun, at(4, 15)).intent == Intent.CALCULATED


# --- min/max limits, sun-conditional ----------------------------------------


class TestMinMaxLimits:
    HIGH_SUN = SunSnapshot(azimuth=180.0, elevation=80.0)  # raw 100 at d=1.0
    LOW_SUN = SunSnapshot(azimuth=180.0, elevation=10.0)  # raw 4 at defaults

    def test_max_clamps_tracking_ported(self):
        """Ported M31 sole-killer: elev 80, d=1.0, h=2.1, max 50 -> 50."""
        cfg = make_vertical(
            distance_shaded_area=1.0,
            limits=PositionLimits(max_position=50),
        )
        d = evaluate(cfg, self.HIGH_SUN, DAY)
        assert d.position == 50

    def test_max_does_not_raise_low_positions(self):
        """A flipped max comparison would push 25 up to 50."""
        cfg = make_vertical(
            distance_shaded_area=0.5,
            window_height=2.0,
            limits=PositionLimits(max_position=50),
        )
        d = evaluate(cfg, SUN_FRONT_45, DAY)
        assert d.position == 25

    def test_max_only_when_sun_skips_default(self):
        cfg = make_vertical(
            distance_shaded_area=1.0,
            limits=PositionLimits(max_position=50, max_only_when_sun=True),
        )
        # sun in front: clamped
        assert evaluate(cfg, self.HIGH_SUN, DAY).position == 50
        # sun behind: default 60 exceeds max but the flag defers to the sun
        assert evaluate(cfg, SUN_BEHIND, DAY).position == 60

    def test_max_unconditional_clamps_default_too(self):
        cfg = make_vertical(limits=PositionLimits(max_position=50))
        assert evaluate(cfg, SUN_BEHIND, DAY).position == 50

    def test_min_clamps_tracking_ported(self):
        """Ported: low sun raises tiny calculated positions to min_pos."""
        cfg = make_vertical(
            default_position=20, limits=PositionLimits(min_position=30)
        )
        d = evaluate(cfg, self.LOW_SUN, DAY)
        assert d.position == 30

    def test_min_only_when_sun_skips_default(self):
        cfg = make_vertical(
            default_position=20,
            limits=PositionLimits(min_position=30, min_only_when_sun=True),
        )
        assert evaluate(cfg, self.LOW_SUN, DAY).position == 30
        assert evaluate(cfg, SUN_BEHIND, DAY).position == 20

    def test_min_unconditional_raises_default_too(self):
        cfg = make_vertical(
            default_position=20, limits=PositionLimits(min_position=30)
        )
        assert evaluate(cfg, SUN_BEHIND, DAY).position == 30

    def test_min_does_not_lower_high_positions(self):
        cfg = make_vertical(
            distance_shaded_area=1.0, limits=PositionLimits(min_position=30)
        )
        assert evaluate(cfg, self.HIGH_SUN, DAY).position == 100


# --- climate tilt presets ---------------------------------------------------


class TestClimateTiltPresets:
    """Preset angles promoted from truth-table rows to engine spec.

    mode2 spans 180 deg: 80 deg -> 44.44%, 45 deg -> 25%, closed -> 0,
    beams-parallel -> (beta+90)/180. mode1 spans 90 deg.
    """

    def test_home_sunny_uses_80_preset(self):
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, HOME_SUNNY_SUMMER)
        assert d.intent == Intent.CLIMATE_TILT_PRESET
        assert d.position == pytest.approx(80 / 180 * 100)

    def test_home_dim_summer_uses_45_preset(self):
        dim = ClimateInputs(presence=True, is_summer=True, is_sunny=False)
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, dim)
        assert d.intent == Intent.CLIMATE_TILT_PRESET
        assert d.position == pytest.approx(45 / 180 * 100)

    def test_home_dim_winter_falls_back_to_basic(self):
        """Basic tilt math: slat 106.87 deg / 180 -> 59% (hand-computed)."""
        dim_winter = ClimateInputs(
            presence=True, is_summer=False, is_winter=True, is_sunny=False
        )
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, dim_winter)
        assert d.intent == Intent.CALCULATED
        assert d.position == 59

    def test_away_summer_closes(self):
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, AWAY_SUNNY_SUMMER)
        assert d.intent == Intent.CLIMATE_BLOCK_HEAT
        assert d.position == 0

    def test_away_winter_mode2_parallel_to_beams(self):
        """beta=45 at gamma=0/elev=45: (45+90)/180 -> 75%."""
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, AWAY_SUNNY_WINTER)
        assert d.intent == Intent.CLIMATE_OPEN_HEAT
        assert d.position == pytest.approx(75.0)

    def test_away_winter_mode1_gets_80_preset(self):
        """The beams-parallel branch is mode2-only; mode1 keeps the preset."""
        d = evaluate(
            make_tilt(tilt_mode="mode1"), SUN_FRONT_45, DAY, AWAY_SUNNY_WINTER
        )
        assert d.intent == Intent.CLIMATE_TILT_PRESET
        assert d.position == pytest.approx(80 / 90 * 100)

    def test_away_intermediate_gets_80_preset(self):
        away_mild = ClimateInputs(presence=False, is_summer=False, is_winter=False)
        d = evaluate(make_tilt(), SUN_FRONT_45, DAY, away_mild)
        assert d.intent == Intent.CLIMATE_TILT_PRESET
        assert d.position == pytest.approx(80 / 180 * 100)

    def test_away_sun_not_in_window_basic_default(self):
        d = evaluate(make_tilt(), SUN_BEHIND, DAY, AWAY_SUNNY_WINTER)
        assert d.intent == Intent.DEFAULT
        assert d.position == 60

    def test_mode1_percentage_unscaled_can_exceed_100(self):
        """tilt_percentage divisor pin: same slat angle, 90 vs 180 span."""
        cfg1 = make_tilt(tilt_mode="mode1")
        cfg2 = make_tilt(tilt_mode="mode2")
        assert geometry.tilt_percentage(cfg1, SUN_FRONT_45) == 119
        assert geometry.tilt_percentage(cfg2, SUN_FRONT_45) == 59


# --- overhang shadow line ---------------------------------------------------


class TestOverhangShadowLine:
    """sunlit_top = height_above_sill - depth * tan(profile), clipped."""

    OVERHANG = Overhang(depth=1.22, height_above_sill=3.05)

    def _cfg(self):
        return make_vertical(window_height=2.44, overhang=self.OVERHANG)

    def test_shadow_line_hand_computed(self):
        # elev 45, gamma 0: 3.05 - 1.22 * tan(45) = 1.83 m
        top = geometry.sunlit_top(self._cfg(), SunSnapshot(180.0, 45.0))
        assert top == pytest.approx(1.83)

    def test_shadow_above_blind_edge_tracks_normally(self):
        # blind edge 0.5 m < shadow line 1.83 m: plain geometry, 20%
        d = evaluate(self._cfg(), SunSnapshot(180.0, 45.0), DAY)
        assert d.intent == Intent.CALCULATED
        assert d.position == 20

    def test_shadow_below_blind_edge_opens_fully(self):
        # elev 65: shadow 0.43 m < required edge 1.07 m -> open fully
        d = evaluate(self._cfg(), SunSnapshot(180.0, 65.0), DAY)
        assert d.intent == Intent.CALCULATED
        assert d.position == 100

    def test_fully_shaded_window_gets_default(self):
        # elev 70: shadow line clips to 0 -> whole window shaded
        d = evaluate(self._cfg(), SunSnapshot(180.0, 70.0), DAY)
        assert d.intent == Intent.SHADED_BY_OVERHANG
        assert d.position == 60


# --- transparent blind ------------------------------------------------------


class TestTransparentBlind:
    def test_summer_home_sunny_closes(self):
        transparent = ClimateInputs(
            presence=True, is_summer=True, is_sunny=True, transparent_blind=True
        )
        d = evaluate(make_vertical(), SUN_FRONT_45, DAY, transparent)
        assert d.intent == Intent.CLIMATE_BLOCK_HEAT
        assert d.position == 0

    def test_opaque_blind_same_day_tracks(self):
        d = evaluate(make_vertical(), SUN_FRONT_45, DAY, HOME_SUNNY_SUMMER)
        assert d.intent == Intent.CALCULATED
        assert d.position == 24


# --- privacy offset zero ----------------------------------------------------


class TestPrivacyOffsetZero:
    """privacy_offset=0 must mean sunset, not the 30-minute default."""

    NIGHT_SUN = SunSnapshot(azimuth=300.0, elevation=-5.0)

    def test_active_five_minutes_after_sunset(self):
        cfg = make_vertical(privacy=PrivacyConfig(enabled=True, offset_min=0))
        d = evaluate(cfg, self.NIGHT_SUN, at(19, 5))
        assert d.intent == Intent.PRIVACY
        assert d.position == 0

    def test_not_active_before_sunset(self):
        cfg = make_vertical(privacy=PrivacyConfig(enabled=True, offset_min=0))
        d = evaluate(cfg, SUN_FRONT_45, at(18, 55))
        assert d.intent != Intent.PRIVACY

    def test_engages_strictly_after_sunset(self):
        cfg = make_vertical(privacy=PrivacyConfig(enabled=True, offset_min=0))
        exactly = TimeContext(SUNSET, SUNRISE, SUNSET)
        just_after = TimeContext(SUNSET + timedelta(minutes=1), SUNRISE, SUNSET)
        assert evaluate(cfg, self.NIGHT_SUN, exactly).intent != Intent.PRIVACY
        assert evaluate(cfg, self.NIGHT_SUN, just_after).intent == Intent.PRIVACY


# --- climate outputs are unclipped (documented quirk) ------------------------


class TestClimateOutputUnclipped:
    """Climate-branch outputs skip the 0-100 clip; limits still apply."""

    def test_away_default_above_100_preserved(self):
        cfg = make_vertical(default_position=110)
        away_mild = ClimateInputs(presence=False, is_summer=False, is_winter=False)
        d = evaluate(cfg, SUN_BEHIND, DAY, away_mild)
        assert d.intent == Intent.CLIMATE_DEFAULT
        assert d.position == 110  # bit-for-bit, not clipped

    def test_basic_path_clips_same_config_to_100(self):
        cfg = make_vertical(default_position=110)
        d = evaluate(cfg, SUN_BEHIND, DAY)
        assert d.position == 100

    def test_min_limit_pushes_climate_close_up(self):
        cfg = make_vertical(limits=PositionLimits(min_position=25))
        d = evaluate(cfg, SUN_FRONT_45, DAY, AWAY_SUNNY_SUMMER)
        assert d.intent == Intent.CLIMATE_BLOCK_HEAT
        assert d.position == 25

    def test_max_limit_pulls_climate_open_down(self):
        cfg = make_vertical(limits=PositionLimits(max_position=80))
        d = evaluate(cfg, SUN_FRONT_45, DAY, AWAY_SUNNY_WINTER)
        assert d.intent == Intent.CLIMATE_OPEN_HEAT
        assert d.position == 80
