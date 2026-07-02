"""Overhang + glare-band geometry: table tests, the paired asymmetry
scenario, and dense parametrized property sweeps.

Reference house (the geometry that motivated the feature): 2.44 m
floor-to-ceiling south glass, balcony overhang 1.22 m deep with its
underside 3.05 m above the sill (8 ft window, 4 ft overhang, 10 ft up).
"""

import math

import numpy as np
import pytest

from custom_components.adaptive_cover.engine import (
    CoverConfig,
    GlareModel,
    Overhang,
    SunSnapshot,
)
from custom_components.adaptive_cover.engine import geometry

H_WIN = 2.44
OVERHANG = Overhang(depth=1.22, height_above_sill=3.05)
GLARE = GlareModel(eye_height=1.22, occupied_distance=0.91)


def make_config(overhang=None, glare=None, distance=0.5, h_win=H_WIN, **kw):
    return CoverConfig(
        cover_type="vertical",
        window_azimuth=kw.get("window_azimuth", 180),
        fov_left=90,
        fov_right=90,
        default_position=60,
        sunset_position=0,
        distance_shaded_area=distance,
        window_height=h_win,
        overhang=overhang,
        glare=glare,
    )


def south_sun(elevation, azimuth=180.0):
    return SunSnapshot(azimuth=azimuth, elevation=elevation)


class TestOverhangShadowLine:
    """Shadow line math against hand-computed values for the real house."""

    def test_no_overhang_whole_window_sunlit(self):
        cfg = make_config()
        assert geometry.sunlit_top(cfg, south_sun(45)) == H_WIN

    def test_low_winter_sun_whole_window_sunlit(self):
        """At 26 deg (SLC winter noon) the shadow line is above the glass."""
        cfg = make_config(overhang=OVERHANG)
        # 3.05 - 1.22*tan(26) = 2.45 > 2.44
        assert geometry.sunlit_top(cfg, south_sun(26)) == pytest.approx(H_WIN)

    def test_equinox_sun_shades_top_third(self):
        """At 49 deg (equinox noon) the top of the glass is shaded."""
        cfg = make_config(overhang=OVERHANG)
        expected = 3.05 - 1.22 * math.tan(math.radians(49))
        assert geometry.sunlit_top(cfg, south_sun(49)) == pytest.approx(
            expected, abs=1e-6
        )
        assert 1.5 < expected < 1.7  # ~1.65 m: bottom two-thirds sunlit

    def test_high_summer_sun_fully_shades_window(self):
        """Above ~68.2 deg (arctan(3.05/1.22)) the glass sees no direct sun."""
        cfg = make_config(overhang=OVERHANG)
        assert geometry.window_fully_shaded(cfg, south_sun(69)) is True
        assert geometry.window_fully_shaded(cfg, south_sun(67)) is False

    def test_fully_shaded_kills_direct_sun_valid(self):
        from custom_components.adaptive_cover.engine import TimeContext
        from datetime import datetime

        ctx = TimeContext(
            now_utc=datetime(2026, 6, 21, 19, 0),
            sunrise_utc=datetime(2026, 6, 21, 12, 0),
            sunset_utc=datetime(2026, 6, 22, 3, 0),
        )
        cfg = make_config(overhang=OVERHANG)
        assert geometry.direct_sun_valid(cfg, south_sun(72), ctx) is False
        assert geometry.direct_sun_valid(make_config(), south_sun(72), ctx) is True

    def test_oblique_sun_uses_profile_angle_not_elevation(self):
        """At gamma=60 the profile angle exceeds the raw elevation, so the
        shadow drops deeper than an elevation-only model would predict."""
        cfg = make_config(overhang=OVERHANG)
        straight = geometry.sunlit_top(cfg, south_sun(45, azimuth=180))
        oblique = geometry.sunlit_top(cfg, south_sun(45, azimuth=240))
        assert oblique < straight

    def test_vertical_percentage_opens_fully_when_shadow_below_required_edge(self):
        """Overhang shadow at/below the penetration edge -> blind fully open."""
        cfg = make_config(overhang=OVERHANG, distance=0.5)
        sun = south_sun(60)  # shadow line 3.05-1.22*1.732=0.94; edge 0.5*1.732=0.87
        no_overhang = make_config(distance=0.5)
        assert geometry.sunlit_top(cfg, sun) > geometry.vertical_blind_height(
            no_overhang, sun
        )
        # push higher: at 64 deg shadow 0.55 < edge 1.03 -> fully open
        sun_high = south_sun(64)
        assert geometry.vertical_percentage(cfg, sun_high) == 100
        assert geometry.vertical_percentage(no_overhang, sun_high) < 100


