"""The clock seam: the one module that reads the current time (P2, ADR 0005).

Everything outside the pure engine asks a :class:`Clock` for "now" instead
of calling ``datetime.now()`` or ``dt_util.utcnow()`` itself;
``tests/engine/test_purity.py`` enforces this with an AST scan. The
coordinator owns one clock (``AdaptiveDataUpdateCoordinator.clock``) and
hands it to the cover adapters and sun tables it builds.

Production uses :data:`SYSTEM_CLOCK`, Home Assistant's ``dt_util``. The
test suite's ``freezer`` fixture freezes that too, so most tests need no
fake; a test that wants one assigns ``coordinator.default_clock`` (the
seam, like ``calculation.sun_data_factory``) or passes ``clock=`` to the
coordinator.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from homeassistant.util import dt as dt_util


class Clock(Protocol):
    """A source of the current time."""

    def utcnow(self) -> dt.datetime:
        """Return the current time, tz-aware in UTC."""
        ...

    def now(self, tz: dt.tzinfo) -> dt.datetime:
        """Return the current time, tz-aware in ``tz``."""
        ...


class HassClock:
    """The real clock: Home Assistant's ``dt_util``.

    The functions are looked up on every call, never bound at import:
    the test harness patches ``dt_util.utcnow`` so ``freezer`` can freeze
    it.
    """

    def utcnow(self) -> dt.datetime:
        """Return ``dt_util.utcnow()``."""
        return dt_util.utcnow()

    def now(self, tz: dt.tzinfo) -> dt.datetime:
        """Return ``dt_util.now(tz)``."""
        return dt_util.now(tz)


SYSTEM_CLOCK: Clock = HassClock()
