"""GatePolicy: the gates between a computed position and a command (P4)."""

from __future__ import annotations

import datetime as dt

import pytest

from custom_components.adaptive_cover.const import (
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_POSITION,
    CONF_DELTA_TIME,
    CONF_MAX_MOVES_HOUR,
    CONF_PRIVACY_POSITION,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SUNSET_POS,
)
from custom_components.adaptive_cover.runtime.gates import CoverFacts, GatePolicy
from custom_components.adaptive_cover.runtime.shade_config import ShadeConfig

COVER = "cover.office"
NOW = dt.datetime(2026, 6, 21, 18, 0, tzinfo=dt.UTC)
NOON = dt.datetime(2026, 6, 21, 12, 0)  # naive local wall time

# Rest positions that are neither 0 nor 100, so each one is visible.
SNAPS = {CONF_SUNSET_POS: 10, CONF_DEFAULT_HEIGHT: 60, CONF_PRIVACY_POSITION: 35}


def config(**options) -> ShadeConfig:
    return ShadeConfig.from_options({**SNAPS, **options})


def local(hhmm: str) -> dt.datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return NOON.replace(hour=hour, minute=minute)


# ------------------------------------------------------------ position delta


@pytest.mark.parametrize(
    ("position", "state", "allowed"),
    [
        (None, 50, True),  # unknown position: cannot prove it is in place
        (50, 52, False),
        (50, 53, True),  # exactly min_change moves
        (50, 47, True),
        (50, 50, False),
    ],
)
def test_position_delta(position, state, allowed):
    cfg = config(**{CONF_DELTA_POSITION: 3})
    assert GatePolicy().position_delta_ok(COVER, position, state, cfg) is allowed


@pytest.mark.parametrize("state", [10, 60, 0, 100])
def test_small_moves_to_rest_positions_pass_the_delta_gate(state):
    cfg = config(**{CONF_DELTA_POSITION: 50})
    assert GatePolicy().position_delta_ok(COVER, state + 1, state, cfg) is True


# ---------------------------------------------------------------- time delta


@pytest.mark.parametrize(
    ("minutes_ago", "allowed"),
    [(None, True), (1, False), (4.9, False), (5, True), (30, True)],
)
def test_time_delta(minutes_ago, allowed):
    last = None if minutes_ago is None else NOW - dt.timedelta(minutes=minutes_ago)
    cfg = config(**{CONF_DELTA_TIME: 5})
    assert GatePolicy().time_delta_ok(COVER, last, NOW, cfg) is allowed


@pytest.mark.parametrize(
    ("state", "snap"),
    [(0, True), (100, True), (10, True), (60, True), (35, True)]
    + [(11, False), (50, False)],
)
def test_snap_positions(state, snap):
    assert GatePolicy().is_snap_position(state, config()) is snap


# --------------------------------------------------------------- quiet hours


@pytest.mark.parametrize(
    ("start", "end", "now", "allowed"),
    [
        ("12:00:00", "14:00:00", "11:59", True),
        ("12:00:00", "14:00:00", "12:00", False),  # start is inside
        ("12:00:00", "14:00:00", "13:59", False),
        ("12:00:00", "14:00:00", "14:00", True),  # end is outside
        ("22:00:00", "06:00:00", "23:00", False),  # window crosses midnight
        ("22:00:00", "06:00:00", "05:59", False),
        ("22:00:00", "06:00:00", "06:00", True),
        ("22:00:00", "06:00:00", "12:00", True),
    ],
)
def test_quiet_hours(start, end, now, allowed):
    cfg = config(**{CONF_QUIET_START: start, CONF_QUIET_END: end})
    assert GatePolicy().quiet_hours_ok(50, local(now), cfg) is allowed


def test_quiet_hours_need_both_ends():
    cfg = config(**{CONF_QUIET_START: "00:00:00"})
    assert GatePolicy().quiet_hours_ok(50, local("12:00"), cfg) is True


@pytest.mark.parametrize("state", [0, 100, 10, 60, 35])
def test_rest_positions_pass_quiet_hours(state):
    cfg = config(**{CONF_QUIET_START: "20:00:00", CONF_QUIET_END: "08:00:00"})
    assert GatePolicy().quiet_hours_ok(state, local("23:00"), cfg) is True


# --------------------------------------------------------------- move budget


