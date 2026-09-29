"""CommandTracker: the in-flight command state of each cover (P4)."""

from __future__ import annotations

import datetime as dt

import pytest

from custom_components.adaptive_cover.runtime.command_tracker import (
    CommandTracker,
    UnconfirmedSend,
)

COVER = "cover.office"
T0 = dt.datetime(2026, 6, 21, 18, 0, tzinfo=dt.UTC)
TIMEOUT = CommandTracker.TARGET_TIMEOUT


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.current = T0

    def utcnow(self) -> dt.datetime:
        return self.current

    def advance(self, **delta) -> None:
        self.current += dt.timedelta(**delta)


class FakeScheduler:
    """Records call_later requests; the test fires them."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, object]] = []
        self.cancelled = 0

    def __call__(self, delay, action):
        self.calls.append((delay, action))

        def cancel() -> None:
            self.cancelled += 1

        return cancel


class Harness:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.scheduler = FakeScheduler()
        self.polled: list[str] = []

        async def force_poll(entity: str) -> None:
            self.polled.append(entity)

        self.tracker = CommandTracker(self.clock, self.scheduler, force_poll)


@pytest.fixture
def h() -> Harness:
    return Harness()


# ------------------------------------------------------------- travel latch


def test_start_latches_the_travel_window(h):
    h.tracker.start(COVER, 80)
    assert h.tracker.wait_for_target == {COVER: True}
    assert h.tracker.target_call == {COVER: 80}
    assert h.tracker.target_call_time == {COVER: T0}
    assert h.tracker.awaiting_target(COVER) is True


def test_nothing_sent_is_not_awaited(h):
    assert h.tracker.awaiting_target(COVER) is False


def test_latch_lasts_the_timeout_then_clears(h):
    h.tracker.start(COVER, 80)
    h.clock.advance(seconds=TIMEOUT.total_seconds())
    assert h.tracker.awaiting_target(COVER) is True
    h.clock.advance(seconds=1)
    assert h.tracker.awaiting_target(COVER) is False
    assert h.tracker.wait_for_target[COVER] is False


def test_release_clears_the_latch(h):
    h.tracker.start(COVER, 80)
    h.tracker.release(COVER)
    assert h.tracker.awaiting_target(COVER) is False


def test_context_ids(h):
    h.tracker.remember_context("ctx-1")
    assert h.tracker.is_own_context_id("ctx-1")
    assert not h.tracker.is_own_context_id("ctx-2")
    for n in range(64):
        h.tracker.remember_context(f"later-{n}")
    assert not h.tracker.is_own_context_id("ctx-1")  # only the last 64


# ----------------------------------------------------------- own landings


@pytest.mark.parametrize(
    ("position", "own"),
    [(80, True), (77, True), (83, True), (76, False), (84, False), (None, False)],
)
def test_own_landing_is_within_tolerance_of_our_target(h, position, own):
    h.tracker.start(COVER, 80)
    assert h.tracker.is_own_landing(COVER, position) is own


def test_no_command_means_no_own_landing(h):
    assert h.tracker.is_own_landing(COVER, 80) is False


# ------------------------------------------------------ report classifier


def test_report_without_a_command_in_flight(h):
    assert h.tracker.classify_report(COVER, "open", 50) is None


def test_settled_report_at_target_is_arrival(h):
    h.tracker.start(COVER, 80)
    assert h.tracker.classify_report(COVER, "open", 78) == "arrived"
    assert h.tracker.wait_for_target[COVER] is False


def test_motion_report_near_target_is_still_travel(h):
    """An opening report carries the position the shade LEFT."""
    h.tracker.start(COVER, 100)
    assert h.tracker.classify_report(COVER, "opening", 99) == "in_travel"
    assert h.tracker.wait_for_target[COVER] is True


def test_report_after_the_timeout_is_expiry(h):
    h.tracker.start(COVER, 80)
    h.clock.advance(seconds=TIMEOUT.total_seconds() + 1)
    assert h.tracker.classify_report(COVER, "opening", 40) == "expired"
    assert h.tracker.wait_for_target[COVER] is False


def test_settled_report_away_from_target_is_a_foreign_landing(h):
    h.tracker.start(COVER, 80)
    assert h.tracker.classify_report(COVER, "open", 40) == "foreign_landing"
    assert h.tracker.wait_for_target[COVER] is False


def test_own_echo_away_from_target_is_still_travel(h):
    h.tracker.start(COVER, 80)
    assert h.tracker.classify_report(COVER, "open", 40, own_context=True) == (
        "in_travel"
    )


def test_settled_report_without_position_is_still_travel(h):
    h.tracker.start(COVER, 80)
    assert h.tracker.classify_report(COVER, "open", None) == "in_travel"


# ------------------------------------------------ motion against our command


@pytest.mark.parametrize(
    ("old_pos", "target", "report", "released"),
    [
        (20, 80, "closing", True),  # we open, it closes: a human
        (20, 80, "opening", False),
        (80, 20, "opening", True),
        (80, 20, "closing", False),
        (50, 50, "closing", False),  # no direction to compare
        (None, 80, "closing", False),
        (20, 80, "open", False),  # not a motion report
    ],
)
def test_motion_against_our_command_releases_the_latch(
    h, old_pos, target, report, released
):
    h.tracker.start(COVER, target)
    assert h.tracker.release_if_against(COVER, report, old_pos) is released
    assert h.tracker.wait_for_target[COVER] is not released


def test_motion_without_a_command_in_flight_is_not_against_it(h):
    assert h.tracker.release_if_against(COVER, "closing", 20) is False


# --------------------------------------------------------- late delivery


def test_failed_send_leaves_nothing_in_flight(h):
    h.tracker.start(COVER, 80)
    h.tracker.failed(COVER, 80, "adaptive", "block glare")
    assert h.tracker.awaiting_target(COVER) is False


def test_motion_toward_a_failed_send_is_adopted(h):
    h.tracker.start(COVER, 80)
    h.tracker.failed(COVER, 80, "adaptive", "block glare")
    h.clock.advance(seconds=30)
    adopted = h.tracker.adopt_late_delivery(COVER, "opening", 20)
    assert adopted == UnconfirmedSend(80, T0, "adaptive", "block glare")
    assert h.tracker.wait_for_target[COVER] is True
    assert h.tracker.target_call[COVER] == 80
    assert h.tracker.target_call_time[COVER] == T0  # the original send time
    assert h.tracker.adopt_late_delivery(COVER, "opening", 20) is None  # once


def test_motion_away_from_a_failed_send_is_not_adopted(h):
    h.tracker.failed(COVER, 80, "adaptive", None)
    assert h.tracker.adopt_late_delivery(COVER, "closing", 20) is None
    assert h.tracker.adopt_late_delivery(COVER, "opening", 20) is not None


def test_a_failed_send_expires(h):
    h.tracker.failed(COVER, 80, "adaptive", None)
    h.clock.advance(seconds=TIMEOUT.total_seconds() + 1)
    assert h.tracker.adopt_late_delivery(COVER, "opening", 20) is None
    h.clock.current = T0  # even back in time: it was dropped
    assert h.tracker.adopt_late_delivery(COVER, "opening", 20) is None


@pytest.mark.parametrize("old_pos", [None, 80])
def test_no_direction_no_adoption(h, old_pos):
    h.tracker.failed(COVER, 80, "adaptive", None)
    assert h.tracker.adopt_late_delivery(COVER, "opening", old_pos) is None


def test_a_delivered_send_forgets_the_failed_one(h):
    h.tracker.failed(COVER, 80, "adaptive", None)
    h.tracker.delivered(COVER)
    assert h.tracker.adopt_late_delivery(COVER, "opening", 20) is None


# --------------------------------------------------------- arrival polls


async def test_silent_cover_gets_polled(h):
    h.tracker.start(COVER, 80)
    h.tracker.schedule_arrival_poll(COVER)
    [(delay, action)] = h.scheduler.calls
    assert delay == TIMEOUT.total_seconds() + 5
    await action(T0)
    assert h.polled == [COVER]


async def test_arrived_cover_is_not_polled(h):
    h.tracker.start(COVER, 80)
    h.tracker.schedule_arrival_poll(COVER)
    h.tracker.classify_report(COVER, "open", 80)
    await h.scheduler.calls[0][1](T0)
    assert h.polled == []


def test_a_new_poll_replaces_the_old_one(h):
    h.tracker.schedule_arrival_poll(COVER)
    h.tracker.schedule_arrival_poll(COVER)
    assert h.scheduler.cancelled == 1
    h.tracker.schedule_arrival_poll("cover.other")
    h.tracker.cancel_polls()
    assert h.scheduler.cancelled == 3
