"""Fetch sun data."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_location


class SunData:
    """Access local sun data."""

    def __init__(self, timezone, hass: HomeAssistant) -> None:  # noqa: D107
        self.hass = hass
        location, elevation = get_astral_location(self.hass)
        self.location = location  # astral.location.Location
        self.elevation = elevation
        self.timezone = timezone

    def _today_local(self) -> date:
        """Today in the HA-configured timezone.

        date.today() reads the PROCESS timezone, which on HA OS is UTC:
        late in the evening it already reports tomorrow, so sunset()
        silently returns tomorrow's sunset and the engine's night branch
        never engages (regression 2026-07-03).
        """
        return datetime.now(ZoneInfo(str(self.timezone))).date()

    @property
    def times(self) -> pd.DatetimeIndex:
        """Define time interval."""
        start_date = self._today_local()
        end_date = start_date + timedelta(days=1)

        times = pd.date_range(
            start=start_date, end=end_date, freq="5min", tz=self.timezone, name="time"
        )
        return times

    @property
    def solar_azimuth(self) -> list:
        """Create list with solar azimuth data per 5 minutes."""
        index = 0
        azi_list = []
        for _i in self.times:
            azi_list.append(
                self.location.solar_azimuth(self.times[index], self.elevation)
            )
            index += 1
        return azi_list

    @property
    def solar_elevation(self) -> list:
        """Create list with solar elevation data per 5 minutes."""
        index = 0
        ele_list = []
        for _i in self.times:
            ele_list.append(
                self.location.solar_elevation(self.times[index], self.elevation)
            )
            index += 1
        return ele_list

    def sunset(self) -> datetime:
        """Fetch today's (local date) sunset time."""
        return self.location.sunset(self._today_local(), local=False)

    def sunrise(self) -> datetime:
        """Fetch today's (local date) sunrise time."""
        return self.location.sunrise(self._today_local(), local=False)

    # def df_today(self)-> pd.DataFrame:
    #     """Create dataframe with azimuth and elevation data"""
    #     df_today = pd.DataFrame({"azimuth":self.solar_azimuth, "elevation":self.solar_elevation})
    #     df_today = df_today.set_index(self.times)
    #     return df_today