class TestGlareBand:
    """Glare-safe height and the admit-no-glare position."""

    def test_winter_noon_position_matches_hand_calc(self):
        """SLC winter noon (26 deg): cover to eye band, warm the floor."""
        cfg = make_config(overhang=OVERHANG, glare=GLARE)
        h_glare = 1.22 + 0.91 * math.tan(math.radians(26))
        expected = round(h_glare / H_WIN * 100)
        assert geometry.admit_no_glare_percentage(cfg, south_sun(26)) == expected
        assert 65 <= expected <= 72  # ~68% open = cover top ~1/3

    def test_glare_low_sun_covers_to_eye_height(self):
        """As elevation -> 0 the safe height approaches eye height."""
        cfg = make_config(glare=GLARE)
        pos = geometry.admit_no_glare_percentage(cfg, south_sun(1))
        assert pos == round(1.24 / H_WIN * 100) or pos == round(1.22 / H_WIN * 100)

    def test_shadow_below_glare_height_means_fully_open(self):
        """If the overhang already shades everything above the eye band,
        no cover movement is needed at all."""
        cfg = make_config(overhang=OVERHANG, glare=GLARE)
        # 56 deg: sunlit_top = 3.05-1.22*tan(56) = 1.24 m;
        # glare-safe = 1.22+0.91*tan(56) = 2.57 m > sunlit_top
        assert geometry.admit_no_glare_percentage(cfg, south_sun(56)) == 100


class TestSunlitBandAsymmetry:
    """The user's rule: same geometry, opposite decisions by objective.

    Sun at 56 deg touches only the bottom half of the glass (shadow line
    1.24 m of 2.44 m). Winter/admit: fully open - no glare possible.
    Summer/block: the penetration model still demands coverage.
    """

    SUN = SunSnapshot(azimuth=180.0, elevation=56.0)
    CFG = None

    @classmethod
    def setup_class(cls):
        cls.CFG = make_config(overhang=OVERHANG, glare=GLARE, distance=0.5)

    def test_bottom_half_sunlit(self):
        top = geometry.sunlit_top(self.CFG, self.SUN)
        assert 0.4 * H_WIN < top < 0.6 * H_WIN

    def test_admit_intent_fully_open(self):
        assert geometry.admit_no_glare_percentage(self.CFG, self.SUN) == 100

    def test_block_intent_stays_closed_down(self):
        block = geometry.vertical_percentage(self.CFG, self.SUN)
        # required edge 0.5*tan(56)=0.74 m < sunlit_top 1.24 m -> must cover
        assert block == round(0.5 * math.tan(math.radians(56)) / H_WIN * 100)
        assert block < 40

    def test_opposite_decisions(self):
        admit = geometry.admit_no_glare_percentage(self.CFG, self.SUN)
        block = geometry.vertical_percentage(self.CFG, self.SUN)
        assert admit == 100 and block < 40


ELEVATIONS = list(range(1, 86, 4))
GAMMAS = list(range(-80, 81, 10))


class TestProperties:
    """Dense parametrized sweeps standing in for hypothesis."""

    @pytest.mark.parametrize("elev", ELEVATIONS)
    @pytest.mark.parametrize("g", GAMMAS)
    def test_positions_in_range(self, elev, g):
        sun = SunSnapshot(azimuth=180 - g, elevation=elev)
        cfg = make_config(overhang=OVERHANG, glare=GLARE)
        assert 0 <= geometry.admit_no_glare_percentage(cfg, sun) <= 100
        assert 0 <= geometry.vertical_percentage(cfg, sun) <= 100
        assert 0 <= geometry.sunlit_top(cfg, sun) <= H_WIN

    @pytest.mark.parametrize("elev", ELEVATIONS)
    @pytest.mark.parametrize("g", GAMMAS)
    def test_overhang_never_closes_more(self, elev, g):
        """Adding an overhang can only leave the blind as-open or more open."""
        sun = SunSnapshot(azimuth=180 - g, elevation=elev)
        with_oh = geometry.vertical_percentage(
            make_config(overhang=OVERHANG), sun
        )
        without = geometry.vertical_percentage(make_config(), sun)
        assert with_oh >= without

    @pytest.mark.parametrize("elev", ELEVATIONS)
    @pytest.mark.parametrize("g", GAMMAS)
    def test_glare_never_closes_more_than_block(self, elev, g):
        """When people sit at/beyond the allowed penetration distance, the
        glare objective is always at least as open as full blocking."""
        sun = SunSnapshot(azimuth=180 - g, elevation=elev)
        cfg = make_config(glare=GLARE, distance=0.5)  # occupied 0.91 >= 0.5
        assert geometry.admit_no_glare_percentage(
            cfg, sun
        ) >= geometry.vertical_percentage(cfg, sun)

    @pytest.mark.parametrize("g", GAMMAS)
    def test_sunlit_top_monotone_decreasing_in_elevation(self, g):
        cfg = make_config(overhang=OVERHANG)
        tops = [
            geometry.sunlit_top(cfg, SunSnapshot(azimuth=180 - g, elevation=e))
            for e in ELEVATIONS
        ]
        assert all(a >= b - 1e-9 for a, b in zip(tops, tops[1:]))

    @pytest.mark.parametrize("elev", ELEVATIONS)
    def test_profile_angle_matches_elevation_at_gamma_zero(self, elev):
        cfg = make_config()
        beta = geometry.profile_angle(cfg, south_sun(elev))
        assert np.rad2deg(beta) == pytest.approx(elev, abs=1e-9)
