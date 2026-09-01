"""Pure-function unit tests for coordinator helpers.

Manager latch semantics, toggle-off/restart override handling, and
set_last_updated behavior are pinned at behavior level by the simulation
days (tests/simulation/test_manual_override_behavior.py for mutations
M08/M11/M12, tests/simulation/test_gates_and_windows.py and
test_lifecycle.py for M13); the load-bearing inverse pin also lives in
tests/simulation/test_transforms.py (M35).
"""

import datetime as dt
import logging

import pytest

from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)
from custom_components.adaptive_cover.coordinator import (
    AdaptiveCoverManager,
    inverse_state,
)


# --- inverse_state ---


class TestInverseState:
    """Tests for the inverse_state helper function."""

    def test_zero_becomes_100(self):
        assert inverse_state(0) == 100

    def test_100_becomes_zero(self):
        assert inverse_state(100) == 0

    def test_50_stays_50(self):
        assert inverse_state(50) == 50

    def test_25_becomes_75(self):
        assert inverse_state(25) == 75


# --- Duration format variants ---


def _make_manager_with_dict(duration_dict):
    """Create an AdaptiveCoverManager from a raw duration dict."""
    logger = ConfigContextAdapter(logging.getLogger("test"))
    logger.set_config_name("Test")
    return AdaptiveCoverManager(duration_dict, logger)


class TestDurationFormatVariants:
    """Verify that different dict formats all produce the correct timedelta."""

    def test_minutes_only(self):
        """{"minutes": 30} → 30 min."""
        mgr = _make_manager_with_dict({"minutes": 30})
        assert mgr.reset_duration == dt.timedelta(minutes=30)

    def test_ha_duration_selector_format(self):
        """{"hours": 0, "minutes": 30, "seconds": 0} → 30 min (HA DurationSelector)."""
        mgr = _make_manager_with_dict({"hours": 0, "minutes": 30, "seconds": 0})
        assert mgr.reset_duration == dt.timedelta(minutes=30)

    def test_seconds_only(self):
        """{"seconds": 1800} → 30 min."""
        mgr = _make_manager_with_dict({"seconds": 1800})
        assert mgr.reset_duration == dt.timedelta(minutes=30)

    def test_hours_only(self):
        """{"hours": 1} → 60 min."""
        mgr = _make_manager_with_dict({"hours": 1})
        assert mgr.reset_duration == dt.timedelta(hours=1)

    def test_ha_format_45_minutes(self):
        """HA DurationSelector with 45 minutes."""
        mgr = _make_manager_with_dict({"hours": 0, "minutes": 45, "seconds": 0})
        assert mgr.reset_duration == dt.timedelta(minutes=45)

    @pytest.mark.asyncio
    async def test_ha_format_override_respects_duration(self):
        """Override with HA DurationSelector format should last the configured time."""
        mgr = _make_manager_with_dict({"hours": 0, "minutes": 45, "seconds": 0})
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")

        # 10 minutes ago — should still be active (10 < 45)
        mgr.manual_control_time["cover.a"] = dt.datetime.now(
            dt.UTC
        ) - dt.timedelta(minutes=10)
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is True

        # 50 minutes ago — should expire (50 > 45)
        mgr.manual_control_time["cover.a"] = dt.datetime.now(
            dt.UTC
        ) - dt.timedelta(minutes=50)
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is False
