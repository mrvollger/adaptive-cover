"""OverrideTracker: the manual-override clock of each cover (P4)."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import pytest

from custom_components.adaptive_cover.runtime.override_tracker import OverrideTracker

COVER = "cover.office"
T0 = dt.datetime(2026, 6, 21, 18, 0, tzinfo=dt.UTC)
LOG = logging.getLogger("test")


class FakeClock:
    def __init__(self) -> None:
        self.current = T0

    def utcnow(self) -> dt.datetime:
        return self.current


@dataclass
class Report:
    last_updated: dt.datetime


def tracker(minutes: float = 30, store: dict | None = None) -> OverrideTracker:
    return OverrideTracker({"minutes": minutes}, LOG, store, FakeClock())


def test_nothing_is_manual_at_first():
    overrides = tracker()
    assert overrides.is_cover_manual(COVER) is False
    assert overrides.binary_cover_manual is False
    assert overrides.manual_controlled == []


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        ({"minutes": 45}, dt.timedelta(minutes=45)),
        ({"hours": 1, "minutes": 30, "seconds": 0}, dt.timedelta(minutes=90)),
        ({"seconds": 90}, dt.timedelta(seconds=90)),
    ],
)
def test_set_duration(duration, expected):
    overrides = tracker()
    overrides.set_duration(duration)
    assert overrides.reset_duration == expected


def test_latch_starts_the_clock():
    overrides = tracker()
    overrides.mark_manual_control(COVER)
    overrides.set_last_updated(COVER, Report(T0), allow_reset=False)
    assert overrides.is_cover_manual(COVER) is True
    assert overrides.manual_control_time == {COVER: T0}
    assert overrides.manual_controlled == [COVER]
    assert overrides.binary_cover_manual is True


@pytest.mark.parametrize(("allow_reset", "restarted"), [(False, False), (True, True)])
def test_later_moves_restart_the_clock_only_when_allowed(allow_reset, restarted):
    overrides = tracker()
    overrides.set_last_updated(COVER, Report(T0), allow_reset)
    later = T0 + dt.timedelta(minutes=10)
    overrides.set_last_updated(COVER, Report(later), allow_reset)
    assert overrides.manual_control_time[COVER] == (later if restarted else T0)
    assert overrides.reset_allowed[COVER] is allow_reset


@pytest.mark.parametrize(("minutes", "expired"), [(29, False), (30, False), (31, True)])
async def test_override_expires_after_the_duration(minutes, expired):
    overrides = tracker(minutes=30)
    overrides.mark_manual_control(COVER)
    overrides.set_last_updated(COVER, Report(T0), allow_reset=False)
    overrides.clock.current = T0 + dt.timedelta(minutes=minutes)
    await overrides.reset_if_needed()
    assert overrides.is_cover_manual(COVER) is not expired


def test_reset_and_reset_all():
    overrides = tracker()
    for cover in (COVER, "cover.other"):
        overrides.mark_manual_control(cover)
        overrides.set_last_updated(cover, Report(T0), allow_reset=True)
    overrides.reset(COVER)
    assert overrides.manual_controlled == ["cover.other"]
    assert COVER not in overrides.manual_control_time
    assert COVER not in overrides.reset_allowed
    overrides.reset_all()
    assert overrides.manual_controlled == []
    assert overrides.manual_control_time == {}


def test_state_survives_a_rebuild_on_the_same_store():
    """An options reload rebuilds the tracker over the same hass.data dict."""
    store: dict = {}
    first = tracker(store=store)
    first.mark_manual_control(COVER)
    first.set_last_updated(COVER, Report(T0), allow_reset=False)
    second = tracker(store=store)
    assert second.is_cover_manual(COVER) is True
    assert second.manual_control_time[COVER] == T0


def test_add_covers():
    overrides = tracker()
    overrides.add_covers([COVER])
    overrides.add_covers([COVER, "cover.other"])
    assert overrides.covers == {COVER, "cover.other"}
