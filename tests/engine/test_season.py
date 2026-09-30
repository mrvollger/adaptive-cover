"""The climate season and its hysteresis (engine/season.py).

The owner's house: heating threshold 72 °F, cooling 75 °F. A thermostat
holding the room at 72 flips the plain rule between winter and
intermediate with every reading; a hysteresis of h keeps each season until
the reading is h past the threshold. Hysteresis 0 must be the plain rule,
bit for bit, whatever the previous season.
"""

from __future__ import annotations

import itertools

import pytest

from custom_components.adaptive_cover.engine import (
    Season,
    SeasonInputs,
    decide_season,
)

LOW, HIGH = 72.0, 75.0
WINTER = Season(winter=True)
SUMMER = Season(summer=True)
INTERMEDIATE = Season()
NO_READING = Season(measured=False)
PREVIOUS = {
    "none": None,
    "winter": WINTER,
    "summer": SUMMER,
    "intermediate": INTERMEDIATE,
    "no_reading": NO_READING,
}


def season(temp, previous=None, *, h=1.0, low=LOW, high=HIGH, outside_high=True):
    inputs = SeasonInputs(
        temperature=temp,
        temp_low=low,
        temp_high=high,
        hysteresis=h,
        outside_high=outside_high,
    )
    return decide_season(inputs, previous).name


def plain(temp, low, high, outside_high=True):
    """The historical rule (ClimateCoverData.is_winter / is_summer)."""
    if temp is None:
        return False, False
    winter = low is not None and temp < low
    summer = high is not None and temp > high and outside_high
    return winter, summer


# ------------------------------------------------------------ plain rule


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (60.0, "winter"),
        (71.9, "winter"),
        (72.0, "intermediate"),  # not below the heating threshold
        (73.5, "intermediate"),
        (75.0, "intermediate"),  # not above the cooling threshold
        (75.1, "summer"),
        (90.0, "summer"),
    ],
)
def test_first_decision_uses_the_plain_rule(temp, expected):
    """No memory (a restart, a reload): the thresholds as they are."""
    assert season(temp, None) == expected


# ------------------------------------------------------------ winter latch


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (71.0, "winter"),
        (72.0, "winter"),  # at the threshold: still winter
        (72.9, "winter"),
        (73.0, "intermediate"),  # low + h: winter ends
        (74.0, "intermediate"),
    ],
)
def test_winter_stays_until_low_plus_hysteresis(temp, expected):
    assert season(temp, WINTER) == expected


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (71.9, "intermediate"),  # the plain rule would say winter
        (71.0, "intermediate"),  # low - h: not yet
        (70.9, "winter"),
    ],
)
def test_winter_is_entered_only_below_low_minus_hysteresis(temp, expected):
    assert season(temp, INTERMEDIATE) == expected


# ------------------------------------------------------------ summer latch


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (76.0, "summer"),
        (75.0, "summer"),  # at the threshold: still summer
        (74.1, "summer"),
        (74.0, "intermediate"),  # high - h: summer ends
        (73.0, "intermediate"),
    ],
)
def test_summer_stays_until_high_minus_hysteresis(temp, expected):
    assert season(temp, SUMMER) == expected


@pytest.mark.parametrize(
    ("temp", "expected"),
    [
        (75.1, "intermediate"),  # the plain rule would say summer
        (76.0, "intermediate"),  # high + h: not yet
        (76.1, "summer"),
    ],
)
def test_summer_is_entered_only_above_high_plus_hysteresis(temp, expected):
    assert season(temp, INTERMEDIATE) == expected


# ------------------------------------------------------------ band edges


def test_a_jump_across_the_band_still_changes_season():
    """From winter to summer (and back) in one reading: both margins apply."""
    assert season(76.1, WINTER) == "summer"
    assert season(76.0, WINTER) == "intermediate"
    assert season(70.9, SUMMER) == "winter"
    assert season(71.0, SUMMER) == "intermediate"


def test_hovering_at_a_threshold_keeps_the_season():
    """71.9 <-> 72.1: the plain rule flips, a 1° hysteresis does not."""
    readings = [71.9, 72.1, 71.9, 72.1, 71.95, 72.05]

    def run(h):
        names, previous = [], None
        for temp in readings:
            found = decide_season(
                SeasonInputs(
                    temperature=temp, temp_low=LOW, temp_high=HIGH, hysteresis=h
                ),
                previous,
            )
            names.append(found.name)
            previous = found
        return names

    assert run(0) == ["winter", "intermediate"] * 3
    assert run(1.0) == ["winter"] * 6


def test_the_outside_condition_still_gates_summer():
    """Summer needs a warm outside, however sticky it is."""
    assert season(80.0, SUMMER, outside_high=False) == "intermediate"
    assert season(74.5, SUMMER, outside_high=True) == "summer"


def test_missing_thresholds_never_decide_a_season():
    assert season(60.0, WINTER, low=None) == "intermediate"
    assert season(90.0, SUMMER, high=None) == "intermediate"


def test_no_reading_decides_neither_and_leaves_no_memory():
    """A missing reading is intermediate (as always); the next one is plain."""
    gone = decide_season(
        SeasonInputs(temperature=None, temp_low=LOW, temp_high=HIGH, hysteresis=1.0),
        WINTER,
    )
    assert (gone.winter, gone.summer, gone.measured) == (False, False, False)
    # 72.5 would stay winter from winter and stay intermediate from
    # intermediate; with no memory the plain rule decides.
    assert season(71.5, gone) == "winter"
    assert season(72.5, gone) == "intermediate"


def test_a_negative_hysteresis_counts_as_none():
    assert season(72.5, WINTER, h=-1.0) == "intermediate"
    assert season(71.9, INTERMEDIATE, h=-1.0) == "winter"


def test_season_names():
    assert WINTER.name == "winter"
    assert SUMMER.name == "summer"
    assert INTERMEDIATE.name == "intermediate"
    # thresholds set the wrong way round: winter wins, like Control method
    assert Season(winter=True, summer=True).name == "winter"


# ------------------------------------------------------------ hysteresis 0

TEMPS = [None, -5.0, 0.0, 20.0, 21.9, 22.0, 22.1, 23.9, 24.0, 24.1, 30.0]
TEMPS += [60.0, 71.9, 72.0, 72.1, 74.9, 75.0, 75.1, 90.0]
THRESHOLDS = {
    "house_f": (LOW, HIGH),
    "metric": (22.0, 24.0),
    "stored_as_int": (72, 75),
    "no_low": (None, HIGH),
    "no_high": (LOW, None),
    "none": (None, None),
    "wrong_way_round": (75.0, 72.0),
    "equal": (72.0, 72.0),
}


@pytest.mark.parametrize("thresholds", THRESHOLDS)
def test_hysteresis_zero_is_the_plain_rule(thresholds):
    """Byte-identity: hysteresis 0 decides as the historical rule, whatever
    the previous season (so the truth table, goldens and replay hold)."""
    low, high = THRESHOLDS[thresholds]
    for temp, previous, outside_high in itertools.product(
        TEMPS, PREVIOUS.values(), (True, False)
    ):
        found = decide_season(
            SeasonInputs(
                temperature=temp,
                temp_low=low,
                temp_high=high,
                hysteresis=0,
                outside_high=outside_high,
            ),
            previous,
        )
        expected = plain(temp, low, high, outside_high)
        assert (found.winter, found.summer) == expected, (temp, previous, outside_high)
