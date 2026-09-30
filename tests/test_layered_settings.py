"""A window acts on its layered settings, and edits store sparsely (P5, P8).

Every window resolves its recurring settings from its own override, its
area, its floor and the house (ADR 0003), and its one-time settings from
its geometry. The editing surfaces store what the user changes where it
belongs:

- a window's Reconfigure and ``change_settings``: one-time settings in the
  window's geometry; recurring ones as the window's own value in its
  ``overrides`` (``values`` where a window may override the option,
  ``legacy`` otherwise), only when it differs from what the window
  inherits; a value equal to the inherited one, or a cleared field,
  removes the override. Nothing else is stored (no copy of the recurring
  settings in the window);
- a new window starts from the house's settings, and a copy copies what
  the source window acts on;
- stored layers that break the spec stop the window (it acts on nothing
  it cannot read) until they are fixed.

Observed through the house entry (where the edit went), the diagnostics
settings (what the window acts on) and entity states.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_QUIET_START,
    CONF_SENSOR_TYPE,
    CONF_SUNSET_POS,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.settings.lift import legacy_flat
from custom_components.adaptive_cover.settings.spec import OPTS_BY_KEY, Scope

from .conftest import COMMON_OPTIONS
from .house_model import mock_window_entry, window_subentry
from .window_form import prefilled, record, start_add_window, start_reconfigure
from .window_form import submit as submit_form
from .window_handle import WindowHandle, window_settings

COVER = "cover.office"
OTHER = "cover.den"

# Every recurring setting at its spec default (°C): the house of these
# tests holds a value for each, as a real house does.
RECURRING_DEFAULTS = {
    key: value
    for key, value in legacy_flat({}, temperature_unit="°C").items()
    if OPTS_BY_KEY[key].scope is Scope.RECURRING
}


def _entry(hass, cover: str = COVER, name: str = "Office", **extra):
    """A house with one window (``entry_id`` is also the window key)."""
    return mock_window_entry(
        hass,
        {"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        {
            **RECURRING_DEFAULTS,
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
            CONF_DELTA_TIME: 2,
            **extra,
        },
    )


@pytest.fixture(autouse=True)
def covers(hass):
    async_mock_service(hass, "cover", "set_cover_position")
    for cover in (COVER, OTHER):
        hass.states.async_set(cover, "open", {"current_position": 60})


async def _setup(hass, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _overrides(entry, key: str | None = None) -> tuple[dict, dict]:
    """The window's stored overrides: (values, legacy)."""
    stored = window_subentry(entry, key or entry.entry_id).data["overrides"]
    return dict(stored["values"]), dict(stored["legacy"])


async def _save_reconfigure(
    hass, entry, changes: dict[str, Any], clear: frozenset[str] = frozenset()
) -> None:
    """Save the window's Reconfigure: every shown value as suggested, with ``changes``.

    A field in ``clear`` is left empty (a cleared field).
    """
    subentry = window_subentry(entry, entry.entry_id)
    result = await start_reconfigure(hass, entry, subentry.subentry_id)
    values = {
        key: value for key, value in prefilled(result).items() if key not in clear
    }
    result = await submit_form(hass, result, {**values, **changes})
    assert result["type"] is FlowResultType.ABORT, result
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()


# ------------------------------------------------------------ reconfigure


async def test_reconfigure_stores_recurring_edits_as_sparse_overrides(
    hass, mock_sun_entity
):
    entry = _entry(hass)
    await _setup(hass, entry)
    house = dict(entry.options["house"])

    await _save_reconfigure(
        hass,
        entry,
        {CONF_EYE_HEIGHT: 1.5, CONF_DELTA_TIME: 7, CONF_QUIET_START: "22:00:00"},
    )

    # A window may override the eye height (values); the delta time and
    # quiet hours are house settings (a per-window legacy value).
    assert _overrides(entry) == (
        {CONF_EYE_HEIGHT: 1.5},
        {CONF_DELTA_TIME: 7, CONF_QUIET_START: "22:00:00"},
    )
    settings = await window_settings(hass, entry.entry_id)
    assert settings[CONF_EYE_HEIGHT] == 1.5
    assert settings[CONF_DELTA_TIME] == 7
    # The window stores no copy of a recurring setting; the house is untouched.
    geometry = record(window_subentry(entry, entry.entry_id)).geometry
    assert not {CONF_EYE_HEIGHT, CONF_DELTA_TIME, CONF_QUIET_START} & set(geometry)
    assert entry.options["house"] == house
    assert WindowHandle(hass, COVER).attributes["provenance"] == {
        CONF_EYE_HEIGHT: "window",
        CONF_DELTA_TIME: "legacy",
        CONF_QUIET_START: "legacy",
    }

    # Back to the inherited delta time, eye height and quiet start cleared:
    # nothing of the window's own is left; it inherits the house's again.
    await _save_reconfigure(
        hass,
        entry,
        {CONF_DELTA_TIME: 2},
        clear=frozenset({CONF_EYE_HEIGHT, CONF_QUIET_START}),
    )
    assert _overrides(entry) == ({}, {})
    settings = await window_settings(hass, entry.entry_id)
    assert settings[CONF_QUIET_START] is None
    assert settings[CONF_EYE_HEIGHT] == house[CONF_EYE_HEIGHT]
    assert WindowHandle(hass, COVER).attributes["provenance"] == {}


