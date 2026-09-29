"""The gates between a computed position and a cover command (refactor P4).

Every automatic move passes these gates in a fixed order, and the first
one that blocks names itself in the Position sensor's ``move_blocked_by``
attribute. Snap positions (fully open or closed, the default, sunset and
privacy positions) are the moves always worth making, so the rate gates
let them through.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..helpers import get_datetime_from_str
from .shade_config import ShadeConfig

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoverFacts:
    """What the gates ask about one cover, each read only when needed.

    The gates ask in their order and stop at the first block: a cover
    under manual override never has its travel latch, time window or
    position read.
    """

    is_manual: Callable[[], bool]
    """The cover is under manual override."""
    awaiting_target: Callable[[], bool]
    """Our last command to the cover is still travelling."""
    in_time_window: Callable[[], bool]
    """The schedule allows automatic moves now."""
    position: Callable[[], int | None]
    """The cover's reported position (None when unknown)."""
    last_command: Callable[[], dt.datetime | None]
    """When we last commanded the cover (None when never)."""


class GatePolicy:
    """Decide whether one automatic move may go out now.

    Holds the per-cover move history for the hourly budget; everything
    else (options, time, what the cover reports) comes in as arguments.
    """

    def __init__(
        self, logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER
    ) -> None:
        """Start with an empty move history."""
        self.logger = logger
        self._move_history: dict[str, list[dt.datetime]] = {}

    def first_blocking_gate(
        self,
        entity: str,
        state: int,
        config: ShadeConfig,
        cover: CoverFacts,
        now: dt.datetime,
        now_local: dt.datetime,
    ) -> str | None:
        """Return the first gate that blocks this move, or None if allowed.

        Precedence (also the documented order): manual override > time
        window > position delta > time throttle > quiet hours > move budget.
        Exposed per cover in the 'move_blocked_by' attribute so 'why didn't
        it move?' is answerable from the UI. ``now`` is aware UTC,
        ``now_local`` naive wall time in HA's configured zone.
        """
        if cover.is_manual():
            return "manual_override"
        if cover.awaiting_target():
            # One command in flight is enough; never stack re-sends.
            return "awaiting_target"
        if not cover.in_time_window():
            return "outside_time_window"
        if not self.position_delta_ok(entity, cover.position(), state, config):
            return "position_delta"
        if not self.time_delta_ok(
            entity, cover.last_command(), now, config
        ) and not self.is_snap_position(state, config):
            # Snap positions (sunset/default/privacy/0/100) bypass the time
            # throttle like they bypass every other rate gate: the evening
            # close must not be swallowed because the shade moved recently.
            return "time_throttle"
        if not self.quiet_hours_ok(state, now_local, config):
            return "quiet_hours"
        if not self.move_budget_ok(entity, state, now, config):
            return "move_budget"
        return None

    def position_delta_ok(
        self, entity: str, position: int | None, state: int, config: ShadeConfig
    ) -> bool:
        """Check cover positions to reduce calls.

        A move smaller than ``min_change`` waits, except to a snap position
        (the same list the other rate gates use). An unknown position allows
        the move.
        """
        if position is not None:
            condition = abs(position - state) >= config.min_change
            self.logger.debug(
                "Entity: %s,  position: %s, state: %s, delta position: %s, min_change: %s, condition: %s",
                entity,
                position,
                state,
                abs(position - state),
                config.min_change,
                condition,
            )
            if self.is_snap_position(state, config):
                condition = True
            return condition
        return True

    def time_delta_ok(
        self,
        entity: str,
        last_sent: dt.datetime | None,
        now: dt.datetime,
        config: ShadeConfig,
    ) -> bool:
        """Throttle: allow only when enough time passed since OUR last command.

        Throttling on the entity's last_updated starved covers whose
        devices chatter (link-quality updates, forced polls bump
        last_updated without any movement). Only our own commands count.
        """
        if last_sent is not None:
            condition = now - last_sent >= dt.timedelta(minutes=config.time_threshold)
            self.logger.debug(
                "Entity: %s, time since our last command: %s, threshold: %s, "
                "condition: %s",
                entity,
                now - last_sent,
                config.time_threshold,
                condition,
            )
            return condition
        return True

    def is_snap_position(self, state: int, config: ShadeConfig) -> bool:
        """Positions that always deserve a move (endpoints, rest positions)."""
        return state in [
            config.sunset_pos,
            config.default_height,
            config.privacy_position,
            0,
            100,
        ]

    def quiet_hours_ok(
        self, state: int, now_local: dt.datetime, config: ShadeConfig
    ) -> bool:
        """Block tracking moves during the configured quiet window.

        Snap positions (fully open/closed, default, sunset, privacy) are
        allowed through: arriving at a rest position is the one move worth
        making at night.
        """
        if not config.quiet_start or not config.quiet_end:
            return True
        if self.is_snap_position(state, config):
            return True
        now = now_local.time()
        start = get_datetime_from_str(config.quiet_start).time()
        end = get_datetime_from_str(config.quiet_end).time()
        if start <= end:
            quiet = start <= now < end
        else:  # window crosses midnight
            quiet = now >= start or now < end
        if quiet:
            self.logger.debug("Quiet hours (%s-%s): skipping tracking move", start, end)
        return not quiet

    def move_budget_ok(
        self, entity: str, state: int, now: dt.datetime, config: ShadeConfig
    ) -> bool:
        """Cap tracking moves per entity per hour (motor noise / wear).

        Snap positions bypass the budget so day-phase transitions always
        happen; only incremental tracking moves are rationed.
        """
        if not config.max_moves_hour:
            return True
        if self.is_snap_position(state, config):
            return True
        history = [
            t
            for t in self._move_history.get(entity, [])
            if now - t < dt.timedelta(hours=1)
        ]
        self._move_history[entity] = history
        if len(history) >= config.max_moves_hour:
            self.logger.debug(
                "Move budget (%s/h) exhausted for %s: skipping tracking move",
                config.max_moves_hour,
                entity,
            )
            return False
        return True

    def record_move(self, entity: str, now: dt.datetime, config: ShadeConfig) -> None:
        """Count one command to ``entity`` against its hourly budget."""
        if config.max_moves_hour:
            self._move_history.setdefault(entity, []).append(now)
