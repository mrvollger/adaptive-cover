"""What the window tells the user about its decisions (refactor P4).

The Position sensor and its siblings explain the shade: why it sits where
it does (intent, decision trace, state reason), what comes next (the next
change event, today's forecast), what changed last, and what moved each
cover (the move log). This module keeps that state and builds those
values. It has no ``hass``: the coordinator passes the time, the cover
adapter and the numbers it already has.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol

from ..const import (
    CONF_AZIMUTH,
    CONF_BLIND_SPOT_ELEVATION,
    CONF_DEFAULT_HEIGHT,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
)
from ..engine.models import Decision
from ..sun import nearest_index

_LOGGER = logging.getLogger(__name__)

type NextEvent = tuple[str, dt.datetime, float | None]
"""(name, when, position); the position is None for an override expiry."""
type SunTable = tuple[Sequence[dt.datetime], Sequence[float], Sequence[float]]
"""Today's solar table: times, azimuths, elevations."""


class SunLocation(Protocol):
    """Where the sun is computed (an astral Location)."""

    def sunrise(self, date: dt.date, local: bool = True) -> dt.datetime:
        """Sunrise on ``date``."""
        ...

    def sunset(self, date: dt.date, local: bool = True) -> dt.datetime:
        """Sunset on ``date``."""
        ...


class SolarDay(Protocol):
    """Today's sun (the adapter's SunData)."""

    @property
    def times(self) -> Sequence[dt.datetime]:
        """The table's points (tz-aware)."""
        ...

    @property
    def solar_azimuth(self) -> Sequence[float]:
        """Azimuth at each point."""
        ...

    @property
    def solar_elevation(self) -> Sequence[float]:
        """Elevation at each point."""
        ...

    @property
    def location(self) -> SunLocation:
        """The location, for tomorrow's sunrise and sunset."""
        ...

    def sunrise(self) -> dt.datetime:
        """Today's sunrise (UTC)."""
        ...

    def sunset(self) -> dt.datetime:
        """Today's sunset (UTC)."""
        ...


class ExplainedCover(Protocol):
    """The cover adapter fields the explanations read."""

    @property
    def sun_data(self) -> SolarDay:
        """Today's sun."""
        ...

    @property
    def h_def(self) -> float:
        """Default position."""
        ...

    @property
    def sunset_pos(self) -> float:
        """Sunset position."""
        ...

    @property
    def sunset_off(self) -> float:
        """Sunset offset (minutes)."""
        ...

    @property
    def sunrise_off(self) -> float:
        """Sunrise offset (minutes)."""
        ...

    def calculate_percentage_at(self, azi: float, elev: float) -> float:
        """Position for a sun at (azimuth, elevation), geometry only."""
        ...


class Climate(Protocol):
    """A climate snapshot (only its inputs matter here)."""

    def to_inputs(self) -> object:
        """Return the engine inputs this snapshot stands for."""
        ...


