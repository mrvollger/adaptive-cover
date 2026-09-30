"""The climate season, sticky by a hysteresis margin.

The season is which side of the heating and cooling thresholds the
temperature is on: winter below ``temp_low``, summer above ``temp_high``
(while the outside is warm enough, where an outside threshold is set),
intermediate in between. The plain rule flips the season whenever a
reading crosses a threshold, so a temperature hovering at one (a
thermostat holding 72 °F against a 72 °F threshold) moves the shades back
and forth with every reading.

``hysteresis`` (HA's temperature unit, >= 0) makes every season sticky by
that margin. Each threshold moves ``h`` away from the season the window
is in, so leaving it takes a reading ``h`` past the threshold:

| Previous season    | winter while   | summer while    |
|--------------------|----------------|-----------------|
| none (plain rule)  | t < low        | t > high        |
| winter             | t < low + h    | t > high + h    |
| summer             | t < low - h    | t > high - h    |
| intermediate       | t < low - h    | t > high + h    |

Once winter, it stays winter until the temperature reaches low + h; once
summer, until it falls to high - h; and the intermediate band is left
only h beyond a threshold (below low - h, above high + h). With h = 0
every row is the plain rule, so the decision is the historical one.

The previous season is an input and the new one the output: the caller
keeps it between decisions (the runtime keeps one per window, in memory
only). ``None`` uses the plain rule: the first decision after a restart
or a reload, and the first after a decision without a reading (a missing
reading decides neither season, as always, and leaves no memory).

Each threshold is its own latch, so thresholds set the wrong way round
(low above high) can still give winter and summer at once, exactly as
the plain rule always did.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonInputs:
    """One season decision's reading and thresholds (HA's temperature unit)."""

    temperature: float | None
    temp_low: float | None
    temp_high: float | None
    hysteresis: float = 0
    outside_high: bool = True
    """The outside is above the outside threshold (True when none is set)."""


@dataclass(frozen=True)
class Season:
    """The season one decision found (and the memory for the next one).

    ``measured`` is False when there was no reading: that season (neither
    winter nor summer) is not remembered, the next decision uses the plain
    rule.
    """

    winter: bool = False
    summer: bool = False
    measured: bool = True

    @property
    def name(self) -> str:
        """``winter``, ``summer`` or ``intermediate`` (winter wins if both)."""
        if self.winter:
            return "winter"
        if self.summer:
            return "summer"
        return "intermediate"


def _margin(hysteresis: float, was_in: bool | None) -> float:
    """How far a threshold moves away from the season the window was in.

    In the season: ``h`` outward (it stays until ``h`` past the threshold);
    out of it: ``h`` inward (it enters only ``h`` past the threshold);
    no memory: 0, the plain rule.
    """
    if was_in is None:
        return 0.0
    return hysteresis if was_in else -hysteresis


def decide_season(inputs: SeasonInputs, previous: Season | None = None) -> Season:
    """Return this decision's season (see the module docstring for the rule)."""
    temperature = inputs.temperature
    if temperature is None:
        return Season(measured=False)
    memory = previous if previous is not None and previous.measured else None
    hysteresis = max(inputs.hysteresis, 0.0)
    was_winter = None if memory is None else memory.winter
    was_summer = None if memory is None else memory.summer
    winter = inputs.temp_low is not None and temperature < inputs.temp_low + _margin(
        hysteresis, was_winter
    )
    summer = (
        inputs.temp_high is not None
        and temperature > inputs.temp_high - _margin(hysteresis, was_summer)
        and inputs.outside_high
    )
    return Season(winter=winter, summer=summer)
