"""Fetch sun data.

The solar table for one local day is built with the standard library (P2,
ADR 0005; pandas until then). Its values are unchanged; its types are now
plain Python: ``times`` is a tuple of tz-aware datetimes in the configured
time zone, ``solar_azimuth`` and ``solar_elevation`` are lists of floats
(contract change C2).
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.location import Location
from homeassistant.core import HomeAssistant

from .runtime.clock import SYSTEM_CLOCK, Clock

# One solar-table point every STEP of real (UTC) time.
STEP = timedelta(minutes=5)


def day_steps(day: date, tz: tzinfo, step: timedelta = STEP) -> tuple[datetime, ...]:
    """Return the points of one local day, both midnights included.

    The points are ``step`` apart in real time, stepped in UTC and shown in
    ``tz``: 289 on a 24-hour day, 277 on the 23-hour day DST starts, 301 on
    the 25-hour day it ends. They are the instants
    ``pandas.date_range(day, day + 1 day, freq=step, tz=tz)`` produced
    before P2. (pandas raised when a zone skips or repeats midnight; this
    takes the first reading of such a midnight.)
    """
    start = datetime.combine(day, time(), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), tzinfo=tz).astimezone(UTC)
    count = (end - start) // step
    return tuple((start + i * step).astimezone(tz) for i in range(count + 1))


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def nearest_index(times: Sequence[datetime], when: datetime) -> int:
    """Return the index of the point nearest ``when``; -1 if there are none.

    ``times`` must be sorted and tz-aware, ``when`` tz-aware. A tie goes to
    the later point and a time outside the table to its nearest end: the
    result of pandas ``DatetimeIndex.get_indexer([when], method="nearest")``,
    which this replaces. Everything is compared in UTC, because Python
    compares two datetimes that share a tzinfo by wall time, which is
    wrong across a DST fold.
    """
    if not times:
        return -1
    target = _utc(when)
    i = bisect_left(times, target, key=_utc)
    if i == 0:
        return 0
    if i == len(times):
        return len(times) - 1
    before = target - _utc(times[i - 1])
    after = _utc(times[i]) - target
    return i - 1 if before < after else i


@dataclass(frozen=True, slots=True)
class SolarDay:
    """One local day of solar positions, a point every ``STEP`` (C2).

    Replaces the pandas table (DatetimeIndex plus two lists) with the same
    values: ``times`` from :func:`day_steps`, ``azimuth[i]`` and
    ``elevation[i]`` for ``times[i]``.
    """

    date: date
    times: tuple[datetime, ...]
    azimuth: list[float]
    elevation: list[float]


def _astral_location(hass: HomeAssistant) -> tuple[Location, float]:
    """Build an astral Location from the HA core configuration.

    Replaces the deprecated ``homeassistant.helpers.sun.get_astral_location``
    (which logged a deprecation warning on every call) with the same
    construction that helper performed internally.
    """
    info = LocationInfo(
        "",
        "",
        str(hass.config.time_zone),
        hass.config.latitude,
        hass.config.longitude,
    )
    return Location(info), hass.config.elevation


class SunData:
    """Access local sun data."""

    def __init__(
        self, timezone, hass: HomeAssistant, clock: Clock = SYSTEM_CLOCK
    ) -> None:
        """Build the provider; ``clock`` decides which local day is today."""
        self.hass = hass
        self._clock = clock
        location, elevation = _astral_location(hass)
        self.location = location  # astral.location.Location
        self.elevation = elevation
        self.timezone = timezone
        # Per-local-date snapshot cache: times + azimuth/elevation computed
        # together so they can never pair data from different days.
        self._day: SolarDay | None = None

    def _today_local(self) -> date:
        """Today in the HA-configured timezone.

        date.today() reads the PROCESS timezone, which on HA OS is UTC:
        late in the evening it already reports tomorrow, so sunset()
        silently returns tomorrow's sunset and the engine's night branch
        never engages (regression 2026-07-03).
        """
        return self._clock.now(ZoneInfo(str(self.timezone))).date()

    def solar_day(self) -> SolarDay:
        """Return today's table, computed once per local date.

        Historically each property regenerated the times index on access,
        so around midnight (or a DST shift) the azimuth/elevation lists
        could be paired with a different day's index. Compute everything
        once per local date and serve it from the same snapshot.
        """
        today = self._today_local()
        if self._day is None or self._day.date != today:
            times = day_steps(today, ZoneInfo(str(self.timezone)))
            self._day = SolarDay(
                date=today,
                times=times,
                azimuth=[
                    self.location.solar_azimuth(ts, self.elevation) for ts in times
                ],
                elevation=[
                    self.location.solar_elevation(ts, self.elevation) for ts in times
                ],
            )
        return self._day

    @property
    def times(self) -> tuple[datetime, ...]:
        """Today's 5-minute points: tz-aware datetimes in the configured zone."""
        return self.solar_day().times

    @property
    def solar_azimuth(self) -> list[float]:
        """Create list with solar azimuth data per 5 minutes."""
        return self.solar_day().azimuth

    @property
    def solar_elevation(self) -> list[float]:
        """Create list with solar elevation data per 5 minutes."""
        return self.solar_day().elevation

    def sunset(self) -> datetime:
        """Fetch today's (local date) sunset time."""
        return self.location.sunset(self._today_local(), local=False)

    def sunrise(self) -> datetime:
        """Fetch today's (local date) sunrise time."""
        return self.location.sunrise(self._today_local(), local=False)
