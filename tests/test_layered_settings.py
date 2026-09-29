"""P5 flip: a window acts on its layered settings, and edits store sparsely.

Since the flip every window resolves its recurring settings from its own
override, its area, its floor and the house (ADR 0003), and its one-time
settings from its options. The editing surfaces store what the user
changes where it belongs:

- the options form and ``change_settings``: one-time settings in the
  window's options; recurring ones as the window's own value in its
  ``overrides`` (``values`` where a window may override the option,
  ``legacy`` otherwise), only when it differs from what the window
  inherits; a value equal to the inherited one, or a cleared field,
  removes the override. The legacy flat keys are left alone (a downgrade
  reads them);
- a new window starts from the house's settings, and a copy copies what
  the source window acts on;
- stored layers that break the spec leave the window on its legacy
  options (logged), never without settings.

Observed through the config-entry store (where the edit went), the
diagnostics settings (what the window acts on) and entity states.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
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

from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle, window_settings

COVER = "cover.office"
OTHER = "cover.den"


def _entry(hass, cover: str = COVER, name: str = "Office", **extra) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
            CONF_DELTA_TIME: 2,
            **extra,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(autouse=True)
def covers(hass):
    async_mock_service(hass, "cover", "set_cover_position")
    for cover in (COVER, OTHER):
        hass.states.async_set(cover, "open", {"current_position": 60})


async def _setup(hass, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _hub(hass) -> MockConfigEntry:
    (hub,) = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    ]
    return hub


def _overrides(entry) -> tuple[dict, dict]:
    stored = entry.options["overrides"]
    assert stored["window_key"] == entry.entry_id
    return dict(stored["values"]), dict(stored["legacy"])


async def _save_options(
    hass, entry, changes: dict[str, Any], clear: frozenset[str] = frozenset()
) -> None:
    """Save the options form: every shown value as suggested, with ``changes``.

    A field in ``clear`` is left empty (a cleared field).
    """
    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input: dict[str, dict[str, Any]] = {}
    for marker, section in result["data_schema"].schema.items():
        fields: dict[str, Any] = {}
        for field in section.schema.schema:
            key = str(field)
            suggested = (field.description or {}).get("suggested_value")
            if key in changes:
                fields[key] = changes[key]
            elif suggested is not None and key not in clear:
                fields[key] = suggested
        user_input[str(marker)] = fields
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()


# ------------------------------------------------------------ options form


async def test_options_form_stores_recurring_edits_as_sparse_overrides(
    hass, mock_sun_entity
):
    entry = _entry(hass)
    await _setup(hass, entry)
    flat_before = {
        key: entry.options.get(key) for key in (CONF_EYE_HEIGHT, CONF_DELTA_TIME)
    }
    house = dict(_hub(hass).options["house"])

    await _save_options(
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
    # The legacy flat keys are left for a downgrade; the house is untouched.
    assert {key: entry.options.get(key) for key in flat_before} == flat_before
    assert _hub(hass).options["house"] == house
    assert WindowHandle(hass, COVER).attributes["provenance"] == {
        CONF_EYE_HEIGHT: "window",
        CONF_DELTA_TIME: "legacy",
        CONF_QUIET_START: "legacy",
    }

    # Back to the inherited delta time, eye height and quiet start cleared:
    # nothing of the window's own is left; it inherits the house's again.
    await _save_options(
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


async def test_options_form_one_time_edit_goes_to_the_options(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    await _save_options(hass, entry, {CONF_HEIGHT_WIN: 2.4})
    assert entry.options[CONF_HEIGHT_WIN] == 2.4
    assert _overrides(entry) == ({}, {})
    assert entry.state is ConfigEntryState.LOADED
    assert (await window_settings(hass, entry.entry_id))[CONF_HEIGHT_WIN] == 2.4


async def test_options_form_shows_what_the_window_acts_on(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_SUNSET_POS: 30},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SUNSET_POS] == 0  # the legacy key, untouched

    result = await hass.config_entries.options.async_init(entry.entry_id)
    suggested = {
        str(field): (field.description or {}).get("suggested_value")
        for section in result["data_schema"].schema.values()
        for field in section.schema.schema
    }
    hass.config_entries.options.async_abort(result["flow_id"])
    assert suggested[CONF_SUNSET_POS] == 30


# ------------------------------------------------------------ change_settings


async def test_change_settings_stores_sparse_overrides(hass, mock_sun_entity):
    entry = _entry(hass)
    await _setup(hass, entry)
    house_eye = _hub(hass).options["house"][CONF_EYE_HEIGHT]

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
    assert _hub(hass).options["house"][CONF_SUNSET_POS] == 12

    # The add form shows the house's value.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    suggested = {
        str(field): (field.description or {}).get("suggested_value")
        for section in result["data_schema"].schema.values()
        for field in section.schema.schema
    }
    hass.config_entries.flow.async_abort(result["flow_id"])
    assert suggested[CONF_SUNSET_POS] == 12

    # add_entry without a template inherits everything recurring.
    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Den", "cover": OTHER},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    new = hass.config_entries.async_get_entry(response["entry_id"])
    assert _overrides(new) == ({}, {})
    assert (await window_settings(hass, new.entry_id))[CONF_SUNSET_POS] == 12


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
    copy = hass.config_entries.async_get_entry(response["entry_id"])
    assert (await window_settings(hass, copy.entry_id))[CONF_EYE_HEIGHT] == 1.6
    assert _overrides(copy) == ({CONF_EYE_HEIGHT: 1.6}, {})


# ------------------------------------------------------------ robustness


async def test_invalid_layers_leave_the_window_on_its_options(
    hass, mock_sun_entity, caplog
):
    entry = _entry(hass, **{CONF_SUNSET_POS: 12})
    await _setup(hass, entry)
    hub = _hub(hass)
    # A floor-level option stored on the house breaks the spec.
    house = {**hub.options["house"], CONF_SUNSET_POS: 40, "bogus_option": 1}
    hass.config_entries.async_update_entry(hub, options={**hub.options, "house": house})
    hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 181, "elevation": 44})
    await hass.async_block_till_done()

    assert (await window_settings(hass, entry.entry_id))[CONF_SUNSET_POS] == 12
    assert WindowHandle(hass, COVER).attributes["provenance"] is None
    assert "the layered settings are invalid" in caplog.text

    # An edit meanwhile goes where the window reads it: its options.
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_SUNSET_POS: 20},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_SUNSET_POS] == 20
    assert (await window_settings(hass, entry.entry_id))[CONF_SUNSET_POS] == 20
