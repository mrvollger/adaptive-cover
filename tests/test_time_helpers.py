"""The stdlib time helpers that replaced pandas and pytz (P2, ADR 0005).

- ``sun.day_steps``: the day table's points (was ``pandas.date_range``).
- ``sun.nearest_index``: the nearest point (was ``DatetimeIndex.get_indexer``
  with ``method="nearest"``).
- ``coordinator.localize_standard``: a naive local time made aware (was
  pytz ``localize``).

The contract-level pins (277/289/301 points, same astral values) are in
``tests/test_regression_fixes.py``; these tests pin the helpers' edge cases.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from custom_components.adaptive_cover.coordinator import localize_standard
from custom_components.adaptive_cover.sun import day_steps, nearest_index

DENVER = ZoneInfo("America/Denver")
SYDNEY = ZoneInfo("Australia/Sydney")


@pytest.mark.parametrize(
    ("zone", "day", "points"),
    [
        (DENVER, dt.date(2026, 3, 8), 277),
        (DENVER, dt.date(2026, 11, 1), 301),
        (SYDNEY, dt.date(2026, 10, 4), 277),  # southern spring: DST starts
        (SYDNEY, dt.date(2026, 4, 5), 301),
        (ZoneInfo("UTC"), dt.date(2026, 6, 1), 289),
    ],
)
def test_day_steps_counts(zone, day, points):
    assert len(day_steps(day, zone)) == points


def test_day_steps_other_step_and_repeated_hour():
    quarter = day_steps(dt.date(2026, 11, 1), DENVER, dt.timedelta(minutes=15))
    assert len(quarter) == 25 * 4 + 1
    # The repeated 01:00 hour appears twice, first as MDT, then as MST.
    one_am = [ts for ts in quarter if (ts.hour, ts.minute) == (1, 0)]
    assert [ts.utcoffset() for ts in one_am] == [
        dt.timedelta(hours=-6),
        dt.timedelta(hours=-7),
    ]


def test_nearest_index_edges():
    times = day_steps(dt.date(2026, 3, 20), DENVER)
    first = times[0].astimezone(dt.UTC)
    assert nearest_index((), first) == -1
    assert nearest_index(times, first - dt.timedelta(hours=3)) == 0
    assert nearest_index(times, first + dt.timedelta(days=2)) == len(times) - 1
    assert nearest_index(times, times[10]) == 10
    assert nearest_index(times, first + dt.timedelta(minutes=52)) == 10
    # Exactly between two points: the later one, as pandas chose.
    assert nearest_index(times, first + dt.timedelta(minutes=52, seconds=30)) == 11
    assert nearest_index(times, first + dt.timedelta(minutes=52, seconds=29)) == 10


def test_nearest_index_across_the_repeated_hour():
    """01:30 MDT and 01:30 MST are an hour apart and must map to different
    points; comparing local datetimes that share a tzinfo would merge them."""
    times = day_steps(dt.date(2026, 11, 1), DENVER)
    mdt = dt.datetime(2026, 11, 1, 7, 30, tzinfo=dt.UTC)  # 01:30 MDT
    mst = dt.datetime(2026, 11, 1, 8, 30, tzinfo=dt.UTC)  # 01:30 MST
    i, j = nearest_index(times, mdt), nearest_index(times, mst)
    assert j - i == 12
    assert times[i].astimezone(dt.UTC) == mdt
    assert times[j].astimezone(dt.UTC) == mst
    # The same instants given as local times (fold 0 and fold 1).
    assert nearest_index(times, dt.datetime(2026, 11, 1, 1, 30, tzinfo=DENVER)) == i
    assert (
        nearest_index(times, dt.datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=DENVER))
        == j
    )


@pytest.mark.parametrize(
    ("naive", "offset_hours"),
    [
        (dt.datetime(2026, 3, 20, 20, 0), -6),  # ordinary evening, MDT
        (dt.datetime(2026, 12, 21, 20, 0), -7),  # ordinary evening, MST
        (dt.datetime(2026, 11, 1, 1, 30), -7),  # repeated: standard time
        (dt.datetime(2026, 3, 8, 2, 30), -7),  # skipped: offset before the jump
    ],
)
def test_localize_standard_is_pytz_is_dst_false(naive, offset_hours):
    aware = localize_standard(naive, DENVER)
    assert aware.replace(tzinfo=None) == naive
    assert aware.utcoffset() == dt.timedelta(hours=offset_hours)
