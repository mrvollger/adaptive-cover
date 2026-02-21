"""Tests for cover calculation classes."""

import logging
from unittest.mock import MagicMock

import numpy as np
import pytest

from custom_components.adaptive_cover.calculation import (
    AdaptiveHorizontalCover,
    AdaptiveTiltCover,
    AdaptiveVerticalCover,
    NormalCoverState,
    get_state_reason,
)
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)


def _make_logger():
    """Create a test logger adapter."""
    logger = ConfigContextAdapter(logging.getLogger("test"))
    logger.set_config_name("Test")
    return logger


def _make_vertical(
    sol_azi=180,
    sol_elev=45,
    win_azi=180,
    fov_left=90,
    fov_right=90,
    h_def=60,
    distance=0.5,
    h_win=2.1,
    sunset_pos=0,
    sunset_off=0,
    sunrise_off=0,
    max_pos=None,
    min_pos=None,
    max_pos_bool=False,
    min_pos_bool=False,
    blind_spot_left=None,
    blind_spot_right=None,
    blind_spot_elevation=None,
    blind_spot_on=False,
    min_elevation=None,
    max_elevation=None,
):
    """Create a vertical cover instance for testing."""
    return AdaptiveVerticalCover(
        hass=MagicMock(),
        logger=_make_logger(),
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sunset_pos=sunset_pos,
        sunset_off=sunset_off,
        sunrise_off=sunrise_off,
        timezone="UTC",
        fov_left=fov_left,
        fov_right=fov_right,
        win_azi=win_azi,
        h_def=h_def,
        max_pos=max_pos,
        min_pos=min_pos,
        max_pos_bool=max_pos_bool,
        min_pos_bool=min_pos_bool,
        blind_spot_left=blind_spot_left,
        blind_spot_right=blind_spot_right,
        blind_spot_elevation=blind_spot_elevation,
        blind_spot_on=blind_spot_on,
        min_elevation=min_elevation,
        max_elevation=max_elevation,
        distance=distance,
        h_win=h_win,
    )


def _make_horizontal(
    sol_azi=180,
    sol_elev=45,
    win_azi=180,
    distance=0.5,
    h_win=2.1,
    awn_length=2.1,
    awn_angle=0,
    **kwargs,
):
    """Create a horizontal cover instance for testing."""
    return AdaptiveHorizontalCover(
        hass=MagicMock(),
        logger=_make_logger(),
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sunset_pos=kwargs.get("sunset_pos", 0),
        sunset_off=kwargs.get("sunset_off", 0),
        sunrise_off=kwargs.get("sunrise_off", 0),
        timezone="UTC",
        fov_left=kwargs.get("fov_left", 90),
        fov_right=kwargs.get("fov_right", 90),
        win_azi=win_azi,
        h_def=kwargs.get("h_def", 60),
        max_pos=kwargs.get("max_pos", None),
        min_pos=kwargs.get("min_pos", None),
        max_pos_bool=kwargs.get("max_pos_bool", False),
        min_pos_bool=kwargs.get("min_pos_bool", False),
        blind_spot_left=kwargs.get("blind_spot_left", None),
        blind_spot_right=kwargs.get("blind_spot_right", None),
        blind_spot_elevation=kwargs.get("blind_spot_elevation", None),
        blind_spot_on=kwargs.get("blind_spot_on", False),
        min_elevation=kwargs.get("min_elevation", None),
        max_elevation=kwargs.get("max_elevation", None),
        distance=distance,
        h_win=h_win,
        awn_length=awn_length,
        awn_angle=awn_angle,
    )


def _make_tilt(
    sol_azi=180,
    sol_elev=45,
    win_azi=180,
    slat_distance=2,
    depth=3,
    mode="mode2",
    **kwargs,
):
    """Create a tilt cover instance for testing."""
    return AdaptiveTiltCover(
        hass=MagicMock(),
        logger=_make_logger(),
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sunset_pos=kwargs.get("sunset_pos", 0),
        sunset_off=kwargs.get("sunset_off", 0),
        sunrise_off=kwargs.get("sunrise_off", 0),
        timezone="UTC",
        fov_left=kwargs.get("fov_left", 90),
        fov_right=kwargs.get("fov_right", 90),
        win_azi=win_azi,
        h_def=kwargs.get("h_def", 60),
        max_pos=kwargs.get("max_pos", None),
        min_pos=kwargs.get("min_pos", None),
        max_pos_bool=kwargs.get("max_pos_bool", False),
        min_pos_bool=kwargs.get("min_pos_bool", False),
        blind_spot_left=kwargs.get("blind_spot_left", None),
        blind_spot_right=kwargs.get("blind_spot_right", None),
        blind_spot_elevation=kwargs.get("blind_spot_elevation", None),
        blind_spot_on=kwargs.get("blind_spot_on", False),
        min_elevation=kwargs.get("min_elevation", None),
        max_elevation=kwargs.get("max_elevation", None),
        slat_distance=slat_distance,
        depth=depth,
        mode=mode,
    )