async def test_reconfigure_one_time_edit_goes_to_the_geometry(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _save_reconfigure(hass, entry, {CONF_HEIGHT_WIN: 2.4})
    subentry = window_subentry(entry, entry.entry_id)
    assert record(subentry).geometry[CONF_HEIGHT_WIN] == 2.4
    assert _overrides(entry) == ({}, {})
    assert entry.state is ConfigEntryState.LOADED
    assert (await window_settings(hass, entry.entry_id))[CONF_HEIGHT_WIN] == 2.4


async def test_reconfigure_shows_what_the_window_acts_on(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_SUNSET_POS: 30},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options["house"][CONF_SUNSET_POS] == 0  # the house, untouched

    subentry = window_subentry(entry, entry.entry_id)
    result = await start_reconfigure(hass, entry, subentry.subentry_id)
    hass.config_entries.subentries.async_abort(result["flow_id"])
    assert prefilled(result)[CONF_SUNSET_POS] == 30


# ------------------------------------------------------------ change_settings


async def test_change_settings_stores_sparse_overrides(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    house_eye = entry.options["house"][CONF_EYE_HEIGHT]

    async def change(**changes):
        response = await hass.services.async_call(
            DOMAIN,
            "change_settings",
            {"config_entry": entry.entry_id, **changes},
            blocking=True,
            return_response=True,
        )
        await hass.async_block_till_done()
        return response

    response = await change(**{CONF_EYE_HEIGHT: 1.6})
    assert response["changed"] == [CONF_EYE_HEIGHT]  # the schema is unchanged
    assert _overrides(entry) == ({CONF_EYE_HEIGHT: 1.6}, {})
    await change(**{CONF_EYE_HEIGHT: house_eye})
    assert _overrides(entry) == ({}, {})
    # None ("clear") means inherit.
    await change(**{CONF_EYE_HEIGHT: 1.6})
    await change(**{CONF_EYE_HEIGHT: None})
    assert _overrides(entry) == ({}, {})
    assert (await window_settings(hass, entry.entry_id))[CONF_EYE_HEIGHT] == house_eye


# ------------------------------------------------------------ new windows


async def test_a_new_window_starts_from_the_house(hass, mock_sun_entity):
    entry = _entry(hass, **{CONF_SUNSET_POS: 12})
    await _setup(hass, entry)
    assert entry.options["house"][CONF_SUNSET_POS] == 12

    # The add form ("Add window") shows the house's value.
    result = await start_add_window(hass, entry)
    hass.config_entries.subentries.async_abort(result["flow_id"])
    assert prefilled(result)[CONF_SUNSET_POS] == 12

    # add_entry without a template inherits everything recurring.
    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Den", "cover": OTHER},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    key = response["entry_id"]
    assert _overrides(entry, key) == ({}, {})
    assert (await window_settings(hass, key))[CONF_SUNSET_POS] == 12


async def test_a_copy_copies_what_the_source_acts_on(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_EYE_HEIGHT: 1.6},
        blocking=True,
    )
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Den", "cover": OTHER, "copy_from": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    key = response["entry_id"]
    assert (await window_settings(hass, key))[CONF_EYE_HEIGHT] == 1.6
    assert _overrides(entry, key) == ({CONF_EYE_HEIGHT: 1.6}, {})


# ------------------------------------------------------------ robustness


async def test_invalid_layers_stop_the_window_until_fixed(hass, mock_sun_entity):
    """Stored layers that break the spec: the window acts on none of them.

    Since v2.1 there are no legacy flat options to fall back on: the window
    stops (its entities are unavailable, no cover is commanded) until the
    layers are valid again.
    """
    entry = _entry(hass, **{CONF_SUNSET_POS: 12})
    await _setup(hass, entry)
    window = WindowHandle.by_key(hass, entry.entry_id)
    assert window.available
    good = dict(entry.options)
    # An option the spec does not know, stored on the house.
    house = {**entry.options["house"], "bogus_option": 1}
    hass.config_entries.async_update_entry(entry, options={**good, "house": house})
    calls = async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 181, "elevation": 44})
    await hass.async_block_till_done()
    assert not window.available
    assert calls == []

    hass.config_entries.async_update_entry(entry, options=good)
    hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 182, "elevation": 43})
    # (Refresh requests are debounced: the next one runs after the cooldown.)
    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=11))
    await hass.async_block_till_done()
    assert window.available
    assert (await window_settings(hass, entry.entry_id))[CONF_SUNSET_POS] == 12
