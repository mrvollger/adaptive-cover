"""A window's Mode: ``auto`` / ``hold`` / ``off`` (refactor P5 flip).

Mode is the one control a person uses for a window (plan, "Entity
surface"):

- ``auto``: the window follows the sun (and climate, where it is on).
- ``hold``: a manual override with an expiry. A detected manual move
  sets it for the resolved override duration; selecting it holds the
  covers where they are for that duration; ``adaptive_cover.hold`` holds
  for a given duration, optionally after commanding a position. When the
  hold ends the window is back in ``auto``.
- ``off``: no moves and no manual-move detection (the old "Manual" mode,
  Toggle Control off).

The Mode select is the source of truth and restores its own state. At
runtime the state lives in two parts the rest of the runtime already
reads: ``ControlState.control`` (False is ``off``) and the
:class:`OverrideTracker` (a held cover is ``hold``). :class:`ModeControl`
changes both; :func:`current_mode` reads them back.

Holds come in two kinds. A **detected** hold (a person moved the cover)
keeps the override tracker's clock rules: it ends the override duration
after its latch time, a later move restarts that clock when the window
allows it, and the day rollover and switching detection off end it. A
**requested** hold (selected, or the ``hold`` service) has a fixed end
(``OverrideTracker.hold_until``) and ends only then, or when the window
goes ``auto`` or ``off``.

No ``hass`` here: time comes from the window's clock.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol

from .clock import Clock
from .override_tracker import OverrideTracker
from .shade_config import ControlState

_LOGGER = logging.getLogger(__name__)


class Mode(StrEnum):
    """A window's Mode (the select's options, translation-keyed)."""

    AUTO = "auto"
    HOLD = "hold"
    OFF = "off"


MODE_OPTIONS: Final[list[str]] = [Mode.AUTO.value, Mode.HOLD.value, Mode.OFF.value]
"""The Mode select's options, in display order."""

HOLD_SOURCE: Final = "hold"
"""The move-log source of a position the ``hold`` service commands."""


def current_mode(control: bool | None, held: bool) -> Mode | None:
    """Return the Mode of a window (None: not restored yet).

    ``control`` is ``ControlState.control``; ``held`` says whether any of
    the window's covers is under a manual override.
    """
    if control is None:
        return None
    if not control:
        return Mode.OFF
    return Mode.HOLD if held else Mode.AUTO


@dataclass(frozen=True, slots=True)
class Restored:
    """The Mode a window starts with after a restart or reload."""

    mode: Mode
    until: dt.datetime | None = None
    """When a restored hold ends (None for ``auto`` and ``off``)."""


def restored_mode(
    own: str | None,
    own_until: dt.datetime | None,
    now: dt.datetime,
) -> Restored:
    """Return the Mode to restore.

    ``own`` and ``own_until`` are the Mode select's last state and its
    ``until`` attribute. A hold whose end passed while Home Assistant was
    down, or whose end is unknown, restores as ``auto``. Nothing to go on
    (a new window) is ``auto``.

    (Until v2.1 a select without a state of its own fell back to the
    Toggle Control switch's, or mapped its pre-flip options; every house
    that runs v2.1 ran v2.0.x, where the select stored its own state.)
    """
    if own in MODE_OPTIONS:
        mode = Mode(own)
        if mode is not Mode.HOLD:
            return Restored(mode)
        if own_until is not None and own_until > now:
            return Restored(Mode.HOLD, own_until)
    return Restored(Mode.AUTO)


class ModeWindow(Protocol):
    """What :class:`ModeControl` needs from a window (the coordinator)."""

    controls: ControlState
    manager: OverrideTracker
    clock: Clock

    @property
    def entities(self) -> list[str]:
        """The window's covers."""
        ...

    @property
    def state(self) -> int:
        """The window's current target position."""
        ...

    async def async_force_apply(
        self, source: str = "user", reason: str | None = None
    ) -> None:
        """Command the target position now, bypassing the rate gates."""
        ...

    async def async_set_position(
        self,
        entity: str,
        state: int,
        source: str = "adaptive",
        reason: str | None = None,
    ) -> None:
        """Command one cover to the target position."""
        ...

    async def async_set_manual_position(
        self,
        entity: str,
        state: int,
        source: str = "integration",
        reason: str | None = None,
    ) -> bool:
        """Command one cover to ``state``; False when undelivered."""
        ...

    async def async_refresh(self) -> None:
        """Run the update pipeline now."""
        ...


