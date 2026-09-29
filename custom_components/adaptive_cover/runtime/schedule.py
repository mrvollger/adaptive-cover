"""The daily control window: start and end time (refactor P4).

Automatic control runs from the start time to the end time each day. Each
one comes from a fixed time option or from a time entity, and the entity
wins. Times are naive wall times in Home Assistant's configured zone: the
coordinator passes ``now`` on that basis, and a reader for entity states.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Any, cast

from ..helpers import get_datetime_from_str
from .shade_config import ShadeConfig

type StateReader = Callable[[str], str | None]
"""Return an entity's state; None when it is missing, unknown or unavailable."""

_LOGGER = logging.getLogger(__name__)


class Schedule:
    """Start and end time of automatic control for one window."""

    def __init__(
        self,
        read_state: StateReader,
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Read time entities through ``read_state``; log to ``logger``."""
        self._read_state = read_state
        self.logger = logger
        self.last_start: dt.datetime | None = None
        """The start time last read from the start entity (for the error log)."""

    def end_time(self, config: ShadeConfig, today: dt.date) -> dt.datetime | None:
        """Return today's end time, or None when there is none.

        A fixed end time of 00:00 means the coming midnight (the end of
        today), not the midnight that started it.
        """
        time = None
        if config.end_time_entity is not None:
            time = get_datetime_from_str(
                self._read_state(config.end_time_entity),
                default_date=today,
            )
        elif config.end_time is not None:
            time = get_datetime_from_str(config.end_time, default_date=today)
            if time.time() == dt.time(0, 0):
                time = time + dt.timedelta(days=1)
        return time

    def after_start(self, config: ShadeConfig, now: dt.datetime) -> bool:
        """Return True once today's start time has passed (no start: True)."""
        if config.start_time_entity is not None:
            # An unavailable start entity reads as None, and comparing with
            # None raises TypeError (known, not fixed in this move); the
            # cast only tells the type checker what the code assumes.
            time = cast(
                dt.datetime,
                get_datetime_from_str(
                    self._read_state(config.start_time_entity),
                    default_date=now.date(),
                ),
            )
            self.logger.debug(
                "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time
            )
            self.last_start = time
            return now >= time
        if config.start_time is not None:
            time = get_datetime_from_str(config.start_time, default_date=now.date())

            self.logger.debug(
                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time
            )
            # Not recorded in last_start: the coordinator's line here was a
            # no-op expression (a P4 ledgered fix, not this move).
            return now >= time
        return True

    def before_end(self, config: ShadeConfig, now: dt.datetime) -> bool:
        """Return True until today's end time (no end time: True)."""
        end = self.end_time(config, now.date())
        if end is not None:
            self.logger.debug(
                "End time: %s, now: %s, now < time: %s", end, now, now < end
            )
            return now < end
        return True

    def in_window(self, config: ShadeConfig, now: dt.datetime) -> bool:
        """Return True while automatic control may move the shade.

        The end is checked first: after it, the start is not read at all.
        """
        end = self.end_time(config, now.date())
        if self.last_start and end and self.last_start > end:
            self.logger.error("Start time is after end time")
        return self.before_end(config, now) and self.after_start(config, now)
