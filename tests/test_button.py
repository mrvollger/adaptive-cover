"""Tests for the Adaptive Cover button platform."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from custom_components.adaptive_cover.button import AdaptiveCoverButton
from custom_components.adaptive_cover.const import CONF_ENTITIES

JAMMED = "cover.jammed"
UNREPORTED = "cover.never_recorded"
HEALTHY = "cover.healthy"


def _make_button(coordinator, entities):
    """Build a button wired to a mock coordinator and config entry."""
    config_entry = MagicMock()
    config_entry.data = {"name": "Test"}
    config_entry.options = {CONF_ENTITIES: entities}
    config_entry.entry_id = "test_entry"
    return AdaptiveCoverButton(
        config_entry,
        "test_entry",
        "Reset Manual Override",
        coordinator,
        display_name="Return to Auto",
    )


def _make_coordinator(wait_for_target, target_call_time):
    """Build a mock coordinator with the wait-for-target machinery."""
    coordinator = MagicMock()
    coordinator.state = 42
    coordinator.TARGET_TIMEOUT = timedelta(seconds=120)
    coordinator.wait_for_target = wait_for_target
    coordinator.target_call_time = target_call_time
    coordinator.manager.is_cover_manual.return_value = True
    coordinator.async_set_position = AsyncMock()
    coordinator.async_refresh = AsyncMock()
    return coordinator


async def test_regression_return_to_auto_bounded():
    """Return-to-auto must not spin forever on a cover that never reports.

    Regression: async_press waited with an unbounded
    `while wait_for_target.get(entity): await asyncio.sleep(1)` loop, so a
    jammed motor or a dropped position report stalled manager.reset and
    every remaining cover indefinitely.  The wait is now bounded by the
    coordinator's TARGET_TIMEOUT relative to target_call_time.
    """
    stale = datetime.now(UTC) - timedelta(seconds=300)  # past TARGET_TIMEOUT
    coordinator = _make_coordinator(
        wait_for_target={JAMMED: True, UNREPORTED: True, HEALTHY: False},
        target_call_time={JAMMED: stale},  # UNREPORTED has no record at all
    )
    button = _make_button(coordinator, [JAMMED, UNREPORTED, HEALTHY])

    # With the unbounded loop this would hang; the bound must finish fast.
    await asyncio.wait_for(button.async_press(), timeout=5)

    reset_entities = [call.args[0] for call in coordinator.manager.reset.call_args_list]
    assert reset_entities == [JAMMED, UNREPORTED, HEALTHY]
    assert coordinator.wait_for_target[JAMMED] is False
    assert coordinator.wait_for_target[UNREPORTED] is False
    coordinator.async_refresh.assert_awaited_once()


async def test_return_to_auto_waits_until_target_reported():
    """A cover that reports arrival within the bound is awaited normally."""
    coordinator = _make_coordinator(
        wait_for_target={HEALTHY: True},
        target_call_time={HEALTHY: datetime.now(UTC)},
    )

    async def _arrive(entity, _state):
        async def _clear():
            await asyncio.sleep(0)
            coordinator.wait_for_target[entity] = False

        asyncio.get_running_loop().create_task(_clear())

    coordinator.async_set_position = AsyncMock(side_effect=_arrive)
    button = _make_button(coordinator, [HEALTHY])

    await asyncio.wait_for(button.async_press(), timeout=5)

    coordinator.manager.reset.assert_called_once_with(HEALTHY)
