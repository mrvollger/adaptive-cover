"""Decider: the active position and the output transforms (P4)."""

from __future__ import annotations

import logging

import pytest

from custom_components.adaptive_cover.const import (
    CONF_INTERP_END,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_INTERP_START,
)
from custom_components.adaptive_cover.runtime.decider import Decider, inverse_state
from custom_components.adaptive_cover.runtime.shade_config import ShadeConfig

PLAIN = ShadeConfig.from_options({})
RANGE = ShadeConfig.from_options({CONF_INTERP_START: 20, CONF_INTERP_END: 80})
LISTS = ShadeConfig.from_options(
    {CONF_INTERP_LIST: ["0", "50", "100"], CONF_INTERP_LIST_NEW: ["0", "20", "100"]}
)


@pytest.mark.parametrize(("state", "inverse"), [(0, 100), (100, 0), (25, 75)])
def test_inverse_state(state, inverse):
    assert inverse_state(state) == inverse


def test_no_transform_by_default():
    assert Decider(False, False).transform(37, PLAIN) == 37


def test_inverse_without_interpolation():
    assert Decider(False, True).transform(30, PLAIN) == 70


@pytest.mark.parametrize(
    ("state", "sent"),
    [(50, 50), (25, 35), (0, 0), (100, 100)],  # 0 -> 20 and 100 -> 80 snap out
)
def test_interpolation_onto_a_range(state, sent):
    assert Decider(True, False).transform(state, RANGE) == sent


@pytest.mark.parametrize(("state", "sent"), [(50, 20), (25, 10), (75, 60)])
def test_interpolation_through_lists(state, sent):
    assert Decider(True, False).transform(state, LISTS) == sent


def test_interpolation_without_a_mapping_is_identity():
    assert Decider(True, False).transform(37, PLAIN) == 37


def test_inverse_is_skipped_with_interpolation(caplog):
    caplog.set_level(logging.INFO)
    assert Decider(True, True).transform(50, LISTS) == 20
    assert "Inverse state is not supported with interpolation" in caplog.text


@pytest.mark.parametrize(
    ("use_climate", "expected"), [(False, 70), (True, 40)]
)  # inverted basic 30 / climate 60
def test_position_picks_the_active_state_and_transforms_it(use_climate, expected):
    decider = Decider(False, True)
    assert decider.position(30, 60, use_climate, PLAIN) == expected
