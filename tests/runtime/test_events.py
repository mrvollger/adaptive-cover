"""RefreshQueue: the typed reasons for the next refresh (P4)."""

from __future__ import annotations

import pytest

from custom_components.adaptive_cover.runtime.events import RefreshEvent, RefreshQueue


def test_nothing_pending_at_first():
    queue: RefreshQueue[str] = RefreshQueue()
    assert not any(queue.pending(event) for event in RefreshEvent)
    assert queue.take_covers() == []


@pytest.mark.parametrize(
    "event",
    [RefreshEvent.ENTITY_CHANGED, RefreshEvent.STARTUP, RefreshEvent.END_TIME],
)
def test_an_event_stays_pending_until_done(event):
    queue: RefreshQueue[str] = RefreshQueue()
    queue.push(event)
    queue.push(event)  # several signals collapse into one
    assert queue.pending(event)
    queue.done(event)
    assert not queue.pending(event)


def test_events_are_independent():
    queue: RefreshQueue[str] = RefreshQueue()
    queue.push(RefreshEvent.STARTUP)
    queue.push(RefreshEvent.END_TIME)
    queue.done(RefreshEvent.STARTUP)
    assert queue.pending(RefreshEvent.END_TIME)


def test_cover_reports_queue_in_order():
    queue: RefreshQueue[str] = RefreshQueue()
    queue.push_cover("left moved")
    queue.push_cover("right moved")
    assert queue.pending(RefreshEvent.COVER_CHANGED)
    assert queue.take_covers() == ["left moved", "right moved"]
    assert queue.take_covers() == []
    # Taking the reports does not mark them handled: the handler does.
    assert queue.pending(RefreshEvent.COVER_CHANGED)
    queue.done(RefreshEvent.COVER_CHANGED)
    assert not queue.pending(RefreshEvent.COVER_CHANGED)
