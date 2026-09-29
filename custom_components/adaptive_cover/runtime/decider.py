"""The output decision: which position goes out, and how it maps (refactor P4).

The engine computes a basic position and, in climate mode, a climate
position. The Decider picks the active one and runs the output transforms
every command goes through: interpolation onto the cover's own range, or
inversion for covers that count the other way. (The min/max clamp is the
engine's, in ``evaluate``.) It has no ``hass``.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from ..engine.numeric import interp
from .shade_config import ShadeConfig

_LOGGER = logging.getLogger(__name__)


def inverse_state(state: float) -> float:
    """Inverse state."""
    return 100 - state


class Decider:
    """Pick the active position and apply the output transforms."""

    def __init__(
        self,
        use_interpolation: bool,
        inverse: bool,
        logger: logging.Logger | logging.LoggerAdapter[Any] = _LOGGER,
    ) -> None:
        """Take the setup-time transform options (interp, inverse_state)."""
        self.use_interpolation = use_interpolation
        self.inverse = inverse
        self.logger = logger

    def position(
        self,
        default_state: float,
        climate_state: float | None,
        use_climate: bool,
        config: ShadeConfig,
    ) -> float:
        """Handle the output of the state based on mode.

        ``climate_state`` is set on every refresh of a climate-mode entry,
        the only kind whose climate switch can be on.
        """
        self.logger.debug(
            "Basic position: %s; Climate position: %s; Using climate position? %s",
            default_state,
            climate_state,
            use_climate,
        )
        if use_climate:
            state = cast(float, climate_state)
        else:
            state = default_state

        state = self.transform(state, config)
        self.logger.debug("Final position to use: %s", state)
        return state

    def transform(self, state: float, config: ShadeConfig) -> float:
        """Apply interpolation / inversion output transforms."""
        if self.use_interpolation:
            self.logger.debug("Interpolating position: %s", state)
            state = self.interpolate(state, config)

        if self.inverse and self.use_interpolation:
            self.logger.info(
                "Inverse state is not supported with interpolation, you can inverse the state by arranging the list from high to low"
            )

        if self.inverse and not self.use_interpolation:
            state = inverse_state(state)
            self.logger.debug("Inversed position: %s", state)
        return state

    def interpolate(self, state: float, config: ShadeConfig) -> float:
        """Interpolate states."""
        normal_range: list[float] = [0, 100]
        new_range: list[float] = []
        if config.interp_start and config.interp_end:
            new_range = [config.interp_start, config.interp_end]
        if config.interp_list and config.interp_list_new:
            normal_range = list(map(int, config.interp_list))
            new_range = list(map(int, config.interp_list_new))
        if new_range:
            state = interp(state, normal_range, new_range)
            if state == new_range[0]:
                state = 0
            if state == new_range[-1]:
                state = 100
        return state