def test_budget_allows_max_moves_per_rolling_hour():
    cfg = config(**{CONF_MAX_MOVES_HOUR: 2})
    gates = GatePolicy()
    assert gates.move_budget_ok(COVER, 50, NOW, cfg) is True
    gates.record_move(COVER, NOW - dt.timedelta(minutes=50), cfg)
    assert gates.move_budget_ok(COVER, 50, NOW, cfg) is True
    gates.record_move(COVER, NOW - dt.timedelta(minutes=10), cfg)
    assert gates.move_budget_ok(COVER, 50, NOW, cfg) is False  # 2 of 2 used
    # Ten minutes later the older move is more than an hour old.
    assert gates.move_budget_ok(COVER, 50, NOW + dt.timedelta(minutes=10), cfg)


def test_budget_is_per_cover():
    cfg = config(**{CONF_MAX_MOVES_HOUR: 1})
    gates = GatePolicy()
    gates.record_move(COVER, NOW, cfg)
    assert gates.move_budget_ok(COVER, 50, NOW, cfg) is False
    assert gates.move_budget_ok("cover.other", 50, NOW, cfg) is True


@pytest.mark.parametrize("state", [0, 100, 10, 60, 35])
def test_rest_positions_pass_an_exhausted_budget(state):
    cfg = config(**{CONF_MAX_MOVES_HOUR: 1})
    gates = GatePolicy()
    gates.record_move(COVER, NOW, cfg)
    assert gates.move_budget_ok(COVER, state, NOW, cfg) is True


def test_no_budget_records_nothing():
    gates = GatePolicy()
    gates.record_move(COVER, NOW, config())
    assert gates.move_budget_ok(COVER, 50, NOW, config(**{CONF_MAX_MOVES_HOUR: 1}))


# ----------------------------------------------------------------- gate order


class FakeCover:
    """Answers for one cover; records which questions were asked."""

    def __init__(self, **answers) -> None:
        self.answers = {
            "is_manual": False,
            "awaiting_target": False,
            "in_time_window": True,
            "position": 20,
            "last_command": None,
            **answers,
        }
        self.asked: list[str] = []

    def _ask(self, name):
        def answer():
            self.asked.append(name)
            return self.answers[name]

        return answer

    def facts(self) -> CoverFacts:
        return CoverFacts(**{name: self._ask(name) for name in self.answers})


# Each row fixes one more gate than the row before it.
BLOCKED = {
    "is_manual": True,
    "awaiting_target": True,
    "in_time_window": False,
    "position": 51,  # one away from the target 50: below min_change
    "last_command": NOW - dt.timedelta(minutes=1),
}
ORDER = [
    ("is_manual", "manual_override"),
    ("awaiting_target", "awaiting_target"),
    ("in_time_window", "outside_time_window"),
    ("position", "position_delta"),
    ("last_command", "time_throttle"),
]


def gate_config(**options) -> ShadeConfig:
    return config(
        **{
            CONF_DELTA_POSITION: 5,
            CONF_DELTA_TIME: 2,
            CONF_QUIET_START: "11:00:00",
            CONF_QUIET_END: "13:00:00",
            CONF_MAX_MOVES_HOUR: 1,
            **options,
        }
    )


@pytest.mark.parametrize("fixed", range(len(ORDER) + 1))
def test_gate_precedence(fixed):
    """The first failing gate in the documented order names the block."""
    answers = {name: BLOCKED[name] for name, _ in ORDER[fixed:]}
    cover = FakeCover(**answers)
    gate = GatePolicy().first_blocking_gate(
        COVER, 50, gate_config(), cover.facts(), NOW, NOON
    )
    expected = ORDER[fixed][1] if fixed < len(ORDER) else "quiet_hours"
    assert gate == expected


def test_budget_is_the_last_gate():
    cfg = gate_config(**{CONF_QUIET_START: None})
    gates = GatePolicy()
    gates.record_move(COVER, NOW, cfg)
    cover = FakeCover()
    assert gates.first_blocking_gate(COVER, 50, cfg, cover.facts(), NOW, NOON) == (
        "move_budget"
    )


def test_open_gates_allow_the_move():
    cover = FakeCover()
    gate = GatePolicy().first_blocking_gate(
        COVER, 50, gate_config(**{CONF_QUIET_START: None}), cover.facts(), NOW, NOON
    )
    assert gate is None


def test_manual_cover_is_not_asked_anything_else():
    cover = FakeCover(is_manual=True)
    GatePolicy().first_blocking_gate(COVER, 50, gate_config(), cover.facts(), NOW, NOON)
    assert cover.asked == ["is_manual"]


def test_time_throttle_lets_rest_positions_through():
    cover = FakeCover(last_command=NOW - dt.timedelta(minutes=1), position=50)
    cfg = gate_config(**{CONF_QUIET_START: None, CONF_MAX_MOVES_HOUR: None})
    gate = GatePolicy().first_blocking_gate(COVER, 100, cfg, cover.facts(), NOW, NOON)
    assert gate is None
