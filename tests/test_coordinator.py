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
    AdaptiveDataUpdateCoordinator,
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


# --- Coordinator-level _update_manager_and_covers tests ---


def _make_mock_coordinator(
    entities=None,
    manual_duration=None,
    manual_toggle=True,
    manual_reset=False,
):
    """Create a minimal mock that has the attributes _update_manager_and_covers needs.

    Rather than instantiating the full AdaptiveDataUpdateCoordinator (which
    requires a running HA instance), we build a thin stand-in with the same
    attributes and bind the real method to it.
    """
    if entities is None:
        entities = ["cover.a"]
    if manual_duration is None:
        manual_duration = {"minutes": 15}

    logger = ConfigContextAdapter(logging.getLogger("test"))
    logger.set_config_name("Test")

    coord = MagicMock()
    coord.logger = logger
    coord.entities = entities
    coord.manual_duration = manual_duration
    coord.manual_reset = manual_reset
    coord._manual_toggle = manual_toggle
    coord.manager = AdaptiveCoverManager(manual_duration, logger)
    coord.manager.add_covers(entities)

    # Bind the real method so we test actual logic
    coord._update_manager_and_covers = (
        AdaptiveDataUpdateCoordinator._update_manager_and_covers.__get__(coord)
    )
    return coord


class TestUpdateManagerAndCovers:
    """Tests for the _update_manager_and_covers method on the coordinator."""

    def test_manual_toggle_true_preserves_override(self):
        """When manual_toggle=True, manual overrides should NOT be cleared."""
        coord = _make_mock_coordinator(manual_toggle=True)
        coord.manager.mark_manual_control("cover.a")
        coord.manager.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC)

        coord._update_manager_and_covers()

        assert coord.manager.is_cover_manual("cover.a") is True

    def test_manual_toggle_false_clears_override(self):
        """When manual_toggle=False, manual overrides should be cleared."""
        coord = _make_mock_coordinator(manual_toggle=False)
        coord.manager.mark_manual_control("cover.a")
        coord.manager.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC)

        coord._update_manager_and_covers()

        assert coord.manager.is_cover_manual("cover.a") is False

    def test_manual_toggle_none_clears_override(self):
        """When manual_toggle=None (init state), overrides should be cleared.

        This is the race condition: _manual_toggle starts as None, and
        `not None` is True, so all overrides get reset on every update
        cycle until the switch entity sets it to True.
        """
        coord = _make_mock_coordinator(manual_toggle=None)
        coord.manager.mark_manual_control("cover.a")
        coord.manager.manual_control_time["cover.a"] = dt.datetime.now(dt.UTC)

        coord._update_manager_and_covers()

        # With the current code: not None → True → overrides cleared
        assert coord.manager.is_cover_manual("cover.a") is False

    def test_duration_propagated_to_manager(self):
        """_update_manager_and_covers should set reset_duration from config."""
        coord = _make_mock_coordinator(
            manual_duration={"hours": 0, "minutes": 45, "seconds": 0}
        )

        coord._update_manager_and_covers()

        assert coord.manager.reset_duration == dt.timedelta(minutes=45)

    def test_duration_updates_on_every_call(self):
        """If the config duration changes, the manager should pick it up."""
        coord = _make_mock_coordinator(manual_duration={"minutes": 15})
        coord._update_manager_and_covers()
        assert coord.manager.reset_duration == dt.timedelta(minutes=15)

        # Simulate config change
        coord.manual_duration = {"minutes": 60}
        coord._update_manager_and_covers()
        assert coord.manager.reset_duration == dt.timedelta(minutes=60)


# --- set_last_updated / allow_reset interaction ---


class TestSetLastUpdated:
    """Tests for the set_last_updated behavior with allow_reset flag."""

    def test_allow_reset_true_updates_time(self):
        """With allow_reset=True, the timer should update on each state change."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")

        first_time = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
        state = MagicMock()
        state.last_updated = first_time
        mgr.set_last_updated("cover.a", state, allow_reset=True)
        assert mgr.manual_control_time["cover.a"] == first_time

        second_time = dt.datetime.now(dt.UTC)
        state.last_updated = second_time
        mgr.set_last_updated("cover.a", state, allow_reset=True)
        # With allow_reset=True, the time should be updated
        assert mgr.manual_control_time["cover.a"] == second_time

    def test_allow_reset_false_does_not_update_time(self):
        """With allow_reset=False, once set the timer should NOT be updated."""
        mgr = _make_manager()
        mgr.add_covers(["cover.a"])
        mgr.mark_manual_control("cover.a")

        first_time = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
        state = MagicMock()
        state.last_updated = first_time
        mgr.set_last_updated("cover.a", state, allow_reset=False)
        assert mgr.manual_control_time["cover.a"] == first_time

        second_time = dt.datetime.now(dt.UTC)
        state.last_updated = second_time
        mgr.set_last_updated("cover.a", state, allow_reset=False)
        # With allow_reset=False, the original time should be kept
        assert mgr.manual_control_time["cover.a"] == first_time