# --- Gamma (surface solar azimuth) ---


class TestGamma:
    """Tests for gamma property (surface solar azimuth angle)."""

    def test_sun_directly_in_front(self):
        """Gamma should be 0 when sun is directly in front of window."""
        cover = _make_vertical(sol_azi=180, win_azi=180)
        assert cover.gamma == pytest.approx(0)

    def test_sun_from_left(self):
        """Gamma should be positive when sun is to the left."""
        cover = _make_vertical(sol_azi=135, win_azi=180)
        assert cover.gamma == pytest.approx(45)

    def test_sun_from_right(self):
        """Gamma should be negative when sun is to the right."""
        cover = _make_vertical(sol_azi=225, win_azi=180)
        assert cover.gamma == pytest.approx(-45)

    def test_sun_behind_window(self):
        """Gamma should be ~180 when sun is behind window."""
        cover = _make_vertical(sol_azi=0, win_azi=180)
        assert abs(cover.gamma) == pytest.approx(180)


# --- Valid (sun in FOV) ---


class TestValid:
    """Tests for valid property (sun within field of view)."""

    def test_sun_in_fov(self):
        """Sun directly in front with positive elevation is valid."""
        cover = _make_vertical(sol_azi=180, sol_elev=45, win_azi=180)
        assert cover.valid is True

    def test_sun_outside_fov_left(self):
        """Sun too far left is not valid."""
        # FOV left = 90, so sun at azimuth 80 is outside (gamma = 100)
        cover = _make_vertical(sol_azi=80, sol_elev=45, win_azi=180)
        assert cover.valid is False

    def test_sun_outside_fov_right(self):
        """Sun too far right is not valid."""
        cover = _make_vertical(sol_azi=280, sol_elev=45, win_azi=180)
        assert cover.valid is False

    def test_sun_below_horizon(self):
        """Sun below horizon is not valid."""
        cover = _make_vertical(sol_azi=180, sol_elev=-5, win_azi=180)
        assert cover.valid is False

    def test_narrow_fov(self):
        """Test with narrow field of view."""
        cover = _make_vertical(
            sol_azi=160, sol_elev=45, win_azi=180, fov_left=10, fov_right=10
        )
        assert cover.valid is False

    def test_sun_at_fov_edge(self):
        """Sun right at FOV edge (gamma = 89) should be valid."""
        cover = _make_vertical(sol_azi=91, sol_elev=45, win_azi=180)
        assert cover.valid is True


# --- Valid elevation ---


class TestValidElevation:
    """Tests for valid_elevation property."""

    def test_no_constraints(self):
        """Valid if no min/max elevation constraints."""
        cover = _make_vertical(sol_elev=45)
        assert cover.valid_elevation is True

    def test_no_constraints_negative(self):
        """Not valid below horizon with no constraints."""
        cover = _make_vertical(sol_elev=-5)
        assert cover.valid_elevation is False

    def test_min_elevation(self):
        """Test minimum elevation filtering."""
        cover = _make_vertical(sol_elev=10, min_elevation=20)
        assert cover.valid_elevation is False

    def test_min_elevation_passes(self):
        """Test minimum elevation passes."""
        cover = _make_vertical(sol_elev=30, min_elevation=20)
        assert cover.valid_elevation is True

    def test_max_elevation(self):
        """Test maximum elevation filtering."""
        cover = _make_vertical(sol_elev=80, max_elevation=70)
        assert cover.valid_elevation is False

    def test_max_elevation_passes(self):
        """Test maximum elevation passes."""
        cover = _make_vertical(sol_elev=60, max_elevation=70)
        assert cover.valid_elevation is True

    def test_both_constraints(self):
        """Test with both min and max elevation."""
        cover = _make_vertical(sol_elev=45, min_elevation=20, max_elevation=70)
        assert cover.valid_elevation is True

    def test_both_constraints_below(self):
        """Test below range with both constraints."""
        cover = _make_vertical(sol_elev=10, min_elevation=20, max_elevation=70)
        assert cover.valid_elevation is False


# --- Vertical cover calculations ---


