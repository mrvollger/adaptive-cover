"""Manual-move detection: when a cover report is a person (refactor P4).

A cover report during our travel window is an echo of our command
(CommandTracker decides that). Outside it, or when the motion or the
landing contradicts our command, the report is a person moving the shade,
and the cover is latched under manual control (OverrideTracker). This
module holds those rules; it has no ``hass``. The coordinator records the
move log entry when a rule latches.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from .command_tracker import MOTION, CommandTracker
from .override_tracker import OverrideTracker
from .shade_config import ControlState, ShadeConfig

_LOGGER = logging.getLogger(__name__)


class CoverState(Protocol):
    """The parts of a cover state report the detector reads."""

    @property
    def state(self) -> str:
        """``open``, ``closed``, ``opening``, ``closing``, ..."""
        ...

    @property
    def attributes(self) -> Mapping[str, Any]:
        """The state attributes (``current_position``, ...)."""
        ...

    @property
    def last_updated(self) -> Any:
        """When the state was written (tz-aware datetime)."""
        ...


class ManualDetector:
    """Decide when a cover report is a manual move, and latch it."""

    def __init__(
        self,
        overrides: OverrideTracker,
        commands: CommandTracker,
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Latch into ``overrides``; read the travel state from ``commands``."""
        self.overrides = overrides
        self.commands = commands
        self.logger = logger

    def motion_started(
        self,
        entity: str,
        new_state: CoverState,
        controls: ControlState,
        config: ShadeConfig,
        ignore_intermediate: bool,
    ) -> bool:
        """Latch manual when a foreign motion STARTS; return True if latched.

        Foreign movement starting (opening/closing we didn't command) is a
        human act the moment the motor spins. These shades report position
        only at journey end, so waiting for the landing report leaves a
        1-3 minute window where the cover reads as auto-controlled while a
        person is actively moving it.
        """
        if (
            new_state.state in MOTION
            and not ignore_intermediate
            and not self.commands.wait_for_target.get(entity)
            and controls.manual
            and controls.control
            and entity in self.overrides.covers
            and not self.overrides.is_cover_manual(entity)
        ):
            self.logger.debug(
                "Foreign %s movement started for %s: latching manual immediately",
                new_state.state,
                entity,
            )
            self.overrides.mark_manual_control(entity)
            self.overrides.set_last_updated(entity, new_state, config.manual_reset)
            return True
        return False

    def redirected(
        self,
        entity: str,
        status: str | None,
        new_state: CoverState,
        controls: ControlState,
        config: ShadeConfig,
    ) -> bool:
        """Latch manual on a foreign landing in the travel window; True if latched.

        ``status`` is CommandTracker.classify_report's answer. Someone
        stopped or redirected the cover mid-travel; without this latch the
        move was swallowed as a motor echo and the next sun tick reverted
        it.
        """
        if (
            status == "foreign_landing"
            and controls.manual
            and controls.control
            and entity in self.overrides.covers
            and not self.overrides.is_cover_manual(entity)
        ):
            self.overrides.mark_manual_control(entity)
            self.overrides.set_last_updated(entity, new_state, config.manual_reset)
            return True
        return False

    def landed(
        self,
        entity: str,
        new_state: CoverState,
        position: int | None,
        our_state: int,
        controls: ControlState,
        config: ShadeConfig,
    ) -> bool:
        """Check a report outside the travel window; True if it newly latched.

        A landing on OUR commanded target is never manual, even when the
        computed state drifted while the shade travelled.
        """
        was_manual = self.overrides.is_cover_manual(entity)
        if controls.manual and controls.control:
            if self.commands.is_own_landing(entity, position):
                self.logger.debug(
                    "State change for %s matches our commanded target; not manual",
                    entity,
                )
            else:
                self.check_landing(
                    entity,
                    new_state,
                    position,
                    our_state,
                    config.manual_reset,
                    config.manual_threshold,
                )
        return not was_manual and self.overrides.is_cover_manual(entity)

    def check_landing(
        self,
        entity_id: str,
        new_state: CoverState,
        new_position: int | None,
        our_state: int,
        allow_reset: bool,
        manual_threshold: float | None,
    ) -> None:
        """Latch manual when the cover sits away from our position."""
        if entity_id not in self.overrides.covers:
            return
        if self.commands.wait_for_target.get(entity_id):
            return

        if new_position is None:
            # A report with no position (device glitch, mid-transition echo)
            # is not evidence of a human move; latching on it produced
            # nonsense override records in the field.
            self.logger.debug(
                "State change for %s carries no position; not latching manual",
                entity_id,
            )
            return
        if new_position != our_state:
            if (
                manual_threshold is not None
                and abs(our_state - new_position) < manual_threshold
            ):
                self.logger.debug(
                    "Position change is less than threshold %s for %s",
                    manual_threshold,
                    entity_id,
                )
                return
            self.logger.debug(
                "Manual change detected for %s. Our state: %s, new state: %s",
                entity_id,
                our_state,
                new_position,
            )
            self.logger.debug(
                "Set manual control for %s, for at least %s seconds, reset_allowed: %s",
                entity_id,
                self.overrides.reset_duration.total_seconds(),
                allow_reset,
            )
            self.overrides.mark_manual_control(entity_id)
            self.overrides.set_last_updated(entity_id, new_state, allow_reset)
