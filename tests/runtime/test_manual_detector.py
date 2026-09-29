"""ManualDetector: when a cover report is a person moving the shade (P4)."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

import pytest

from custom_components.adaptive_cover.const import (
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_THRESHOLD,
)
from custom_components.adaptive_cover.runtime.command_tracker import CommandTracker
from custom_components.adaptive_cover.runtime.manual_detector import ManualDetector
from custom_components.adaptive_cover.runtime.override_tracker import OverrideTracker
from custom_components.adaptive_cover.runtime.shade_config import (
    ControlState,
    ShadeConfig,
)

COVER = "cover.office"
T0 = dt.datetime(2026, 6, 21, 18, 0, tzinfo=dt.UTC)
ON = ControlState(control=True, manual=True)


class FakeClock:
    def utcnow(self) -> dt.datetime:
        return T0


@dataclass
class Report:
    state: str
    position: int | None = None
    last_updated: dt.datetime = T0
    attributes: dict[str, Any] = field(default_factory=dict)


def config(**options) -> ShadeConfig:
    return ShadeConfig.from_options(options)


class Harness:
    def __init__(self) -> None:
        log = logging.getLogger("test")
        self.overrides = OverrideTracker({"minutes": 30}, log, None, FakeClock())
        self.overrides.add_covers([COVER])

        async def no_poll(entity: str) -> None:
            raise AssertionError("no poll expected")

        self.commands = CommandTracker(FakeClock(), lambda *_: lambda: None, no_poll)
        self.detector = ManualDetector(self.overrides, self.commands)

    def motion(self, report="opening", controls=ON, ignore=False, **options):
        return self.detector.motion_started(
            COVER, Report(report), controls, config(**options), ignore
        )

    def landed(self, position, our_state=50, controls=ON, **options):
        return self.detector.landed(
            COVER, Report("open"), position, our_state, controls, config(**options)
        )


@pytest.fixture
def h() -> Harness:
    return Harness()


# ------------------------------------------------------------ motion start


@pytest.mark.parametrize("report", ["opening", "closing"])
def test_foreign_motion_latches_at_once(h, report):
    assert h.motion(report) is True
    assert h.overrides.is_cover_manual(COVER)
    assert h.overrides.manual_control_time[COVER] == T0


def test_a_settled_report_is_not_a_motion_start(h):
    assert h.motion("open") is False


def test_motion_during_our_travel_is_ours(h):
    h.commands.start(COVER, 80)
    assert h.motion() is False


@pytest.mark.parametrize(
    "controls",
    [
        ControlState(control=True, manual=None),  # switches not restored yet
        ControlState(control=True, manual=False),
        ControlState(control=False, manual=True),
        ControlState(control=None, manual=True),
    ],
)
def test_motion_needs_detection_and_control_on(h, controls):
    assert h.motion(controls=controls) is False


def test_ignored_intermediate_states_never_latch(h):
    assert h.motion(ignore=True) is False


def test_unknown_cover_and_repeat_latches(h):
    assert (
        h.detector.motion_started(
            "cover.unknown", Report("opening"), ON, config(), False
        )
        is False
    )
    assert h.motion() is True
    assert h.motion() is False  # already manual: nothing new


def test_motion_latch_restarts_the_clock_only_when_allowed(h):
    h.overrides.set_last_updated(COVER, Report("open", last_updated=T0), False)
    later = T0 + dt.timedelta(minutes=5)
    h.detector.motion_started(
        COVER,
        Report("opening", last_updated=later),
        ON,
        config(**{CONF_MANUAL_OVERRIDE_RESET: True}),
        False,
    )
    assert h.overrides.manual_control_time[COVER] == later


# ------------------------------------------------------- redirect in travel


@pytest.mark.parametrize(
    ("status", "latched"),
    [
        ("foreign_landing", True),
        ("arrived", False),
        ("expired", False),
        ("in_travel", False),
        (None, False),
    ],
)
def test_only_a_foreign_landing_latches_in_travel(h, status, latched):
    result = h.detector.redirected(COVER, status, Report("open"), ON, config())
    assert result is latched
    assert h.overrides.is_cover_manual(COVER) is latched


def test_redirect_needs_detection_on(h):
    off = ControlState(control=True, manual=False)
    assert (
        h.detector.redirected(COVER, "foreign_landing", Report("open"), off, config())
        is False
    )


# ---------------------------------------------------------------- landings


@pytest.mark.parametrize(
    ("position", "latched"),
    [(50, False), (51, True), (0, True), (None, False)],
)
def test_landing_away_from_our_position_latches(h, position, latched):
    assert h.landed(position) is latched
    assert h.overrides.is_cover_manual(COVER) is latched


@pytest.mark.parametrize(
    ("position", "latched"), [(46, False), (54, False), (45, True), (55, True)]
)
def test_landing_threshold(h, position, latched):
    assert h.landed(position, **{CONF_MANUAL_THRESHOLD: 5}) is latched


def test_landing_on_our_target_is_ours_even_if_the_state_drifted(h):
    h.commands.start(COVER, 80)
    h.commands.release(COVER)  # the travel window is over; the target stays
    assert h.landed(79, our_state=70) is False


def test_landing_during_our_travel_is_not_manual(h):
    h.commands.start(COVER, 80)
    assert h.landed(20, our_state=70) is False


def test_landing_needs_detection_and_control_on(h):
    assert h.landed(10, controls=ControlState(control=True, manual=None)) is False


def test_landing_on_an_unknown_cover(h):
    assert (
        h.detector.landed("cover.unknown", Report("open"), 10, 50, ON, config())
        is False
    )


def test_a_cover_already_manual_is_not_newly_latched(h):
    h.overrides.mark_manual_control(COVER)
    assert h.landed(10) is False