class TestAdaptiveVerticalCover:
    """Tests for vertical cover position calculations."""

    def test_calculate_position_sun_in_front(self):
        """Sun directly in front should produce positive position."""
        cover = _make_vertical(sol_azi=180, sol_elev=45, win_azi=180)
        pos = cover.calculate_position()
        assert pos > 0
        # With distance=0.5, elevation=45, gamma=0: height = 0.5 * tan(45) = 0.5
        assert pos == pytest.approx(0.5, abs=0.01)

    def test_calculate_position_high_elevation(self):
        """High elevation should produce larger position (more coverage)."""
        cover = _make_vertical(sol_azi=180, sol_elev=70, win_azi=180)
        pos = cover.calculate_position()
        # height = 0.5 * tan(70) ≈ 1.37, clipped to h_win=2.1
        assert pos == pytest.approx(0.5 * np.tan(np.radians(70)), abs=0.01)

    def test_calculate_position_clipped_to_window(self):
        """Position should be clipped to window height."""
        cover = _make_vertical(sol_azi=180, sol_elev=85, win_azi=180, h_win=1.0)
        pos = cover.calculate_position()
        assert pos == pytest.approx(1.0)  # clipped to h_win

    def test_calculate_percentage(self):
        """Percentage should be height/h_win * 100."""
        cover = _make_vertical(
            sol_azi=180, sol_elev=45, win_azi=180, distance=0.5, h_win=2.0
        )
        pct = cover.calculate_percentage()
        # height = 0.5 * tan(45) = 0.5; percentage = 0.5/2.0 * 100 = 25
        assert pct == 25

    def test_calculate_percentage_full_coverage(self):
        """Very high sun should give high percentage."""
        cover = _make_vertical(
            sol_azi=180, sol_elev=80, win_azi=180, distance=1.0, h_win=2.1
        )
        pct = cover.calculate_percentage()
        assert pct > 90  # Should be close to 100%


# --- Horizontal cover calculations ---


class TestAdaptiveHorizontalCover:
    """Tests for horizontal awning calculations."""

    def test_calculate_percentage_basic(self):
        """Basic awning percentage calculation."""
        cover = _make_horizontal(
            sol_azi=180, sol_elev=45, win_azi=180, distance=0.5, h_win=2.1
        )
        pct = cover.calculate_percentage()
        # Should produce a valid percentage
        assert 0 <= pct <= 200  # Can exceed 100 before clamping in NormalCoverState

    def test_calculate_position_returns_float(self):
        """Position should be a float."""
        cover = _make_horizontal(sol_azi=180, sol_elev=60, win_azi=180)
        pos = cover.calculate_position()
        assert isinstance(pos, (float, np.floating))


# --- Tilt cover calculations ---


class TestAdaptiveTiltCover:
    """Tests for tilt cover calculations."""

    def test_beta_property(self):
        """Beta should be calculated from elevation and gamma."""
        cover = _make_tilt(sol_azi=180, sol_elev=45, win_azi=180)
        # When gamma=0: beta = arctan(tan(45)/cos(0)) = arctan(1/1) = 45°
        assert np.rad2deg(cover.beta) == pytest.approx(45, abs=0.1)

    def test_mode1_percentage(self):
        """Mode1 scales angle/90*100; can exceed 100 (clamped by NormalCoverState)."""
        cover = _make_tilt(sol_azi=180, sol_elev=45, win_azi=180, mode="mode1")
        pct = cover.calculate_percentage()
        assert pct > 0  # Should be a positive percentage

    def test_mode2_percentage(self):
        """Mode2 should scale to 0-180 degrees -> 0-100%."""
        cover = _make_tilt(sol_azi=180, sol_elev=45, win_azi=180, mode="mode2")
        pct = cover.calculate_percentage()
        assert 0 <= pct <= 100

    def test_mode1_higher_than_mode2(self):
        """Mode1 percentage should be higher than mode2 for same angle."""
        cover1 = _make_tilt(sol_azi=180, sol_elev=45, win_azi=180, mode="mode1")
        cover2 = _make_tilt(sol_azi=180, sol_elev=45, win_azi=180, mode="mode2")
        assert cover1.calculate_percentage() > cover2.calculate_percentage()


# --- NormalCoverState ---


