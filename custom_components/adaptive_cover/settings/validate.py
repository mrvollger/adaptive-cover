"""Cross-field checks shared by the setup wizard and the options form.

One function per rule. Each returns ``{field: error_key}`` (empty when the
values pass); the error keys have strings under ``config.error`` and
``options.error`` in strings.json. A rule only checks fields that are set,
so it can run on any page's values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from ..const import (
    CONF_BLIND_SPOT_LEFT,
    CONF_BLIND_SPOT_RIGHT,
    CONF_INTERP_LIST,
    CONF_INTERP_LIST_NEW,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
)

ERROR_ELEVATION_ORDER: Final = "max_elevation_not_above_min"
ERROR_BLIND_SPOT_ORDER: Final = "blind_spot_right_not_above_left"
ERROR_INTERP_LENGTHS: Final = "interp_lists_differ"

Errors = dict[str, str]


def elevation_order(values: Mapping[str, Any]) -> Errors:
    """Require max elevation above min elevation when both are set."""
    low = values.get(CONF_MIN_ELEVATION)
    high = values.get(CONF_MAX_ELEVATION)
    if low is not None and high is not None and high <= low:
        return {CONF_MAX_ELEVATION: ERROR_ELEVATION_ORDER}
    return {}


def blind_spot_order(values: Mapping[str, Any]) -> Errors:
    """Require the blind spot's right edge to be past its left edge."""
    left = values.get(CONF_BLIND_SPOT_LEFT)
    right = values.get(CONF_BLIND_SPOT_RIGHT)
    if left is not None and right is not None and right <= left:
        return {CONF_BLIND_SPOT_RIGHT: ERROR_BLIND_SPOT_ORDER}
    return {}


def interp_lengths(values: Mapping[str, Any]) -> Errors:
    """Require the interpolation lists to pair up (same length)."""
    old = values.get(CONF_INTERP_LIST)
    new = values.get(CONF_INTERP_LIST_NEW)
    if old is not None and new is not None and len(old) != len(new):
        return {CONF_INTERP_LIST_NEW: ERROR_INTERP_LENGTHS}
    return {}


Rule = Callable[[Mapping[str, Any]], Errors]
RULES: Final[tuple[Rule, ...]] = (elevation_order, blind_spot_order, interp_lengths)
ERROR_KEYS: Final = (
    ERROR_ELEVATION_ORDER,
    ERROR_BLIND_SPOT_ORDER,
    ERROR_INTERP_LENGTHS,
)


def cross_field_errors(
    values: Mapping[str, Any], rules: tuple[Rule, ...] = RULES
) -> Errors:
    """Run ``rules`` on ``values``; ``{field: error_key}`` for each failure."""
    errors: Errors = {}
    for rule in rules:
        errors.update(rule(values))
    return errors
