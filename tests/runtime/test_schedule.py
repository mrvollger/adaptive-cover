"""Schedule: the daily start/end window of automatic control (P4)."""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from custom_components.adaptive_cover.const import (
    CONF_END_ENTITY,
    CONF_END_TIME,
    CONF_START_ENTITY,
    CONF_START_TIME,
)
from custom_components.adaptive_cover.runtime.schedule import Schedule
from custom_components.adaptive_cover.runtime.shade_config import ShadeConfig

DAY = dt.date(2026, 3, 20)
START_ENTITY = "input_datetime.shade_start"
END_ENTITY = "input_datetime.shade_end"


def at(hhmm: str, day: dt.date = DAY) -> dt.datetime:
    """Naive local wall time on ``day``."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hour, minute))


class FakeStates:
    """Dict-backed state reader that records what it was asked."""

    def __init__(self, **states: str | None) -> None:
        self.states = {f"input_datetime.{k}": v for k, v in states.items()}
        self.reads: list[str] = []

    def __call__(self, entity_id: str) -> str | None:
        self.reads.append(entity_id)
        return self.states.get(entity_id)


def config(**options) -> ShadeConfig:
    return ShadeConfig.from_options(options)


# ---------------------------------------------------------------- end time


def test_no_end_time():
    assert Schedule(FakeStates()).end_time(config(), DAY) is None


def test_fixed_end_time_is_today():
    end = Schedule(FakeStates()).end_time(config(**{CONF_END_TIME: "21:30:00"}), DAY)
    assert end == at("21:30")


def test_midnight_end_means_the_coming_midnight():
    end = Schedule(FakeStates()).end_time(config(**{CONF_END_TIME: "00:00:00"}), DAY)
    assert end == dt.datetime.combine(DAY + dt.timedelta(days=1), dt.time())


def test_end_entity_wins_over_the_fixed_end():
    states = FakeStates(shade_end="19:00:00")
    cfg = config(**{CONF_END_TIME: "21:30:00", CONF_END_ENTITY: END_ENTITY})
    assert Schedule(states).end_time(cfg, DAY) == at("19:00")
    assert states.reads == [END_ENTITY]


def test_regression_midnight_end_entity_means_the_coming_midnight():
    """An end ENTITY at 00:00 is normalized like the fixed end time."""
    cfg = config(**{CONF_END_ENTITY: END_ENTITY})
    end = Schedule(FakeStates(shade_end="00:00:00")).end_time(cfg, DAY)
    assert end == dt.datetime.combine(DAY + dt.timedelta(days=1), dt.time())


def test_a_dated_end_entity_keeps_its_date():
    cfg = config(**{CONF_END_ENTITY: END_ENTITY})
    states = FakeStates(shade_end="2026-03-22 00:00:00")
    end = Schedule(states).end_time(cfg, DAY)
    assert end == dt.datetime(2026, 3, 22)


def test_unavailable_end_entity_means_no_end():
    cfg = config(**{CONF_END_TIME: "21:30:00", CONF_END_ENTITY: END_ENTITY})
    assert Schedule(FakeStates(shade_end=None)).end_time(cfg, DAY) is None


# ------------------------------------------------------------ before / after


@pytest.mark.parametrize(
    ("now", "before"),
    [("21:29", True), ("21:30", False), ("23:00", False)],
)
def test_before_end(now, before):
    cfg = config(**{CONF_END_TIME: "21:30:00"})
    assert Schedule(FakeStates()).before_end(cfg, at(now)) is before


def test_before_a_midnight_end_holds_all_evening():
    cfg = config(**{CONF_END_TIME: "00:00:00"})
    assert Schedule(FakeStates()).before_end(cfg, at("23:59")) is True


def test_no_end_is_always_before_end():
    assert Schedule(FakeStates()).before_end(config(), at("23:59")) is True


@pytest.mark.parametrize(
    ("now", "after"),
    [("07:29", False), ("07:30", True), ("12:00", True)],
)
def test_after_fixed_start(now, after):
    cfg = config(**{CONF_START_TIME: "07:30:00"})
    assert Schedule(FakeStates()).after_start(cfg, at(now)) is after


def test_no_start_is_always_after_start():
    assert Schedule(FakeStates()).after_start(config(), at("00:00")) is True


def test_start_entity_wins_over_the_fixed_start():
    states = FakeStates(shade_start="09:00:00")
    cfg = config(**{CONF_START_TIME: "07:30:00", CONF_START_ENTITY: START_ENTITY})
    schedule = Schedule(states)
    assert schedule.after_start(cfg, at("08:00")) is False
    assert schedule.after_start(cfg, at("09:00")) is True
    assert schedule.last_start == at("09:00")


# ----------------------------------------------------------------- window


@pytest.mark.parametrize(
    ("now", "inside"),
    [("07:00", False), ("07:30", True), ("21:29", True), ("21:30", False)],
)
def test_in_window(now, inside):
    cfg = config(**{CONF_START_TIME: "07:30:00", CONF_END_TIME: "21:30:00"})
    assert Schedule(FakeStates()).in_window(cfg, at(now)) is inside


def test_no_times_is_always_in_window():
    assert Schedule(FakeStates()).in_window(config(), at("03:00")) is True


def test_start_after_end_is_logged(caplog):
    caplog.set_level(logging.ERROR)
    states = FakeStates(shade_start="22:00:00")
    cfg = config(**{CONF_START_ENTITY: START_ENTITY, CONF_END_TIME: "21:00:00"})
    schedule = Schedule(states)
    assert schedule.in_window(cfg, at("12:00")) is False  # records the start
    assert "Start time is after end time" not in caplog.text
    schedule.in_window(cfg, at("12:05"))
    assert "Start time is after end time" in caplog.text


# ------------------------------------------------ unreadable time entities


@pytest.mark.parametrize("state", [None, "not a time"])
def test_regression_unreadable_start_entity_falls_back(state):
    """An unreadable start entity uses the fixed start (it used to raise)."""
    cfg = config(**{CONF_START_TIME: "07:30:00", CONF_START_ENTITY: START_ENTITY})
    schedule = Schedule(FakeStates(shade_start=state))
    assert schedule.after_start(cfg, at("07:29")) is False
    assert schedule.after_start(cfg, at("07:30")) is True


@pytest.mark.parametrize("state", [None, "not a time"])
def test_regression_unreadable_start_entity_alone_is_not_started(state):
    cfg = config(**{CONF_START_ENTITY: START_ENTITY})
    schedule = Schedule(FakeStates(shade_start=state))
    assert schedule.after_start(cfg, at("23:00")) is False


def test_unparseable_end_entity_means_no_end():
    cfg = config(**{CONF_END_TIME: "21:30:00", CONF_END_ENTITY: END_ENTITY})
    assert Schedule(FakeStates(shade_end="soon")).end_time(cfg, DAY) is None
