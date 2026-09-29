"""The commands in flight to each cover (refactor P4).

When the coordinator sends a position, the cover travels for up to
``TARGET_TIMEOUT``. During that travel window its reports are echoes of
our command, not human moves. This module keeps that per-cover state (the
travel latch, the target, when it was sent, our context ids, sends that
raised but may still arrive) and classifies cover reports against it. It
has no ``hass``: time comes from the clock, and the arrival poll goes
through callables the coordinator provides.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any, NamedTuple

from .clock import Clock

_LOGGER = logging.getLogger(__name__)

type PollAction = Callable[[dt.datetime], Coroutine[Any, Any, None]]
"""A timed callback: receives the time it fires."""
type CallLater = Callable[[float, PollAction], Callable[[], None]]
"""Run an action after a delay in seconds; returns a cancel function."""
type ForcePoll = Callable[[str], Coroutine[Any, Any, None]]
"""Ask the cover entity for a fresh state now."""

MOTION = ("opening", "closing")


class UnconfirmedSend(NamedTuple):
    """A send that raised but may still have reached the motor."""

    target: int
    sent_at: dt.datetime
    source: str
    reason: str | None


class CommandTracker:
    """The in-flight command state of a window's covers."""

    # Wait-for-target: covers rarely land exactly on the commanded value
    # (99 when told 100), and a latch that never clears swallows every
    # subsequent HUMAN move - adaptive then reverts people within minutes.
    TARGET_TOLERANCE = 3  # percent: close enough counts as arrived
    TARGET_TIMEOUT = dt.timedelta(seconds=120)  # travel-time upper bound

    def __init__(
        self,
        clock: Clock,
        call_later: CallLater,
        force_poll: ForcePoll,
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Track commands; schedule arrival polls through ``call_later``."""
        self.clock = clock
        self._call_later = call_later
        self._force_poll = force_poll
        self.logger = logger
        self.wait_for_target: dict[str, bool] = {}
        """The travel latch: True while our command to the cover travels."""
        self.target_call: dict[str, int] = {}
        """The position we last commanded."""
        self.target_call_time: dict[str, dt.datetime] = {}
        """When we last commanded the cover."""
        self._our_context_ids: deque[str] = deque(maxlen=64)
        self._poll_cancels: dict[str, Callable[[], None]] = {}
        # Sends that raised but may still have reached the motor. See
        # adopt_late_delivery.
        self._unconfirmed_sends: dict[str, UnconfirmedSend] = {}

    # ------------------------------------------------------------ sending

    def start(self, entity: str, target: int) -> None:
        """Latch the travel window for a command about to be sent."""
        self.wait_for_target[entity] = True
        self.target_call[entity] = target
        self.target_call_time[entity] = self.clock.utcnow()
        self.logger.debug(
            "Set wait for target %s and target call %s",
            self.wait_for_target,
            self.target_call,
        )

    def remember_context(self, context_id: str) -> None:
        """Remember the context id a command is sent with."""
        self._our_context_ids.append(context_id)

    def is_own_context_id(self, context_id: str) -> bool:
        """Return True when ``context_id`` belongs to a command WE sent."""
        return context_id in self._our_context_ids

    def failed(self, entity: str, target: int, source: str, reason: str | None) -> None:
        """Record a send that raised: no travel, but it may arrive late."""
        self.wait_for_target[entity] = False
        # Zigbee often delivers a command whose acknowledgement is
        # lost, so the call raises while the motor still moves -
        # sometimes 30 s later. Remember the target so that late
        # start is not read as a human (house, 2026-09-29).
        self._unconfirmed_sends[entity] = UnconfirmedSend(
            target,
            self.clock.utcnow(),
            source,
            reason,
        )

    def delivered(self, entity: str) -> None:
        """Record a send that went through."""
        self._unconfirmed_sends.pop(entity, None)

    def release(self, entity: str) -> None:
        """Clear the travel latch: whatever the cover does now is not ours."""
        self.wait_for_target[entity] = False

    # ---------------------------------------------------------- questions

    def awaiting_target(self, entity: str) -> bool:
        """Return True while our last command to ``entity`` is travelling.

        A latch older than TARGET_TIMEOUT is stale: it is cleared here.
        """
        if self.wait_for_target.get(entity):
            sent_at = self.target_call_time.get(entity)
            if (
                sent_at is not None
                and self.clock.utcnow() - sent_at <= self.TARGET_TIMEOUT
            ):
                return True
            self.wait_for_target[entity] = False
        return False

    def is_own_landing(self, entity: str, position: int | None) -> bool:
        """Return True when ``position`` is the cover arriving at OUR command.

        The computed state can drift a few percent while the shade travels
        (sun keeps moving); comparing the landing against the recomputed
        state falsely latched a manual override on our own move. The landing
        must be compared against what we actually commanded.
        """
        target = self.target_call.get(entity)
        if target is None:
            return False
        return position is not None and abs(position - target) <= self.TARGET_TOLERANCE

    def classify_report(
        self,
        entity: str,
        report: str,
        position: int | None,
        own_context: bool = False,
    ) -> str | None:
        """Classify a cover report against the command in flight.

        ``report`` is the cover's state (``opening``, ``open``, ...).
        Returns None (no wait active / nothing notable), "arrived",
        "expired", "in_travel" (intermediate state while waiting), or
        "foreign_landing" (a definitive position report inside the travel
        window that is NOT our target — someone redirected the cover).
        Arrival and expiry clear the travel latch, and so does a foreign
        landing.
        """
        if self.wait_for_target.get(entity):
            target = self.target_call.get(entity)
            # Only a settled report is an arrival. An opening/closing report
            # still carries the position the shade LEFT, which for a small
            # move (99 -> 100) is within tolerance of the target: counting
            # it cleared the latch, and the next refresh re-sent the same
            # snap position (snaps bypass the delta and time gates).
            settled = report not in MOTION
            arrived = (
                settled
                and position is not None
                and target is not None
                and abs(position - target) <= self.TARGET_TOLERANCE
            )
            sent_at = self.target_call_time.get(entity)
            expired = (
                sent_at is None or self.clock.utcnow() - sent_at > self.TARGET_TIMEOUT
            )
            if arrived:
                self.wait_for_target[entity] = False
                self.logger.debug(
                    "Position %s within tolerance of target %s for %s",
                    position,
                    target,
                    entity,
                )
                return "arrived"
            if expired:
                # Motor had ample time; whatever moves now is a human.
                self.wait_for_target[entity] = False
                self.logger.debug(
                    "Target wait expired for %s (at %s, wanted %s); "
                    "treating changes as manual",
                    entity,
                    position,
                    target,
                )
                return "expired"
            if not own_context and settled and position is not None:
                # Definitive landing inside the travel window that is not
                # our target: a human stopped or redirected the cover.
                # Leaving the wait latched here swallowed the manual move
                # and the next sun tick reverted it.
                self.wait_for_target[entity] = False
                self.logger.debug(
                    "Landing at %s inside travel window differs from our "
                    "target %s for %s: foreign move",
                    position,
                    target,
                    entity,
                )
                return "foreign_landing"
            self.logger.debug("Wait for target: %s", self.wait_for_target)
            return "in_travel"
        self.logger.debug("No wait for target call for %s", entity)
        return None

    def release_if_against(self, entity: str, report: str, old_pos: int | None) -> bool:
        """Clear the travel latch when the cover moves AGAINST our command.

        A cover starting to move against our in-flight command is a human
        act even inside the travel window: our motor cannot reverse on its
        own. Returns True when the latch was cleared.
        """
        if report in MOTION and self.wait_for_target.get(entity):
            target = self.target_call.get(entity)
            if target is not None and old_pos is not None and target != old_pos:
                expected = "opening" if target > old_pos else "closing"
                if report != expected:
                    self.logger.debug(
                        "%s is %s but our command was %s: human takeover "
                        "during travel window",
                        entity,
                        report,
                        expected,
                    )
                    self.wait_for_target[entity] = False
                    return True
        return False

    def adopt_late_delivery(
        self, entity: str, report: str, old_pos: int | None
    ) -> UnconfirmedSend | None:
        """Adopt motion toward a send that raised as our own travel.

        A failed send leaves no command in flight, so the motor starting
        toward that target looked like a foreign move and latched a manual
        override. Within TARGET_TIMEOUT of the failed send, motion in the
        direction of its target restores the in-flight state instead.
        Returns the adopted send, or None.
        """
        sent = self._unconfirmed_sends.get(entity)
        if sent is None:
            return None
        target, sent_at = sent.target, sent.sent_at
        if self.clock.utcnow() - sent_at > self.TARGET_TIMEOUT:
            self._unconfirmed_sends.pop(entity, None)
            return None
        if old_pos is None or old_pos == target:
            return None
        expected = "opening" if target > old_pos else "closing"
        # Belt and braces: motion AGAINST our target is also caught right
        # after this by the against-direction check (so no test can tell
        # this guard apart; no mutation pins it). Skipping here keeps a
        # human move from being logged as a late delivery.
        if report != expected:
            return None
        self._unconfirmed_sends.pop(entity, None)
        self.wait_for_target[entity] = True
        self.target_call[entity] = target
        self.target_call_time[entity] = sent_at
        self.logger.debug(
            "%s started %s toward %s after a failed send: late delivery, "
            "not a manual move",
            entity,
            expected,
            target,
        )
        return sent

    # ------------------------------------------------------ arrival polls

    def schedule_arrival_poll(self, entity: str) -> None:
        """Force a device poll if no landing report arrives in time.

        Zigbee shades drop attribute reports; without this the entity can
        sit 'closing' at a stale position for minutes, freezing manual
        detection and the dashboard alike.
        """
        if (cancel := self._poll_cancels.pop(entity, None)) is not None:
            cancel()

        async def _poll_if_silent(_now: dt.datetime) -> None:
            self._poll_cancels.pop(entity, None)
            if not self.wait_for_target.get(entity):
                return  # arrived; nothing to do
            self.logger.debug("No landing report from %s; forcing a state poll", entity)
            await self._force_poll(entity)

        self._poll_cancels[entity] = self._call_later(
            self.TARGET_TIMEOUT.total_seconds() + 5,
            _poll_if_silent,
        )

    def cancel_polls(self) -> None:
        """Cancel every pending arrival poll (entry unload)."""
        for cancel in self._poll_cancels.values():
            cancel()
        self._poll_cancels.clear()
