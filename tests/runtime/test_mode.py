"""Mode (auto / hold / off) and requested holds, without hass (P5 flip)."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import pytest

from custom_components.adaptive_cover.runtime.mode import (
    MODE_OPTIONS,
    Mode,
    ModeControl,
    Restored,
    current_mode,
    restored_mode,
)
from custom_components.adaptive_cover.runtime.override_tracker import OverrideTracker
from custom_components.adaptive_cover.runtime.shade_config import ControlState

COVER = "cover.office"
T0 = dt.datetime(2026, 6, 21, 18, 0, tzinfo=dt.UTC)
LOG = logging.getLogger("test")
HOUR = dt.timedelta(hours=1)


class FakeClock:
    def __init__(self) -> None:
        self.current = T0

    def utcnow(self) -> dt.datetime:
        return self.current

    def now(self, tz: dt.tzinfo) -> dt.datetime:
        return self.current.astimezone(tz)


@dataclass
class Report:
    last_updated: dt.datetime


@dataclass
class FakeWindow:
    """What ModeControl reads and calls; records the commands."""

    controls: ControlState = field(default_factory=lambda: ControlState(control=True))
    clock: FakeClock = field(default_factory=FakeClock)
    target: int = 40
    covers: list[str] = field(default_factory=lambda: [COVER])
    sent: list[tuple[str, int, str]] = field(default_factory=list)
    forced: list[str] = field(default_factory=list)
    refreshes: int = 0

    def __post_init__(self) -> None:
        self.manager = OverrideTracker({"hours": 2}, LOG, None, self.clock)
        self.manager.add_covers(self.covers)

    @property
    def entities(self) -> list[str]:
        return self.covers

    @property
    def state(self) -> int:
        return self.target

    async def async_force_apply(self, source="user", reason=None) -> None:
        self.forced.append(source)
        for entity in self.covers:
            if not self.manager.is_cover_manual(entity):
                self.sent.append((entity, self.target, source))

    async def async_set_position(self, entity, state, source="adaptive", reason=None):
        self.sent.append((entity, state, source))

    async def async_set_manual_position(
        self, entity, state, source="integration", reason=None
    ) -> bool:
        self.sent.append((entity, state, source))
        return True

    async def async_refresh(self) -> None:
        self.refreshes += 1


# ------------------------------------------------------------ pure rules


def test_options():
    assert MODE_OPTIONS == ["auto", "hold", "off"]


@pytest.mark.parametrize(
    ("control", "held", "mode"),
    [
        (None, False, None),
        (None, True, None),
        (False, False, Mode.OFF),
        (False, True, Mode.OFF),
        (True, False, Mode.AUTO),
        (True, True, Mode.HOLD),
    ],
)
def test_current_mode(control, held, mode):
    assert current_mode(control, held) is mode


@pytest.mark.parametrize(
    ("own", "until", "restored"),
    [
        # The Mode's own state.
        ("auto", None, Restored(Mode.AUTO)),
        ("off", None, Restored(Mode.OFF)),
        ("hold", T0 + HOUR, Restored(Mode.HOLD, T0 + HOUR)),
        # A hold that ended while down, or without an end, is auto.
        ("hold", T0 - HOUR, Restored(Mode.AUTO)),
        ("hold", T0, Restored(Mode.AUTO)),
        ("hold", None, Restored(Mode.AUTO)),
        # Nothing to go on (a new window, or a state that is no Mode): auto.
        # Since v2.1 there is no fallback to the Toggle Control switch and
        # the select's options from before the P5 flip are not read.
        (None, None, Restored(Mode.AUTO)),
        ("unknown", None, Restored(Mode.AUTO)),
        ("unavailable", None, Restored(Mode.AUTO)),
        ("Manual", None, Restored(Mode.AUTO)),
    ],
)
def test_restored_mode(own, until, restored):
    assert restored_mode(own, until, T0) == restored


# ------------------------------------------------------------ requested holds


async def test_a_requested_hold_ends_at_its_own_end():
    window = FakeWindow()
    window.manager.hold(COVER, T0 + 4 * HOUR, T0)
    assert window.manager.expires_at(COVER) == T0 + 4 * HOUR

    window.clock.current = T0 + 3 * HOUR  # past the 2 h override duration
    await window.manager.reset_if_needed()
    assert window.manager.is_cover_manual(COVER)

    window.clock.current = T0 + 4 * HOUR
    await window.manager.reset_if_needed()
    assert not window.manager.is_cover_manual(COVER)
    assert window.manager.expires_at(COVER) is None


def test_a_detected_override_ends_after_the_override_duration():
    manager = FakeWindow().manager
    manager.mark_manual_control(COVER)
    manager.set_last_updated(COVER, Report(T0), allow_reset=False)
    assert manager.expires_at(COVER) == T0 + 2 * HOUR


def test_rollover_and_detection_off_end_only_detected_overrides():
    window = FakeWindow(covers=[COVER, "cover.den"])
    manager = window.manager
    manager.hold(COVER, T0 + 4 * HOUR, T0)
    manager.mark_manual_control("cover.den")
    manager.set_last_updated("cover.den", Report(T0), allow_reset=False)

    manager.reset_detected()
    assert manager.manual_controlled == [COVER]

    manager.reset_all()
    assert manager.manual_controlled == []


def test_a_move_during_a_hold_restarts_the_clock_only_when_allowed():
    manager = FakeWindow().manager
    manager.hold(COVER, T0 + 3 * HOUR, T0)
    manager.set_last_updated(COVER, Report(T0 + 2 * HOUR), allow_reset=False)
    assert manager.expires_at(COVER) == T0 + 3 * HOUR
    manager.set_last_updated(COVER, Report(T0 + 2 * HOUR), allow_reset=True)
    assert manager.expires_at(COVER) == T0 + 4 * HOUR


# ------------------------------------------------------------ ModeControl


async def test_hold_uses_its_duration_else_the_override_duration():
    window = FakeWindow()
    modes = ModeControl(window, LOG)
    await modes.hold(dt.timedelta(hours=4))
    assert modes.mode is Mode.HOLD
    assert modes.until == T0 + 4 * HOUR
    assert window.sent == []

    await modes.hold()
    assert modes.until == T0 + 2 * HOUR


async def test_hold_with_a_position_commands_it_first():
    window = FakeWindow(controls=ControlState(control=False))
    modes = ModeControl(window, LOG)
    await modes.hold(HOUR, position=0)
    assert window.sent == [(COVER, 0, "hold")]
    assert window.controls.control is True
    assert modes.mode is Mode.HOLD


async def test_auto_ends_a_hold_and_sends_the_target():
    window = FakeWindow()
    modes = ModeControl(window, LOG)
    await modes.hold()
    await modes.select(Mode.AUTO)
    assert modes.mode is Mode.AUTO
    assert window.sent == [(COVER, 40, "adaptive")]
    assert window.forced == []


async def test_auto_from_off_is_control_on_and_a_forced_apply():
    window = FakeWindow(controls=ControlState(control=False))
    modes = ModeControl(window, LOG)
    await modes.select(Mode.AUTO)
    assert modes.mode is Mode.AUTO
    assert window.forced == ["control_enabled"]


async def test_off_ends_every_hold():
    window = FakeWindow()
    modes = ModeControl(window, LOG)
    await modes.hold()
    await modes.select(Mode.OFF)
    assert modes.mode is Mode.OFF
    assert not window.manager.binary_cover_manual
    assert modes.until is None


async def test_enable_keeps_holds():
    window = FakeWindow()
    modes = ModeControl(window, LOG)
    await modes.hold()
    await modes.enable()
    assert modes.mode is Mode.HOLD
    assert window.sent == []


async def test_restore_relatches_a_hold_only_where_it_was_lost():
    window = FakeWindow(covers=[COVER, "cover.den"], controls=ControlState())
    window.manager.mark_manual_control("cover.den")
    window.manager.set_last_updated("cover.den", Report(T0), allow_reset=False)
    modes = ModeControl(window, LOG)

    await modes.restore(Restored(Mode.HOLD, T0 + HOUR))

    assert modes.mode is Mode.HOLD
    assert window.manager.expires_at(COVER) == T0 + HOUR
    assert window.manager.expires_at("cover.den") == T0 + 2 * HOUR  # kept
    assert window.refreshes == 1


async def test_restore_off_and_auto_set_control_only():
    window = FakeWindow(controls=ControlState())
    modes = ModeControl(window, LOG)
    await modes.restore(Restored(Mode.OFF))
    assert modes.mode is Mode.OFF
    await modes.restore(Restored(Mode.AUTO))
    assert modes.mode is Mode.AUTO
    assert window.sent == []
