"""The manual-override clock of a window's covers (refactor P4).

A cover a person moved stays under manual control for the override
duration; after that, automatic control resumes. This module keeps that
state per cover (latched or not, when the clock started) in a dict the
coordinator owns in ``hass.data``, so an options reload does not wipe an
active override. It has no ``hass``: time comes from the clock.

A **requested** hold (the Mode select's ``hold``, the ``hold`` service;
runtime/mode.py) is a latch with a fixed end in ``hold_until``. It ends
only then (or when the window goes auto or off): the clock rules of a
detected override (the override duration, the restart-on-move option, the
day rollover, switching detection off) do not apply to it.
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
        # The fixed end of each requested hold (a cover without one is a
        # detected override: latch time + reset_duration).
        self.hold_until: dict[str, dt.datetime] = state.setdefault("until", {})
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
            if entity_id in self.hold_until:
                # A person moved a cover under a requested hold: the hold
                # lasts at least as long as a detected override would.
                self.hold_until[entity_id] = max(
                    self.hold_until[entity_id], last_updated + self.reset_duration
                )
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

    def hold(self, cover: str, until: dt.datetime, now: dt.datetime) -> None:
        """Hold ``cover`` until ``until`` (a requested hold, latched ``now``)."""
        self.manual_control[cover] = True
        self.manual_control_time[cover] = now
        self.hold_until[cover] = until

    def expires_at(self, cover: str) -> dt.datetime | None:
        """When the cover's override ends, or None if it is not held.

        A requested hold ends at its ``hold_until``; a detected override the
        override duration after its latch time (the day rollover can end
        it earlier).
        """
        if not self.is_cover_manual(cover):
            return None
        if (until := self.hold_until.get(cover)) is not None:
            return until
        latched_at = self.manual_control_time.get(cover)
        if latched_at is None:
            return None
        return latched_at + self.reset_duration

    async def reset_if_needed(self) -> None:
        """Expire manual overrides whose duration elapsed.

        Every override expires after reset_duration; the reset toggle only
        controls whether later manual moves RESTART the clock (see
        set_last_updated), never whether expiry happens at all. A requested
        hold expires at its own end.
        """
        current_time = self.clock.utcnow()
        manual_control_time_copy = dict(self.manual_control_time)
        for entity_id, last_updated in manual_control_time_copy.items():
            if (until := self.hold_until.get(entity_id)) is not None:
                if current_time >= until:
                    self.logger.debug(
                        "Ending the hold of %s: it was held until %s",
                        entity_id,
                        until,
                    )
                    self.reset(entity_id)
                continue
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
        self.hold_until.pop(entity_id, None)
        self.logger.debug("Reset manual override for %s", entity_id)

    def reset_all(self) -> None:
        """Clear every manual override and hold (Mode off / deliberate resume)."""
        for entity_id in list(self.manual_control):
            self.reset(entity_id)

    def reset_detected(self) -> None:
        """Clear every detected override; requested holds keep their end.

        The day rollover and switching detection off end what a person's
        move started, not a hold someone asked for until a given time.
        """
        for entity_id in list(self.manual_control):
            if entity_id not in self.hold_until:
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
