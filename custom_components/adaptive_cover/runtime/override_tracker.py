"""The manual-override clock of a window's covers (refactor P4).

A cover a person moved stays under manual control for the override
duration; after that, automatic control resumes. This module keeps that
state per cover (latched or not, when the clock started) in a dict the
coordinator owns in ``hass.data``, so an options reload does not wipe an
active override. It has no ``hass``: time comes from the clock.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from .clock import SYSTEM_CLOCK, Clock


class Stamped(Protocol):
    """A cover state report: when it was written."""

    @property
    def last_updated(self) -> dt.datetime:
        """The time the state was written (tz-aware)."""
        ...


class OverrideTracker:
    """Track which covers are under manual control, and until when."""

    def __init__(
        self,
        reset_duration: Mapping[str, float],
        logger: logging.Logger | logging.LoggerAdapter[Any],
        persisted_state: dict[str, Any] | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        """Initialize the override tracker.

        persisted_state lets override bookkeeping survive an entry reload
        (options edits reload the entry and rebuild the coordinator): pass a
        dict owned by hass.data and the tracker mutates it in place. clock
        is the coordinator's (runtime/clock.py).
        """
        self.clock = clock
        self.covers: set[str] = set()

        state = persisted_state if persisted_state is not None else {}
        self.manual_control: dict[str, bool] = state.setdefault("control", {})
        self.manual_control_time: dict[str, dt.datetime] = state.setdefault("time", {})
        # Per-cover record of the allow_reset flag at latch time
        # (bookkeeping only; expiry itself is unconditional).
        self.reset_allowed: dict[str, bool] = state.setdefault("reset_allowed", {})
        self.reset_duration = dt.timedelta(**reset_duration)
        self.logger = logger

    def set_duration(self, duration: Mapping[str, float]) -> None:
        """Set the override duration (``timedelta`` keyword arguments)."""
        self.reset_duration = dt.timedelta(**duration)
        self.logger.debug(
            "Manual override duration from config: %s → timedelta: %s",
            duration,
            self.reset_duration,
        )

    def add_covers(self, entity: Iterable[str]) -> None:
        """Update set with entities."""
        self.covers.update(entity)

    def set_last_updated(
        self, entity_id: str, new_state: Stamped, allow_reset: bool
    ) -> None:
        """Set last updated time for manual control."""
        self.reset_allowed[entity_id] = bool(allow_reset)
        if entity_id not in self.manual_control_time or allow_reset:
            last_updated = new_state.last_updated
            self.manual_control_time[entity_id] = last_updated
            self.logger.debug(
                "Updating last updated for manual control to %s for %s. Allow reset:%s",
                last_updated,
                entity_id,
                allow_reset,
            )
        elif not allow_reset:
            self.logger.debug(
                "Already manual control time specified for %s, reset is not allowed by user setting:%s",
                entity_id,
                allow_reset,
            )

    def mark_manual_control(self, cover: str) -> None:
        """Mark cover as under manual control."""
        self.manual_control[cover] = True

    async def reset_if_needed(self) -> None:
        """Expire manual overrides whose duration elapsed.

        Every override expires after reset_duration; the reset toggle only
        controls whether later manual moves RESTART the clock (see
        set_last_updated), never whether expiry happens at all.
        """
        current_time = self.clock.utcnow()
        manual_control_time_copy = dict(self.manual_control_time)
        for entity_id, last_updated in manual_control_time_copy.items():
            if current_time - last_updated > self.reset_duration:
                self.logger.debug(
                    "Resetting manual override for %s, because duration has elapsed",
                    entity_id,
                )
                self.reset(entity_id)

    def reset(self, entity_id: str) -> None:
        """Reset manual control for a cover."""
        self.manual_control[entity_id] = False
        self.manual_control_time.pop(entity_id, None)
        self.reset_allowed.pop(entity_id, None)
        self.logger.debug("Reset manual override for %s", entity_id)

    def reset_all(self) -> None:
        """Clear every manual override (new day / deliberate resume)."""
        for entity_id in list(self.manual_control):
            self.reset(entity_id)

    def is_cover_manual(self, entity_id: str) -> bool:
        """Check if a cover is under manual control."""
        return self.manual_control.get(entity_id, False)

    @property
    def binary_cover_manual(self) -> bool:
        """Check if any cover is under manual control."""
        return any(value for value in self.manual_control.values())

    @property
    def manual_controlled(self) -> list[str]:
        """Get the list of covers under manual control."""
        return [k for k, v in self.manual_control.items() if v]