class Explainer:
    """Explanations of one window: next change, forecast, last change, moves."""

    MOVE_LOG_LIMIT = 10

    def __init__(
        self, logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER
    ) -> None:
        """Start with nothing explained yet."""
        self.logger = logger
        self.forecast: list[dict[str, Any]] | None = None
        """Today's change-points, transformed like the commands."""
        self._forecast_key: str | None = "___unset___"
        self.move_log: dict[str, list[dict[str, Any]]] = {}
        """Per cover, the last moves with their source and reason."""
        self._previous_state: float | None = None
        self.last_change: dict[str, Any] = {
            "old_position": None,
            "new_position": None,
            "time": None,
            "reason": None,
        }
        """The last change of the computed position or of a cover."""

    # ---------------------------------------------------------- next change

    def _predict_position_at_time(
        self,
        cover_data: ExplainedCover,
        target_time: dt.datetime,
        sun_table: SunTable | None,
    ) -> float:
        """Predict cover position at a specific future time using sun data."""
        if sun_table is not None:
            times, azimuths, elevations = sun_table
        else:
            sun_data = cover_data.sun_data
            times = sun_data.times
            azimuths = sun_data.solar_azimuth
            elevations = sun_data.solar_elevation
        # Nearest table point to the tz-aware target, compared as instants
        # (the table is in local time, the target usually UTC).
        idx = nearest_index(times, target_time)
        if idx < 0 or idx >= len(times):
            return int(cover_data.h_def)
        return cover_data.calculate_percentage_at(azimuths[idx], elevations[idx])

    @staticmethod
    def _make_utc(time: dt.datetime) -> dt.datetime:
        """Ensure a datetime is UTC-aware."""
        if time.tzinfo is None:
            return time.replace(tzinfo=dt.UTC)
        return time

    def next_event(
        self,
        cover_data: ExplainedCover,
        *,
        now: dt.datetime,
        tomorrow: dt.date,
        start: dt.datetime | None,
        end: dt.datetime | None,
        sun_table: SunTable | None,
        configured_end: dt.datetime | None,
        end_position: Any,
        override_expiries: Iterable[dt.datetime],
    ) -> NextEvent | None:
        """Find the next significant cover state change event.

        Today's sunrise/sunset come from the sun data (configured local
        date); once passed, tomorrow's are asked for by the LOCAL date too
        (``tomorrow``). The UTC date rolls over mid-evening in western
        timezones (18:00 in Denver), which named the sunrise two local days
        out. ``configured_end`` is the tz-aware end-of-day close when that
        close is on, and ``end_position`` the position it sends.
        """
        location = cover_data.sun_data.location
        events: list[NextEvent] = []

        # Sun enters FOV
        if start is not None:
            start_utc = self._make_utc(start)
            if start_utc > now:
                predicted_pos = self._predict_position_at_time(
                    cover_data, start_utc, sun_table
                )
                events.append(("Sun enters window", start_utc, predicted_pos))

        # Sun leaves FOV
        if end is not None:
            end_utc = self._make_utc(end)
            if end_utc > now:
                events.append(("Sun leaves window", end_utc, int(cover_data.h_def)))

        # Sunset + offset (today, then tomorrow if past)
        try:
            sunset_raw = cover_data.sun_data.sunset()
            sunset_utc = self._make_utc(sunset_raw)
            sunset_time = sunset_utc + dt.timedelta(minutes=cover_data.sunset_off)
            if sunset_time <= now:
                sunset_raw = location.sunset(tomorrow, local=False)
                sunset_utc = self._make_utc(sunset_raw)
                sunset_time = sunset_utc + dt.timedelta(minutes=cover_data.sunset_off)
            if sunset_time > now:
                events.append(
                    ("Sunset + offset", sunset_time, int(cover_data.sunset_pos))
                )
        except Exception:  # noqa: BLE001
            self.logger.debug("Could not compute sunset event", exc_info=True)

        # Sunrise + offset (today, then tomorrow if past)
        try:
            sunrise_raw = cover_data.sun_data.sunrise()
            sunrise_utc = self._make_utc(sunrise_raw)
            sunrise_time = sunrise_utc + dt.timedelta(minutes=cover_data.sunrise_off)
            if sunrise_time <= now:
                sunrise_raw = location.sunrise(tomorrow, local=False)
                sunrise_utc = self._make_utc(sunrise_raw)
                sunrise_time = sunrise_utc + dt.timedelta(
                    minutes=cover_data.sunrise_off
                )
            if sunrise_time > now:
                events.append(("Sunrise + offset", sunrise_time, int(cover_data.h_def)))
        except Exception:  # noqa: BLE001
            self.logger.debug("Could not compute sunrise event", exc_info=True)

        # Configured end time
        if configured_end is not None and configured_end > now:
            events.append(("Configured end time", configured_end, end_position))

        # Manual override expires
        for expire_time in override_expiries:
            if expire_time > now:
                events.append(
                    (
                        "Manual override expires",
                        expire_time,
                        None,  # position will be the current computed state
                    )
                )

        if not events:
            return None

        events.sort(key=lambda e: e[1])
        return events[0]

    # -------------------------------------------------------------- forecast

    async def refresh_forecast(
        self,
        stale: bool,
        climate: Climate | None,
        build: Callable[[], Awaitable[list[dict[str, Any]]]],
        transform: Callable[[float], float],
    ) -> None:
        """Rebuild today's forecast when the day rolled over or the climate changed.

        The climate snapshot is baked into the schedule, so a change of its
        inputs rebuilds it too. ``build`` runs the engine over the day (in
        an executor); ``transform`` is the commands' output transform.
        """
        forecast_key = None
        if climate is not None:
            try:
                forecast_key = repr(climate.to_inputs())
            except Exception:  # noqa: BLE001
                forecast_key = None
        if stale or forecast_key != self._forecast_key:
            try:
                raw_forecast = await build()
                self.forecast = [
                    {**entry, "position": int(transform(entry["position"]))}
                    for entry in raw_forecast
                ]
            except Exception:  # noqa: BLE001
                self.logger.debug("Forecast build failed", exc_info=True)
                self.forecast = None
            self._forecast_key = forecast_key

    # ----------------------------------------------------------- last change

    def note_state(self, state: float, reason: str, now: dt.datetime) -> None:
        """Track last state change (computed position changes)."""
        if self._previous_state is not None and self._previous_state != state:
            self.last_change = {
                "old_position": self._previous_state,
                "new_position": state,
                "time": now,
                "reason": reason,
            }
        self._previous_state = state

    def note_cover_report(
        self,
        new_pos: float | None,
        old_pos: float | None,
        state: float,
        reason: str,
        now: dt.datetime,
    ) -> None:
        """Track a cover state change (manual or integration-initiated)."""
        if new_pos is not None:
            self.last_change = {
                "old_position": old_pos if old_pos is not None else state,
                "new_position": new_pos,
                "time": now,
                "reason": reason,
            }

    # --------------------------------------------------------------- moves

    def record(
        self,
        entity: str,
        position: Any,
        source: str,
        reason: str | None,
        now: dt.datetime,
    ) -> dict[str, Any]:
        """Append to the per-cover move log; return the entry.

        Answers "what moved this cover and why": source is adaptive /
        startup / end_time / control_enabled / all_covers / hold / manual, with
        the driving intent as reason where known.
        """
        entry: dict[str, Any] = {
            "time": now.isoformat(timespec="seconds"),
            "position": position,
            "source": source,
            "reason": reason,
        }
        log = self.move_log.setdefault(entity, [])
        log.append(entry)
        del log[: -self.MOVE_LOG_LIMIT]
        return entry

    def format_last_move(self, entity: str, tz: dt.tzinfo) -> str | None:
        """Compact 'HH:MM -> 37% (source: reason)' line for attributes.

        HH:MM is in ``tz``, HA's configured time zone (not the process's).
        """
        log = self.move_log.get(entity)
        if not log:
            return None
        entry = log[-1]
        when = dt.datetime.fromisoformat(entry["time"]).astimezone(tz)
        line = f"{when.strftime('%H:%M')} -> {entry['position']}% ({entry['source']}"
        if entry.get("reason"):
            line += f": {entry['reason']}"
        return line + ")"

    # ----------------------------------------------------------- attributes

    def attributes(
        self,
        options: Mapping[str, Any],
        decision: Decision | None,
        gate_blocks: Mapping[str, str | None],
        entities: Iterable[str],
        sun: dict[str, Any],
        tz: dt.tzinfo,
    ) -> dict[str, Any]:
        """Build the Position sensor's explanation attributes.

        ``tz`` is HA's configured time zone, for the last-move times.
        """
        return {
            "default": options.get(CONF_DEFAULT_HEIGHT),
            "sunset_default": options.get(CONF_SUNSET_POS),
            "sunset_offset": options.get(CONF_SUNSET_OFFSET),
            "azimuth_window": options.get(CONF_AZIMUTH),
            "field_of_view": [
                options.get(CONF_FOV_LEFT),
                options.get(CONF_FOV_RIGHT),
            ],
            "blind_spot": options.get(CONF_BLIND_SPOT_ELEVATION),
            "intent": str(decision.intent) if decision else None,
            "decision_trace": list(decision.trace) if decision else None,
            "forecast_today": self.forecast,
            "move_blocked_by": {
                entity: gate for entity, gate in gate_blocks.items() if gate
            },
            "last_moves": {
                entity: line
                for entity in entities
                if (line := self.format_last_move(entity, tz)) is not None
            },
            "sun": sun,
        }
