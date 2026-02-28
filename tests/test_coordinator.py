"""Tests for coordinator module."""

import datetime as dt
import logging
from unittest.mock import MagicMock

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


# --- AdaptiveCoverManager ---


def _make_manager(reset_minutes=15):
    """Create an AdaptiveCoverManager for testing."""
    logger = ConfigContextAdapter(logging.getLogger("test"))
    logger.set_config_name("Test")
    return AdaptiveCoverManager({"minutes": reset_minutes}, logger)


class TestAdaptiveCoverManager:
    """Tests for AdaptiveCoverManager."""

    def test_add_covers(self):
        """Test adding cover entities."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a", "cover.b"])
        assert mgr.covers == {"cover.a", "cover.b"}

    def test_add_covers_idempotent(self):
        """Adding the same cover twice doesn't duplicate."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])
        mgr.add_covers(["cover.a", "cover.b"])
        assert mgr.covers == {"cover.a", "cover.b"}

    def test_mark_manual_control(self):
        """Test marking a cover as manually controlled."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")
        assert mgr.is_cover_manual("cover.a") is True

    def test_is_cover_manual_default_false(self):
        """Unregistered cover should not be manual."""
        mgr = _make_manager()
        assert mgr.is_cover_manual("cover.unknown") is False

    def test_binary_cover_manual(self):
        """binary_cover_manual should be True when any cover is manual."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a", "cover.b"])
        assert mgr.binary_cover_manual is False

        mgr.mark_manual_control("cover.a")
        assert mgr.binary_cover_manual is True

    def test_manual_controlled_list(self):
        """manual_controlled should list only manually controlled covers."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a", "cover.b", "cover.c"])
        mgr.mark_manual_control("cover.a")
        mgr.mark_manual_control("cover.c")
        assert sorted(mgr.manual_controlled) == ["cover.a", "cover.c"]

    def test_reset(self):
        """Reset should clear manual control for a cover."""
        mgr = _make_manager()
        mgr.mark_manual_control("cover.a")
        mgr.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC)
        assert mgr.is_cover_manual("cover.a") is True

        mgr.reset("cover.a")
        assert mgr.is_cover_manual("cover.a") is False
        assert "cover.a" not in mgr.manual_control_time

    @pytest.mark.asyncio
    async def test_reset_if_needed_expired(self):
        """Should reset covers whose manual control duration has elapsed."""
        mgr = _make_manager(reset_minutes=15)
        mgr.mark_manual_control("cover.a")
        # Set manual control time to 20 minutes ago
        mgr.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC) - dt.timedelta(
            minutes=20
        )
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is False

    @pytest.mark.asyncio
    async def test_reset_if_needed_not_expired(self):
        """Should NOT reset covers whose duration hasn't elapsed."""
        mgr = _make_manager(reset_minutes=15)
        mgr.mark_manual_control("cover.a")
        # Set manual control time to 5 minutes ago
        mgr.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC) - dt.timedelta(
            minutes=5
        )
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is True

    def test_handle_state_change_detects_manual(self):
        """State change with different position should mark as manual."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        # Create mock state change data
        event = MagicMock()
        event.entity_id = "cover.a"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_position": 75}
        event.new_state.last_updated = dt.datetime.now(dt.UTC)

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=None,
        )
        assert mgr.is_cover_manual("cover.a") is True

    def test_handle_state_change_ignores_matching(self):
        """State change matching our state should NOT mark as manual."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        event = MagicMock()
        event.entity_id = "cover.a"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_position": 50}

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=None,
        )
        assert mgr.is_cover_manual("cover.a") is False

    def test_handle_state_change_respects_threshold(self):
        """Small changes below threshold should NOT mark as manual."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        event = MagicMock()
        event.entity_id = "cover.a"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_position": 52}

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=5,
        )
        assert mgr.is_cover_manual("cover.a") is False

    def test_handle_state_change_tilt_type(self):
        """Tilt cover should read current_tilt_position attribute."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        event = MagicMock()
        event.entity_id = "cover.a"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_tilt_position": 80}
        event.new_state.last_updated = dt.datetime.now(dt.UTC)

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_tilt",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=None,
        )
        assert mgr.is_cover_manual("cover.a") is True

    def test_handle_state_change_skips_wait_for_target(self):
        """Should not detect manual if waiting for target position."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        event = MagicMock()
        event.entity_id = "cover.a"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_position": 75}

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={"cover.a": True},
            manual_threshold=None,
        )
        assert mgr.is_cover_manual("cover.a") is False

    def test_handle_state_change_ignores_unknown_cover(self):
        """Should ignore state changes for covers not in the set."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])

        event = MagicMock()
        event.entity_id = "cover.unknown"
        event.new_state = MagicMock()
        event.new_state.attributes = {"current_position": 75}

        mgr.handle_state_change(
            states_data=event,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=None,
        )
        assert mgr.is_cover_manual("cover.unknown") is False

    def test_handle_state_change_none_data(self):
        """Should handle None states_data gracefully."""
        mgr = _make_manager()
        mgr.handle_state_change(
            states_data=None,
            our_state=50,
            blind_type="cover_blind",
            allow_reset=True,
            wait_target_call={},
            manual_threshold=None,
        )
        # Should not raise

    @pytest.mark.asyncio
    async def test_reset_duration_is_configurable(self):
        """Override should last for the configured duration, not a hardcoded value."""
        mgr = _make_manager(reset_minutes=45)
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")

        # 30 minutes ago — still within the 45-minute window
        mgr.manual_control_time["cover.a"] = dt.datetime.now(
            dt.UTC
        ) - dt.timedelta(minutes=30)
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is True

        # 50 minutes ago — past the 45-minute window
        mgr.manual_control_time["cover.a"] = dt.datetime.now(
            dt.UTC
        ) - dt.timedelta(minutes=50)
        await mgr.reset_if_needed()
        assert mgr.is_cover_manual("cover.a") is False

    def test_reset_duration_update_takes_effect(self):
        """Changing reset_duration on the manager should affect future resets."""
        mgr = _make_manager(reset_minutes=5)
        assert mgr.reset_duration == dt.timedelta(minutes=5)

        # Simulate what _update_manager_and_covers now does
        mgr.reset_duration = dt.timedelta(minutes=60)
        assert mgr.reset_duration == dt.timedelta(minutes=60)

    @pytest.mark.asyncio
    async def test_reset_duration_update_affects_expiry(self):
        """After updating reset_duration, the new value should govern expiry."""
        mgr = _make_manager(reset_minutes=5)
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")

        # 10 minutes ago — would expire with 5-min duration
        mgr.manual_control_time["cover.a"] = dt.datetime.now(
            dt.UTC
        ) - dt.timedelta(minutes=10)

        # Extend duration to 30 minutes (simulating the bug fix)
        mgr.reset_duration = dt.timedelta(minutes=30)

        await mgr.reset_if_needed()
        # Should still be manual because 10 < 30
        assert mgr.is_cover_manual("cover.a") is True
