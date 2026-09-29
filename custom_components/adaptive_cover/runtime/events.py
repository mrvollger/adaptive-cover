"""What the next refresh has to handle (refactor P4).

A window refreshes for several reasons: a tracked input changed, one of
its covers reported, the entry just started, or the end-of-day timer
fired. Four boolean flags on the coordinator used to carry those reasons;
:class:`RefreshQueue` carries them typed. It has no ``hass``.
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum


class RefreshEvent(StrEnum):
    """Why a refresh runs."""

    ENTITY_CHANGED = "entity_changed"
    """A tracked input (sun, sensor, end-time entity) changed: move if due."""
    COVER_CHANGED = "cover_changed"
    """One of the window's covers reported: check for a manual move."""
    STARTUP = "startup"
    """The entry's first refresh: position the covers."""
    END_TIME = "end_time"
    """The end-of-day timer fired: run the close."""


class RefreshQueue[C]:
    """The pending refresh events of one window.

    An event stays pending until its handler marks it done, as the flags
    did: several signals of one kind before a refresh collapse into one,
    and a handler that defers (the switches have not restored yet) leaves
    its event pending for the next refresh. Cover reports also queue, in
    order, with their state change (``C``), so covers that moved together
    are each checked.
    """

    def __init__(self) -> None:
        """Start with nothing pending."""
        self._pending: set[RefreshEvent] = set()
        self._covers: deque[C] = deque()

    def push(self, event: RefreshEvent) -> None:
        """Mark ``event`` pending."""
        self._pending.add(event)

    def push_cover(self, change: C) -> None:
        """Queue a cover report and mark COVER_CHANGED pending."""
        self._covers.append(change)
        self._pending.add(RefreshEvent.COVER_CHANGED)

    def pending(self, event: RefreshEvent) -> bool:
        """Return True while ``event`` waits for its handler."""
        return event in self._pending

    def done(self, event: RefreshEvent) -> None:
        """Mark ``event`` handled."""
        self._pending.discard(event)

    def take_covers(self) -> list[C]:
        """Remove and return the queued cover reports, oldest first."""
        covers = list(self._covers)
        self._covers.clear()
        return covers
