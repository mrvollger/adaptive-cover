"""Fetch sun data."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from astral import LocationInfo
from astral.location import Location
from homeassistant.core import HomeAssistant


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

    def __init__(self, timezone, hass: HomeAssistant) -> None:  # noqa: D107
        self.hass = hass
        location, elevation = _astral_location(hass)
        self.location = location  # astral.location.Location
        self.elevation = elevation
        self.timezone = timezone
        # Per-local-date snapshot cache: times + azimuth/elevation computed
        # together so they can never pair data from different days.
        self._snapshot_date: date | None = None
        self._times: pd.DatetimeIndex | None = None
        self._solar_azimuth: list | None = None
        self._solar_elevation: list | None = None

    def _today_local(self) -> date:
        """Today in the HA-configured timezone.

        date.today() reads the PROCESS timezone, which on HA OS is UTC:
        late in the evening it already reports tomorrow, so sunset()
        silently returns tomorrow's sunset and the engine's night branch
        never engages (regression 2026-07-03).
        """
        return datetime.now(ZoneInfo(str(self.timezone))).date()

    def _snapshot(self) -> tuple[pd.DatetimeIndex, list, list]:
        """Return (times, azimuth, elevation) computed from one date read.

        Historically each property regenerated the times index on access,
        so around midnight (or a DST shift) the azimuth/elevation lists
        could be paired with a different day's index. Compute everything
        once per local date and serve it from the same snapshot.
        """
        today = self._today_local()
        if self._snapshot_date != today:
            start_date = today
            end_date = start_date + timedelta(days=1)
            times = pd.date_range(
                start=start_date,
                end=end_date,
                freq="5min",
                tz=self.timezone,
                name="time",
            )
            self._times = times
            self._solar_azimuth = [
                self.location.solar_azimuth(ts, self.elevation) for ts in times
            ]
            self._solar_elevation = [
                self.location.solar_elevation(ts, self.elevation) for ts in times
            ]
            self._snapshot_date = today
        return self._times, self._solar_azimuth, self._solar_elevation

    @property
    def times(self) -> pd.DatetimeIndex:
        """Define time interval."""
        return self._snapshot()[0]

    @property
    def solar_azimuth(self) -> list:
        """Create list with solar azimuth data per 5 minutes."""
        return self._snapshot()[1]

    @property
    def solar_elevation(self) -> list:
        """Create list with solar elevation data per 5 minutes."""
        return self._snapshot()[2]

    def sunset(self) -> datetime:
        """Fetch today's (local date) sunset time."""
        return self.location.sunset(self._today_local(), local=False)

    def sunrise(self) -> datetime:
        """Fetch today's (local date) sunrise time."""
        return self.location.sunrise(self._today_local(), local=False)