class ModeControl:
    """Change a window's Mode: the selects, the buttons, ``hold``."""

    def __init__(
        self,
        window: ModeWindow,
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Act on ``window``'s control state, overrides and covers."""
        self.window = window
        self.logger = logger

    @property
    def mode(self) -> Mode | None:
        """The window's Mode now (None: not restored yet)."""
        return current_mode(
            self.window.controls.control, self.window.manager.binary_cover_manual
        )

    @property
    def until(self) -> dt.datetime | None:
        """When the window's hold ends (the latest of its covers), or None."""
        manager = self.window.manager
        ends = [
            end
            for cover in self.window.entities
            if (end := manager.expires_at(cover)) is not None
        ]
        return max(ends, default=None)

    async def select(self, mode: Mode) -> None:
        """Apply a Mode picked on the select (or the house select)."""
        if mode is Mode.OFF:
            await self.off()
        elif mode is Mode.HOLD:
            await self.hold()
        else:
            await self.auto()

    async def off(self) -> None:
        """Stop moving and stop detecting; every hold ends."""
        self.window.controls.control = False
        self.window.manager.reset_all()
        await self.window.async_refresh()

    async def enable(self) -> None:
        """Turn automatic control on (``auto`` from ``off``).

        The target position goes out now, bypassing the rate gates, to
        every cover that is not held; holds are kept.
        """
        self.window.controls.control = True
        await self.window.async_force_apply(
            source="control_enabled", reason="adaptive control switched on"
        )
        await self.window.async_refresh()

    async def auto(self) -> None:
        """Return to ``auto``: from ``off`` control comes back on, a hold ends."""
        if self.window.controls.control is False:
            await self.enable()
            return
        self.window.controls.control = True
        await self.return_to_auto()
        await self.window.async_refresh()

    async def return_to_auto(self) -> None:
        """End every hold and send each held cover the target position.

        The press does not wait for the cover to land. Its travel is ours
        (the command tracker's travel window), so the landing is never read
        as a manual move.
        """
        window = self.window
        for entity in window.entities:
            if window.manager.is_cover_manual(entity):
                self.logger.debug("Returning %s to auto", entity)
                await window.async_set_position(entity, window.state)
                window.manager.reset(entity)
            else:
                self.logger.debug("%s is already in auto", entity)

    async def hold(
        self, duration: dt.timedelta | None = None, position: int | None = None
    ) -> None:
        """Hold every cover for ``duration`` (default: the override duration).

        With ``position``, each cover is then sent there (latched first, so
        no refresh in between walks it back; the travel is ours, never a
        manual move). A window that was ``off`` comes back on so the hold
        can end in ``auto``.
        """
        window = self.window
        now = window.clock.utcnow()
        length = duration if duration is not None else window.manager.reset_duration
        until = now + length
        window.controls.control = True
        for entity in window.entities:
            window.manager.hold(entity, until, now)
        self.logger.debug("Holding %s until %s", window.entities, until)
        if position is not None:
            for entity in window.entities:
                await window.async_set_manual_position(
                    entity, position, source=HOLD_SOURCE, reason="hold requested"
                )
        await window.async_refresh()

    async def restore(self, restored: Restored) -> None:
        """Start from a restored Mode (the select's ``async_added_to_hass``).

        A cover the override tracker already holds (an options reload keeps
        it) keeps its own clock; a restored hold is re-latched only on
        covers that lost it (a restart clears the tracker).
        """
        window = self.window
        window.controls.control = restored.mode is not Mode.OFF
        if restored.mode is Mode.HOLD and restored.until is not None:
            now = window.clock.utcnow()
            for entity in window.entities:
                if not window.manager.is_cover_manual(entity):
                    window.manager.hold(entity, restored.until, now)
        await window.async_refresh()
