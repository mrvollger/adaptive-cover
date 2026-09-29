"""EndOfDay: arming, firing, catch-up and retry of the end-of-day close (P4)."""

from __future__ import annotations

import datetime as dt

import pytest

from custom_components.adaptive_cover.runtime.end_of_day import EndOfDay

DAY = dt.date(2026, 3, 20)


def at(hhmm: str) -> dt.datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return dt.datetime.combine(DAY, dt.time(hour, minute))


class Harness:
    """Fakes for the timer, the wall clock, the end time and the refresh."""

    def __init__(self) -> None:
        self.now = at("12:00")
        self.end: dt.datetime | None = at("21:00")
        self.armed: list[tuple[object, dt.datetime]] = []
        self.cancelled = 0
        self.closes = 0
        self.sent: list[tuple[str, int]] = []
        self.undeliverable: set[str] = set()
        self.manual: set[str] = set()

        def track_point(action, point):
            self.armed.append((action, point))

            def cancel() -> None:
                self.cancelled += 1

            return cancel

        async def request_close() -> None:
            self.closes += 1

        self.eod = EndOfDay(
            track_point, lambda: self.now, lambda: self.end, request_close
        )

    async def fire(self) -> None:
        action, point = self.armed[-1]
        await action(point)

    async def send(self, cover: str, target: int) -> bool:
        self.sent.append((cover, target))
        return cover not in self.undeliverable

    async def close(self, covers, sunset_pos=10, transform=lambda x: x) -> None:
        await self.eod.close(
            covers, sunset_pos, transform, lambda c: c in self.manual, self.send
        )


@pytest.fixture
def h() -> Harness:
    return Harness()


# ------------------------------------------------------------------ arming


def test_arms_for_the_end_time(h):
    h.eod.ensure_armed(at("21:00"), True)
    assert [point for _, point in h.armed] == [at("21:00")]
    assert h.eod.scheduled_time == at("21:00")
    assert h.eod.is_catchup is False


@pytest.mark.parametrize(("end", "track"), [(None, True), (at("21:00"), False)])
def test_no_end_time_or_no_close_arms_nothing(h, end, track):
    h.eod.ensure_armed(end, track)
    assert h.armed == []


def test_an_unchanged_end_time_is_armed_once(h):
    h.eod.ensure_armed(at("21:00"), True)
    h.eod.ensure_armed(at("21:00"), True)
    assert len(h.armed) == 1


@pytest.mark.parametrize("new_end", ["20:00", "22:00"])
def test_a_changed_end_time_re_arms(h, new_end):
    h.eod.ensure_armed(at("21:00"), True)
    h.eod.ensure_armed(at(new_end), True)
    assert [point for _, point in h.armed] == [at("21:00"), at(new_end)]
    assert h.cancelled == 1


@pytest.mark.parametrize(
    ("now", "catchup"), [("20:59", False), ("21:00", True), ("23:00", True)]
)
def test_arming_a_due_time_is_a_catch_up(h, now, catchup):
    h.now = at(now)
    h.eod.arm(at("21:00"))
    assert h.eod.is_catchup is catchup


def test_shutdown_cancels_and_forgets(h):
    h.eod.ensure_armed(at("21:00"), True)
    h.eod.shutdown()
    assert h.cancelled == 1
    assert h.eod.scheduled_time is None
    h.eod.shutdown()  # nothing armed: nothing to cancel
    assert h.cancelled == 1


# ------------------------------------------------------------------ firing


async def test_a_fire_asks_for_the_close(h):
    h.eod.ensure_armed(at("21:00"), True)
    h.now = at("21:00")
    await h.fire()
    assert h.closes == 1


async def test_a_late_fire_still_closes(h):
    h.eod.ensure_armed(at("21:00"), True)
    h.now = at("21:07")  # the event loop delivered the callback late
    await h.fire()
    assert h.closes == 1


async def test_an_end_moved_later_re_arms_instead(h):
    h.eod.ensure_armed(at("21:00"), True)
    h.end = at("22:00")
    await h.fire()
    assert h.closes == 0
    assert h.armed[-1][1] == at("22:00")
    assert h.eod.scheduled_time == at("22:00")


@pytest.mark.parametrize("end", [None, at("20:00")])
async def test_an_end_gone_or_moved_earlier_closes(h, end):
    h.eod.ensure_armed(at("21:00"), True)
    h.end = end
    await h.fire()
    assert h.closes == 1


# ------------------------------------------------------------------- close


async def test_close_sends_the_transformed_sunset_position(h):
    await h.close(["cover.a", "cover.b"], sunset_pos=10, transform=lambda x: 100 - x)
    assert h.sent == [("cover.a", 90), ("cover.b", 90)]


async def test_on_time_close_wins_over_manual(h):
    h.manual = {"cover.a"}
    h.eod.arm(at("21:00"))
    await h.close(["cover.a", "cover.b"])
    assert [cover for cover, _ in h.sent] == ["cover.a", "cover.b"]


async def test_catch_up_close_skips_manual_covers(h):
    h.manual = {"cover.a"}
    h.now = at("23:00")
    h.eod.arm(at("21:00"))
    await h.close(["cover.a", "cover.b"])
    assert [cover for cover, _ in h.sent] == ["cover.b"]


async def test_finish_ends_the_catch_up(h):
    h.now = at("23:00")
    h.eod.arm(at("21:00"))
    h.eod.finish()
    assert h.eod.is_catchup is False


# ------------------------------------------------------------------ retry


async def test_undelivered_close_is_retried_when_the_cover_returns(h):
    h.undeliverable = {"cover.a"}
    await h.close(["cover.a", "cover.b"], sunset_pos=10)
    assert h.eod.pending_snap == {"cover.a": 10}
    assert h.eod.take_retry("cover.b", True) is None
    assert h.eod.take_retry("cover.a", True) == 10
    assert h.eod.take_retry("cover.a", True) is None  # sent once


@pytest.mark.parametrize("control", [False, None])
async def test_retry_needs_control_on_and_is_dropped_otherwise(h, control):
    h.undeliverable = {"cover.a"}
    await h.close(["cover.a"])
    assert h.eod.take_retry("cover.a", control) is None
    assert h.eod.pending_snap == {}
