"""The end-of-day close (refactor P4).

With "return to sunset position" on, every cover closes to the sunset
position at the configured end time. This module arms the timer for that
moment, decides what a fire means (close now, or re-arm because the end
moved later), runs the close (skipping manual covers when it is a
catch-up), and keeps the closes that could not be delivered for a retry
when the cover comes back. It has no ``hass``: the timer, the wall clock,
the end time and the refresh go through callables the coordinator
provides.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

_LOGGER = logging.getLogger(__name__)

type FireAction = Callable[[dt.datetime], Coroutine[Any, Any, None]]
"""A timed callback: receives the time it fires."""
type TrackPoint = Callable[[FireAction, dt.datetime], Callable[[], None]]
"""Run an action at a point in time; returns a cancel function."""


class EndOfDay:
    """Arm, fire, run and retry the end-of-day close of one window."""

    def __init__(
        self,
        track_point: TrackPoint,
        now_local: Callable[[], dt.datetime],
        end_time: Callable[[], dt.datetime | None],
        request_close: Callable[[], Coroutine[Any, Any, None]],
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Arm through ``track_point``; ask for the close with ``request_close``.

        ``now_local`` and ``end_time`` return naive wall times in HA's
        configured zone (the end time is today's, or None).
        """
        self._track_point = track_point
        self._now_local = now_local
        self._end_time = end_time
        self._request_close = request_close
        self.logger = logger
        self._cancel: Callable[[], None] | None = None
        self.scheduled_time: dt.datetime | None = None
        """The end time armed (None: nothing armed yet; != compare re-arms)."""
        self.is_catchup = False
        """The armed close was already due when armed (restart or reload)."""
        # Covers whose end-of-day close could not be delivered (device
        # unavailable / service error): retried when the cover comes back.
        self.pending_snap: dict[str, int] = {}

    # --------------------------------------------------------------- timer

    def ensure_armed(
        self, end: dt.datetime | None, track_end_time: bool | None
    ) -> None:
        """Arm for ``end`` when the close is on and the end time changed."""
        # != (not >) so moving the end time EARLIER re-arms too; and a
        # first refresh after the end time arms a past point, which
        # fires immediately as a catch-up close.
        if end and track_end_time and end != self.scheduled_time:
            self.arm(end)

    def arm(self, end: dt.datetime) -> None:
        """(Re)arm the end-of-day listener for ``end``.

        Arming a time already in the past fires immediately: after an HA
        restart or entry reload that lands past the end time, the close
        still runs (as a catch-up, which respects manual overrides).
        """
        self.cancel()
        self.is_catchup = end <= self._now_local()
        self.logger.debug(
            "Scheduling end time update at %s (was %s, catchup=%s)",
            end,
            self.scheduled_time,
            self.is_catchup,
        )
        self._cancel = self._track_point(self._on_fire, end)
        self.scheduled_time = end

    def cancel(self) -> None:
        """Cancel the armed listener, if any."""
        if self._cancel:
            self._cancel()
            self._cancel = None

    def shutdown(self) -> None:
        """Cancel the listener and forget the armed time (entry unload)."""
        self.cancel()
        self.scheduled_time = None

    async def _on_fire(self, _fired_at: dt.datetime) -> None:
        """Control state at end time.

        The point-in-time listener never fires early, so a fire IS the end
        time: run the close unconditionally. (A 1-second equality check here
        silently dropped the close whenever the event loop delivered the
        callback late — the shades then stayed up all night.) The only
        exception: the end time was moved LATER after arming — re-arm.
        """
        current_end = self._end_time()
        self.logger.debug(
            "Timed refresh fired. Configured end: %s, armed for: %s",
            current_end,
            self.scheduled_time,
        )
        # Compare configured vs armed on the SAME naive basis — never
        # against a re-read wall clock, which diverges from the armed time
        # whenever the process timezone differs from HA's configured one.
        if (
            current_end is not None
            and self.scheduled_time is not None
            and current_end > self.scheduled_time
        ):
            self.logger.debug(
                "End time moved later (%s) after arming; re-arming", current_end
            )
            self.arm(current_end)
            return
        await self._request_close()

    # --------------------------------------------------------------- close

    async def close(
        self,
        covers: Iterable[str],
        sunset_pos: float | None,
        transform: Callable[[float | None], float],
        is_manual: Callable[[str], bool],
        send: Callable[[str, int], Coroutine[Any, Any, bool]],
    ) -> None:
        """Send the sunset position to each cover; keep undelivered ones.

        ``send`` returns False when the command could not be delivered.
        """
        # Same transform pipeline as every other move (interpolation +
        # inversion) — a raw sunset position is out of calibration for
        # interpolated covers and then primes false manual detection.
        target = int(transform(sunset_pos))
        for cover in covers:
            if self.is_catchup and is_manual(cover):
                # A catch-up close (armed after its moment: restart or
                # reload landed past the end time) must not bulldoze an
                # override a human set in the meantime. The on-time
                # close still wins over manual by design.
                self.logger.debug(
                    "Catch-up end close skips manually overridden %s", cover
                )
                continue
            delivered = await send(cover, target)
            if not delivered:
                self.pending_snap[cover] = target

    def finish(self) -> None:
        """Mark the close handled (ran, or control is off): the next is on time."""
        self.is_catchup = False

    def take_retry(self, entity: str, control: bool | None) -> int | None:
        """Return a missed close to resend now that ``entity`` is back.

        The missed close is dropped either way; it is resent only while
        automatic control is on.
        """
        pending = self.pending_snap.pop(entity, None)
        if pending is not None and control:
            return pending
        return None
