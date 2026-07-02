"""Characterization: coordinator service-call gates and next-event prediction.

Builds a REAL AdaptiveDataUpdateCoordinator via object.__new__ (skipping
__init__, which needs a live HA config entry) and sets only the attributes
the methods under test read. This pins today's gating quirks:

- check_position_delta's snap-position bypass (sunset/default/0/100)
- the "00:00 end time means tomorrow midnight" rule
- naive-local vs UTC time handling in the timing window
- _compute_next_event's event ordering and predicted positions
"""

from __future__ import annotations

import datetime as dt
import difflib
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from freezegun import freeze_time

from custom_components.adaptive_cover.calculation import AdaptiveVerticalCover
from custom_components.adaptive_cover.config_context_adapter import (
    ConfigContextAdapter,
)
from custom_components.adaptive_cover.coordinator import (
    AdaptiveCoverManager,
    AdaptiveDataUpdateCoordinator,
)

from .golden_lib import GOLDENS_DIR, SLC, FakeSunData

UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"
NEXT_EVENTS_GOLDEN = GOLDENS_DIR / "next_events.txt"


class FakeStates:
    """hass.states stand-in supporting attributes and last_updated."""

    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None, last_updated=None):
        self._states[entity_id] = SimpleNamespace(
            state=state,
            attributes=attributes or {},
            last_updated=last_updated,
        )

    def get(self, entity_id):
        return self._states.get(entity_id)


def _make_logger():
    logger = ConfigContextAdapter(logging.getLogger("gating"))
    logger.set_config_name("Gating")
    return logger


def make_coordinator(**overrides):
    """Real coordinator instance without HA; only gate-relevant attrs set."""
    coord = object.__new__(AdaptiveDataUpdateCoordinator)
    coord.logger = _make_logger()
    coord.hass = SimpleNamespace(
        states=FakeStates(),
        config=SimpleNamespace(time_zone="America/Denver"),
    )
    coord._cover_type = "cover_blind"
    coord.min_change = 5
    coord.time_threshold = 2
    coord.start_time = None
    coord.start_time_entity = None
    coord.end_time = None
    coord.end_time_entity = None
    coord._start_time = None
    coord._track_end_time = False
    coord.manager = AdaptiveCoverManager({"minutes": 15}, coord.logger)
    coord.config_entry = SimpleNamespace(options={})
    for key, value in overrides.items():
        setattr(coord, key, value)
    return coord


OPTIONS = {"sunset_position": 0, "default_percentage": 60}


class TestCheckPositionDelta:
    """Pin check_position_delta including the snap-position bypass."""

    def _coord_with_cover_at(self, position):
        coord = make_coordinator()
        coord.hass.states.set(
            "cover.a", "open", attributes={"current_position": position}
        )
        return coord

    def test_below_threshold_blocks(self):
        coord = self._coord_with_cover_at(50)
        assert coord.check_position_delta("cover.a", 52, OPTIONS) is False

    def test_at_threshold_allows(self):
        coord = self._coord_with_cover_at(50)
        assert coord.check_position_delta("cover.a", 55, OPTIONS) is True

    @pytest.mark.parametrize("snap_state", [0, 100, 60])
    def test_snap_positions_bypass_threshold(self, snap_state):
        """sunset_pos (0), 100, and default (60) bypass the delta gate.

        QUIRK: even a 1% move is allowed when the target is one of these.
        """
        coord = self._coord_with_cover_at(snap_state + 1)
        assert coord.check_position_delta("cover.a", snap_state, OPTIONS) is True

    def test_unknown_position_allows(self):
        coord = make_coordinator()
        assert coord.check_position_delta("cover.missing", 50, OPTIONS) is True

    def test_tilt_uses_tilt_attribute(self):
        coord = make_coordinator(_cover_type="cover_tilt")
        coord.hass.states.set(
            "cover.a",
            "open",
            attributes={"current_position": 0, "current_tilt_position": 50},
        )
        assert coord.check_position_delta("cover.a", 52, OPTIONS) is False


class TestCheckTimeDelta:
    """Pin check_time_delta throttling."""

    def test_recent_update_blocks(self):
        coord = make_coordinator()
        coord.hass.states.set(
            "cover.a",
            "open",
            last_updated=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
        )
        assert coord.check_time_delta("cover.a") is False

    def test_stale_update_allows(self):
        coord = make_coordinator()
        coord.hass.states.set(
            "cover.a",
            "open",
            last_updated=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=3),
        )
        assert coord.check_time_delta("cover.a") is True

    def test_missing_entity_allows(self):
        coord = make_coordinator()
        assert coord.check_time_delta("cover.missing") is True


