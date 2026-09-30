"""The live house as v1.19.x runs it, inside a test hass (for ADR 0008).

``load_v1_19_house`` puts the sanitized live house's floors, areas and
physical covers into hass (tests/fixtures/house_snapshot), then the
adaptive_cover config entries and registry rows as v1.19.x holds them
just before the owner installs v2.1:

- the hub entry at 1.5, lifted: its options hold the house, floor and
  area layers (and the hub's leftover geometry and ``group``);
- the 15 window entries at 1.5, each with its data and options (the 1.3
  shape, the legacy flat keys, and the ``overrides`` the lift gave it);
- the window devices on their window entries (no ``via``), every entity
  row on its entry (the 60 hidden switch aliases included);
- the 3 disabled "SE" window entries.

It is derived from the v2.0 consolidation fixture (tests/fixtures/
consolidated_v2_0), which v2.0 produced from the same 1.5 entries by
moving them verbatim (ADR 0006): each window subentry becomes its window
entry again (its key is the entry_id), and each registry row goes back to
that entry. One difference is kept on purpose: the edited window
(``expected.json`` "edited") holds its edit as v1.19.x stores one, in the
flat option only (``sunset_position`` 42), with the overrides the lift
gave it (no ``sunset_position``). Its layered settings then differ from
what it acts on, as the ``settings_differ`` repair of v1.19.x shows.
Nothing is set up.
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import CONF_SUNSET_POS, DOMAIN

from .consolidated_house import _load_places, fixture_json

EDIT_VALUE = 42.0


def v1_19_entries() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    """The hub and the window entries as v1.19.x stores them (plain dicts).

    Returns (hub, windows, subentry_id -> window key).
    """
    stored = fixture_json("house.json")["house"]
    edited = fixture_json("expected.json")["edited"]
    hub = {
        "entry_id": stored["entry_id"],
        "title": stored["title"],
        "unique_id": stored["unique_id"],
        "data": copy.deepcopy(stored["data"]),
        "options": copy.deepcopy(stored["options"]),
    }
    windows: list[dict[str, Any]] = []
    keys: dict[str, str] = {}
    for subentry in stored["subentries"]:
        key = subentry["data"]["window_key"]
        keys[subentry["subentry_id"]] = key
        options = copy.deepcopy(subentry["data"]["options"])
        if key == edited:
            # v1.19.x writes an edit to the flat option only.
            options[CONF_SUNSET_POS] = EDIT_VALUE
            options["overrides"]["values"].pop(CONF_SUNSET_POS)
        windows.append(
            {
                "entry_id": key,
                "title": subentry["title"],
                "unique_id": subentry["unique_id"],
                "data": copy.deepcopy(subentry["data"]["data"]),
                "options": options,
            }
        )
    return hub, windows, keys


def load_v1_19_house(hass) -> tuple[MockConfigEntry, list[MockConfigEntry]]:
    """Put the live house as v1.19.x holds it into hass; return (hub, windows)."""
    _load_places(hass)
    stored_hub, stored_windows, keys = v1_19_entries()
    hub = MockConfigEntry(
        domain=DOMAIN,
        entry_id=stored_hub["entry_id"],
        title=stored_hub["title"],
        unique_id=stored_hub["unique_id"],
        data=stored_hub["data"],
        options=stored_hub["options"],
        version=1,
        minor_version=5,
    )
    hub.add_to_hass(hass)
    windows = []
    for stored in stored_windows:
        window = MockConfigEntry(
            domain=DOMAIN,
            entry_id=stored["entry_id"],
            title=stored["title"],
            unique_id=stored["unique_id"],
            data=stored["data"],
            options=stored["options"],
            version=1,
            minor_version=5,
        )
        window.add_to_hass(hass)
        windows.append(window)
    for disabled in fixture_json("house.json")["disabled_windows"]:
        MockConfigEntry(
            domain=DOMAIN,
            entry_id=disabled["entry_id"],
            title=disabled["title"],
            data=disabled["data"],
            options=disabled["options"],
            version=disabled["version"],
            minor_version=disabled["minor_version"],
            disabled_by=ConfigEntryDisabler.USER,
        ).add_to_hass(hass)

    registry = fixture_json("registry.json")
    dev_reg = dr.async_get(hass)
    device_ids: dict[tuple[str, str], str] = {}
    for device in registry["devices"]:
        identifier = tuple(device["identifier"])
        # A window device sits on its window entry; the hub device on the hub.
        owner = keys.get(device["config_subentry_id"] or "", hub.entry_id)
        created = dev_reg.async_get_or_create(
            config_entry_id=owner,
            identifiers={identifier},
            name=device["name"],
            entry_type=dr.DeviceEntryType(device["entry_type"])
            if device["entry_type"]
            else None,
        )
        dev_reg.async_update_device(
            created.id, name_by_user=device["name_by_user"], area_id=device["area_id"]
        )
        device_ids[identifier] = created.id

    ent_reg = er.async_get(hass)
    entries = {entry.entry_id: entry for entry in (hub, *windows)}
    for row in registry["entities"]:
        _domain, object_id = row["entity_id"].split(".", 1)
        owner = keys.get(row["config_subentry_id"] or "", hub.entry_id)
        created = ent_reg.async_get_or_create(
            row["domain"],
            DOMAIN,
            row["unique_id"],
            config_entry=entries[owner],
            device_id=device_ids[tuple(row["device"])] if row["device"] else None,
            suggested_object_id=object_id,
            has_entity_name=row["has_entity_name"],
            original_name=row["original_name"],
            translation_key=row["translation_key"],
            entity_category=EntityCategory(row["entity_category"])
            if row["entity_category"]
            else None,
            hidden_by=er.RegistryEntryHider(row["hidden_by"])
            if row["hidden_by"]
            else None,
            disabled_by=er.RegistryEntryDisabler(row["disabled_by"])
            if row["disabled_by"]
            else None,
        )
        assert created.entity_id == row["entity_id"]
        if row["name"] or row["icon"] or row["area_id"] or row["labels"]:
            ent_reg.async_update_entity(
                created.entity_id,
                name=row["name"],
                icon=row["icon"],
                area_id=row["area_id"],
                labels=set(row["labels"]),
            )
    return hub, windows