class TestNormalCoverState:
    """Tests for NormalCoverState."""

    def test_returns_calculated_when_sun_valid(self):
        """Should return calculated percentage when sun is in FOV."""
        cover = _make_vertical(sol_azi=180, sol_elev=45, win_azi=180)
        state = NormalCoverState(cover)
        result = state.get_state()
        # Sun is in FOV and not sunset, so should use calculate_percentage
        assert result == cover.calculate_percentage()

    def test_returns_default_when_sun_not_valid(self):
        """Should return default when sun is not in FOV."""
        # Sun behind window (azimuth=0 vs window=180), so valid=False
        # With sunset_valid=False (mocked), default = h_def = 60
        cover = _make_vertical(sol_azi=0, sol_elev=45, win_azi=180, h_def=60)
        state = NormalCoverState(cover)
        result = state.get_state()
        # direct_sun_valid=False -> uses default (h_def since sunset_valid=False)
        assert result == 60

    def test_max_position_clamping(self):
        """Should clamp to max_pos when enabled (and max_pos_bool=False means always applied)."""
        cover = _make_vertical(
            sol_azi=180, sol_elev=80, win_azi=180, max_pos=50, distance=1.0, h_win=2.1
        )
        state = NormalCoverState(cover)
        result = state.get_state()
        # max_pos_bool=False means apply_max_position checks if max_pos != 100
        # max_pos=50 != 100, so max_pos is applied
        assert result == 50

    def test_min_position_clamping(self):
        """Should clamp to min_pos when enabled (and min_pos_bool=False means always applied)."""
        cover = _make_vertical(
            sol_azi=180, sol_elev=10, win_azi=180, min_pos=30, h_def=20
        )
        state = NormalCoverState(cover)
        result = state.get_state()
        assert result >= 30

    def test_state_clipped_0_to_100(self):
        """State should never be below 0 or above 100."""
        cover = _make_vertical(sol_azi=180, sol_elev=45, win_azi=180)
        state = NormalCoverState(cover)
        result = state.get_state()
        assert 0 <= result <= 100


# --- get_state_reason ---


class TestGetStateReason:
    """Tests for get_state_reason function."""

    def test_sun_in_window(self):
        """Should report sun in window when direct_sun_valid."""
        cover = _make_vertical(sol_azi=180, sol_elev=45, win_azi=180)
        reason = get_state_reason(cover)
        assert "Sun in window" in reason
        assert "180" in reason
        assert "45" in reason

    def test_sun_below_horizon(self):
        """Should report sun below horizon."""
        cover = _make_vertical(sol_azi=180, sol_elev=-5, win_azi=180)
        reason = get_state_reason(cover)
        assert reason == "Sun below horizon"

    def test_sun_outside_fov(self):
        """Should report sun outside field of view."""
        # Sun behind window
        cover = _make_vertical(sol_azi=0, sol_elev=45, win_azi=180)
        reason = get_state_reason(cover)
        assert "Sun outside field of view" in reason

    def test_elevation_outside_range(self):
        """Should report elevation outside configured range."""
        cover = _make_vertical(sol_azi=180, sol_elev=80, win_azi=180, max_elevation=70)
        reason = get_state_reason(cover)
        assert "outside configured range" in reason

    def test_blind_spot(self):
        """Should report sun in blind spot."""
        # Sun in front (gamma=0) in blind spot: left_edge=90-0=90, right_edge=90-90=0
        # blindspot = (0 <= 90) & (0 >= 0) & (30 <= 90) = True
        cover = _make_vertical(
            sol_azi=180,
            sol_elev=30,
            win_azi=180,
            blind_spot_left=0,
            blind_spot_right=90,
            blind_spot_elevation=90,
            blind_spot_on=True,
        )
        reason = get_state_reason(cover)
        assert reason == "Sun in blind spot"


# --- calculate_percentage_at ---


class TestCalculatePercentageAt:
    """Tests for calculate_percentage_at method."""

    def test_returns_correct_position(self):
        """Should calculate position for given azi/elev."""
        cover = _make_vertical(
            sol_azi=100, sol_elev=10, win_azi=180, distance=0.5, h_win=2.0
        )
        result = cover.calculate_percentage_at(180, 45)
        # At azi=180, elev=45 with window at 180: sun is directly in front
        # height = 0.5 * tan(45) = 0.5; percentage = 0.5/2.0 * 100 = 25
        assert result == 25

    def test_restores_original_values(self):
        """Should restore original sol_azi and sol_elev after calculation."""
        cover = _make_vertical(sol_azi=100, sol_elev=10, win_azi=180)
        cover.calculate_percentage_at(180, 45)
        assert cover.sol_azi == 100
        assert cover.sol_elev == 10

    def test_restores_on_error(self):
        """Original values should be restored even if calculation fails."""
        cover = _make_vertical(sol_azi=100, sol_elev=10, win_azi=180)
        # Even with unusual values, should restore
        cover.calculate_percentage_at(0, -90)
        assert cover.sol_azi == 100
        assert cover.sol_elev == 10

    def test_different_positions_for_different_inputs(self):
        """Different solar positions should give different results."""
        cover = _make_vertical(
            sol_azi=180, sol_elev=45, win_azi=180, distance=0.5, h_win=2.0
        )
        pos1 = cover.calculate_percentage_at(180, 30)
        pos2 = cover.calculate_percentage_at(180, 60)
        # Higher elevation = more coverage
        assert pos2 > pos1
