"""Drive the one-screen window form (add and reconfigure) from tests.

The form is sectioned (``settings/schema.py``, "setup form"). Tests say what
they enter as one flat ``{field: value}`` dict; these helpers put each field
in the section that shows it. A section the test leaves out is sent empty,
which is what an untouched section is: every field keeps its default.

Since v2.1 (P8) the form has three places: the config flow's user step (a
fresh install: it creates the house with its first window), "Add window"
on the house (the ``window`` subentry flow) and a window's Reconfigure (the
subentry flow's reconfigure step, the exceptions included).

Only public surfaces: the config-entry and subentry flow managers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_COVER_ENTITY,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.settings import schema
from custom_components.adaptive_cover.settings.spec import OPTS_BY_KEY
from custom_components.adaptive_cover.settings.window_record import WindowRecord

# Form-only fields: all in the Window section.
FORM_FIELDS = frozenset(
    {
        schema.FIELD_COPY_FROM,
        schema.FIELD_PRESET,
        schema.FIELD_NAME,
        schema.FIELD_SENSOR_TYPE,
    }
)


def section_of(key: str) -> str:
    """Return the setup-form section that shows ``key``."""
    if key in FORM_FIELDS:
        return schema.WINDOW_SECTION
    return schema.setup_section(OPTS_BY_KEY[key])


def sectioned(
    values: Mapping[str, Any], sections: Iterable[str] = schema.SETUP_SECTIONS
) -> dict[str, dict[str, Any]]:
    """Return ``values`` as the form's ``{section: {field: value}}`` input."""
    out: dict[str, dict[str, Any]] = {name: {} for name in sections}
    for key, value in values.items():
        out[section_of(key)][key] = value
    return out


def shown(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{section: {field: marker}}`` of a shown form."""
    return {
        str(name): {str(marker): marker for marker in validator.schema.schema}
        for name, validator in result["data_schema"].schema.items()
    }


def prefilled(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return every field's pre-filled value (``suggested_value``), flat."""
    values: dict[str, Any] = {}
    for fields in shown(result).values():
        for key, marker in fields.items():
            description = marker.description or {}
            if "suggested_value" in description:
                values[key] = description["suggested_value"]
    return values


def collapsed(result: Mapping[str, Any]) -> dict[str, bool]:
    """Return ``{section: collapsed}`` of a shown form."""
    return {
        str(name): validator.options["collapsed"]
        for name, validator in result["data_schema"].schema.items()
    }


def add_legacy_house(hass) -> MockConfigEntry:
    """Add the hub of a house that still has window entries (1.5, not set up).

    v2.1 runs no such house: it must be consolidated on v2.0.x first
    (``upgrade.py``). Tests of the ``consolidate_first`` answers start here.
    """
    from custom_components.adaptive_cover.hub import (
        CONF_IS_HUB,
        HUB_ENTRY_NAME,
        HUB_UNIQUE_ID,
    )

    hub = MockConfigEntry(
        domain=DOMAIN,
        title=HUB_ENTRY_NAME,
        unique_id=HUB_UNIQUE_ID,
        data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
        options={},
        version=1,
        minor_version=5,
    )
    hub.add_to_hass(hass)
    return hub


def house(hass) -> config_entries.ConfigEntry:
    """Return the house entry."""
    return next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get("is_hub")
    )


def window_subentries(entry: config_entries.ConfigEntry) -> list[Any]:
    """Return the house's window subentries."""
    return [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == "window"
    ]


def only_window(entry: config_entries.ConfigEntry) -> Any:
    """Return the house's only window subentry."""
    (subentry,) = window_subentries(entry)
    return subentry


def record(subentry: Any) -> WindowRecord:
    """Return what a window subentry stores, read."""
    return WindowRecord.from_data(subentry.data)


def _manager(hass, result: Mapping[str, Any]):
    """The flow manager of ``result`` (a subentry flow's handler is a tuple)."""
    if isinstance(result.get("handler"), tuple):
        return hass.config_entries.subentries
    return hass.config_entries.flow


async def start_add(hass) -> dict[str, Any]:
    """Open the add form of a fresh install (the config flow's user step)."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def start_add_window(hass, entry=None) -> dict[str, Any]:
    """Open "Add window" on the house (the subentry flow)."""
    entry = entry or house(hass)
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "window"), context={"source": config_entries.SOURCE_USER}
    )


async def start_reconfigure(hass, entry, subentry_id: str) -> dict[str, Any]:
    """Open the Reconfigure form of one window subentry of ``entry``."""
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "window"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry_id,
        },
    )


async def submit(
    hass,
    result: Mapping[str, Any],
    values: Mapping[str, Any],
    sections: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Submit ``values`` on the shown form (its own sections by default)."""
    names = list(sections) if sections is not None else list(shown(result))
    return await _manager(hass, result).async_configure(
        result["flow_id"], sectioned(values, names)
    )


async def show_type(hass, result: Mapping[str, Any], cover_type: str, cover: str):
    """Switch the shown form to ``cover_type``; return the form shown for it."""
    result = await submit(
        hass,
        result,
        {CONF_COVER_ENTITY: cover, schema.FIELD_SENSOR_TYPE: cover_type},
    )
    assert result["type"] is FlowResultType.FORM, result
    return result


async def add_window(hass, values: Mapping[str, Any], *, start=None) -> dict[str, Any]:
    """Add a window from ``values`` (flat); return the final flow result.

    ``start`` opens the form (default: a fresh install's config flow; pass
    ``start_add_window`` for "Add window" on the house). A cover type other
    than the default is picked first, so the form shows that type's
    geometry, as a user would.
    """
    result = await (start or start_add)(hass)
    cover_type = values.get(schema.FIELD_SENSOR_TYPE, SensorType.BLIND)
    if cover_type != SensorType.BLIND:
        result = await show_type(hass, result, cover_type, values[CONF_COVER_ENTITY])
    return await submit(hass, result, values)