class TestCheckPosition:
    """Pin check_position (should-we-bother-calling-the-service check)."""

    def test_different_position_true(self):
        coord = make_coordinator()
        coord.hass.states.set("cover.a", "open", attributes={"current_position": 40})
        assert coord.check_position("cover.a", 50) is True

    def test_same_position_false(self):
        coord = make_coordinator()
        coord.hass.states.set("cover.a", "open", attributes={"current_position": 50})
        assert coord.check_position("cover.a", 50) is False

    def test_unknown_position_false(self):
        """QUIRK: unknown current position means NO service call is made."""
        coord = make_coordinator()
        assert coord.check_position("cover.missing", 50) is False


class TestTimingWindow:
    """Pin the start/end timing window incl. the 00:00 end-time rule."""

    @freeze_time("2026-03-20 10:00:00")
    def test_midnight_end_time_means_tomorrow(self):
        coord = make_coordinator(end_time="00:00:00")
        assert coord._end_time == dt.datetime(2026, 3, 21, 0, 0)
        assert coord.before_end_time is True

    @freeze_time("2026-03-20 10:00:00")
    def test_explicit_end_time_same_day(self):
        coord = make_coordinator(end_time="09:00:00")
        assert coord._end_time == dt.datetime(2026, 3, 20, 9, 0)
        assert coord.before_end_time is False

    @freeze_time("2026-03-20 10:00:00")
    def test_after_start_time_uses_naive_local(self):
        coord = make_coordinator(start_time="09:30:00")
        assert coord.after_start_time is True
        coord2 = make_coordinator(start_time="10:30:00")
        assert coord2.after_start_time is False

    @freeze_time("2026-03-20 10:00:00")
    def test_start_time_entity_wins_over_start_time(self):
        coord = make_coordinator(
            start_time="06:00:00", start_time_entity="input_datetime.start"
        )
        coord.hass.states.set("input_datetime.start", "11:00:00")
        assert coord.after_start_time is False

    @freeze_time("2026-03-20 10:00:00")
    def test_check_adaptive_time_combines_gates(self):
        coord = make_coordinator(start_time="07:30:00", end_time="00:00:00")
        assert coord.check_adaptive_time is True
        late = make_coordinator(start_time="07:30:00", end_time="09:00:00")
        assert late.check_adaptive_time is False


def _render_next_events():
    """Render _compute_next_event output at three times of day."""
    lines = ["# _compute_next_event characterization: 2026-03-20, SLC south window"]
    date = pd.Timestamp("2026-03-20")
    sun_data = FakeSunData(SLC["lat"], SLC["lon"], SLC["tz"], date)
    with patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=sun_data,
    ):
        cover = AdaptiveVerticalCover(
            hass=SimpleNamespace(states=FakeStates()),
            logger=_make_logger(),
            sol_azi=180.0,
            sol_elev=45.0,
            sunset_pos=0,
            sunset_off=0,
            sunrise_off=0,
            timezone=SLC["tz"],
            fov_left=90,
            fov_right=90,
            win_azi=180,
            h_def=60,
            max_pos=None,
            min_pos=None,
            max_pos_bool=False,
            min_pos_bool=False,
            blind_spot_left=None,
            blind_spot_right=None,
            blind_spot_elevation=None,
            blind_spot_on=False,
            min_elevation=None,
            max_elevation=None,
            distance=0.5,
            h_win=2.1,
        )
        start, end = cover.solar_times()

        for frozen in ["2026-03-20 04:00:00", "2026-03-20 15:00:00",
                       "2026-03-20 22:00:00"]:
            local = pd.Timestamp(frozen, tz=SLC["tz"])
            with freeze_time(local.to_pydatetime()):
                coord = make_coordinator()
                event = coord._compute_next_event(cover, start, end)
            if event is None:
                lines.append(f"now={frozen} -> None")
            else:
                name, when, pos = event
                lines.append(
                    f"now={frozen} -> name={name!r} time={when.isoformat()} pos={pos}"
                )
    return "\n".join(lines) + "\n"


def test_next_event_golden():
    rendered = _render_next_events()
    if UPDATE:
        GOLDENS_DIR.mkdir(exist_ok=True)
        NEXT_EVENTS_GOLDEN.write_text(rendered)
        pytest.skip("updated next_events.txt")
    assert NEXT_EVENTS_GOLDEN.exists(), "run with UPDATE_GOLDENS=1 first"
    expected = NEXT_EVENTS_GOLDEN.read_text()
    if rendered != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), rendered.splitlines(), lineterm="", n=2
            )
        )
        pytest.fail(f"next-event behavior changed:\n{diff}")
