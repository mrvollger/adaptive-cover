"""Explainer: next change, forecast, last change and the move log (P4)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pytest

from custom_components.adaptive_cover.engine.models import Decision, Intent
from custom_components.adaptive_cover.runtime.explainer import Explainer

UTC = dt.UTC
NOW = dt.datetime(2026, 3, 20, 18, 0, tzinfo=UTC)
TOMORROW = dt.date(2026, 3, 21)


def utc(hour: int, minute: int = 0, day: int = 20) -> dt.datetime:
    return dt.datetime(2026, 3, day, hour, minute, tzinfo=UTC)


class FakeLocation:
    def sunrise(self, date, local=True):
        return dt.datetime(date.year, date.month, date.day, 13, 30, tzinfo=UTC)

    def sunset(self, date, local=True):
        return dt.datetime(date.year, date.month, date.day, 1, 30, tzinfo=UTC)


@dataclass
class FakeSun:
    sunrise_at: dt.datetime = utc(13, 30)
    sunset_at: dt.datetime = utc(1, 30, day=21)
    times: list[dt.datetime] = field(
        default_factory=lambda: [utc(h) for h in range(24)]
    )
    solar_azimuth: list[float] = field(default_factory=lambda: [180.0] * 24)
    solar_elevation: list[float] = field(default_factory=lambda: [30.0] * 24)
    location: FakeLocation = field(default_factory=FakeLocation)

    def sunrise(self):
        return self.sunrise_at

    def sunset(self):
        return self.sunset_at


@dataclass
class FakeCover:
    sun_data: FakeSun = field(default_factory=FakeSun)
    h_def: float = 60
    sunset_pos: float = 0
    sunset_off: float = 0
    sunrise_off: float = 0

    def calculate_percentage_at(self, azi, elev):
        return 42


def next_event(cover=None, **kwargs):
    args = {
        "now": NOW,
        "tomorrow": TOMORROW,
        "start": None,
        "end": None,
        "sun_table": None,
        "configured_end": None,
        "end_position": None,
        "override_expiries": [],
    }
    return Explainer().next_event(cover or FakeCover(), **(args | kwargs))


# ----------------------------------------------------------- next change


def test_the_earliest_event_wins():
    event = next_event(start=utc(19), end=utc(23))
    assert event == ("Sun enters window", utc(19), 42)


def test_sun_leaving_takes_the_default_position():
    assert next_event(end=utc(19)) == ("Sun leaves window", utc(19), 60)


def test_past_events_are_skipped():
    event = next_event(start=utc(17), end=utc(17, 30))
    assert event == ("Sunset + offset", utc(1, 30, day=21), 0)


def test_a_passed_sunset_asks_for_tomorrows():
    cover = FakeCover()
    cover.sun_data.sunset_at = utc(1, 30)  # this morning's UTC date: passed
    cover.sun_data.sunrise_at = utc(13, 30)  # passed too
    event = next_event(cover)
    assert event == ("Sunset + offset", utc(1, 30, day=21), 0)


def test_naive_times_are_read_as_utc():
    event = next_event(start=dt.datetime(2026, 3, 20, 19, 0))
    assert event == ("Sun enters window", utc(19), 42)


def test_configured_end_and_override_expiry():
    assert next_event(configured_end=utc(19), end_position=5) == (
        "Configured end time",
        utc(19),
        5,
    )
    assert next_event(override_expiries=[utc(17), utc(18, 30)]) == (
        "Manual override expires",
        utc(18, 30),
        None,
    )


def test_a_broken_sun_is_skipped():
    cover = FakeCover()
    cover.sun_data.sunset_at = None  # e.g. polar night
    cover.sun_data.sunrise_at = None
    assert next_event(cover) is None


def test_the_prediction_uses_the_cached_table():
    table = ([utc(19)], [180.0], [30.0])
    event = next_event(start=utc(19), sun_table=table)
    assert event == ("Sun enters window", utc(19), 42)


# --------------------------------------------------------------- forecast


class Climate:
    def __init__(self, inputs):
        self.inputs = inputs

    def to_inputs(self):
        return self.inputs


async def test_forecast_rebuilds_on_a_new_day_or_new_climate():
    explainer = Explainer()
    builds = []

    async def build():
        builds.append(1)
        return [{"time": "t", "position": 30, "intent": "x"}]

    def invert(position):
        return 100 - position

    await explainer.refresh_forecast(False, Climate("cold"), build, invert)
    assert explainer.forecast == [{"time": "t", "position": 70, "intent": "x"}]
    await explainer.refresh_forecast(False, Climate("cold"), build, invert)
    assert len(builds) == 1  # same snapshot: cached
    await explainer.refresh_forecast(False, Climate("hot"), build, invert)
    await explainer.refresh_forecast(True, Climate("hot"), build, invert)
    assert len(builds) == 3


async def test_a_failed_forecast_is_none():
    explainer = Explainer()

    async def build():
        raise RuntimeError("astral")

    await explainer.refresh_forecast(True, None, build, float)
    assert explainer.forecast is None


# ------------------------------------------------------------ last change


def test_last_change_tracks_the_computed_position():
    explainer = Explainer()
    explainer.note_state(30, "sun", NOW)
    assert explainer.last_change["new_position"] is None  # nothing before
    explainer.note_state(30, "sun", NOW)
    explainer.note_state(40, "sunset", NOW)
    assert explainer.last_change == {
        "old_position": 30,
        "new_position": 40,
        "time": NOW,
        "reason": "sunset",
    }


@pytest.mark.parametrize(("old", "expected_old"), [(20, 20), (None, 55)])
def test_last_change_from_a_cover_report(old, expected_old):
    explainer = Explainer()
    explainer.note_cover_report(80, old, 55, "Manual override", NOW)
    assert explainer.last_change == {
        "old_position": expected_old,
        "new_position": 80,
        "time": NOW,
        "reason": "Manual override",
    }


def test_a_report_without_position_changes_nothing():
    explainer = Explainer()
    explainer.note_cover_report(None, 20, 55, "x", NOW)
    assert explainer.last_change["new_position"] is None


# ---------------------------------------------------------------- moves


def test_move_log_keeps_the_last_ten():
    explainer = Explainer()
    for position in range(15):
        entry = explainer.record("cover.a", position, "adaptive", "glare", NOW)
    assert entry == {
        "time": "2026-03-20T18:00:00+00:00",
        "position": 14,
        "source": "adaptive",
        "reason": "glare",
    }
    assert [e["position"] for e in explainer.move_log["cover.a"]] == list(range(5, 15))


def test_last_move_line():
    explainer = Explainer()
    assert explainer.format_last_move("cover.a") is None
    explainer.record("cover.a", 37, "manual", None, NOW)
    line = explainer.format_last_move("cover.a")
    assert line is not None
    assert line.endswith(" -> 37% (manual)")


def test_attributes():
    explainer = Explainer()
    explainer.record("cover.a", 37, "adaptive", "glare", NOW)
    decision = Decision(position=37, intent=Intent.CALCULATED, trace=("a", "b"))
    attrs = explainer.attributes(
        {"default_percentage": 60},
        decision,
        {"cover.a": None, "cover.b": "quiet_hours"},
        ["cover.a", "cover.b"],
        {"azimuth": 180},
    )
    assert attrs["intent"] == str(Intent.CALCULATED)
    assert attrs["decision_trace"] == ["a", "b"]
    assert attrs["move_blocked_by"] == {"cover.b": "quiet_hours"}
    assert list(attrs["last_moves"]) == ["cover.a"]
    assert attrs["sun"] == {"azimuth": 180}
    assert explainer.attributes({}, None, {}, [], {})["intent"] is None
