"""The live house as v2.0 consolidated it, inside a test hass (for P8).

``load_consolidated_house`` puts the sanitized live house's floors, areas
and physical covers (tests/fixtures/house_snapshot) into hass, then the
adaptive_cover config entries and registry rows exactly as v2.0.x left
them after its consolidation (tests/fixtures/consolidated_v2_0, see its
generate.py): the house entry at 2.1 with its 15 window subentries
(stored verbatim, ADR 0006), the 3 disabled "SE" window entries, the
window devices on the house and their subentries, and every entity row
(the 60 hidden switch aliases included). Nothing is set up.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import EntityCategory
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import DOMAIN

from .live_house import snapshot_json

FIXTURE = Path(__file__).parent / "fixtures" / "consolidated_v2_0"


def fixture_json(name: str) -> dict[str, Any]:
    """One file of the consolidated-v2.0 fixture."""
    return json.loads((FIXTURE / name).read_text())


def _load_places(hass) -> None:
    """Floors, areas, the physical covers (with areas and states), sensors."""
    registry = snapshot_json("floors_areas.json")
    floor_reg = fr.async_get(hass)
    floor_ids = {
        floor["floor_id"]: floor_reg.async_create(floor["name"]).floor_id
        for floor in registry["floors"]
    }
    area_reg = ar.async_get(hass)
    for area in registry["areas"]:
        created = area_reg.async_create(area["area_id"])
        assert created.id == area["area_id"]
        area_reg.async_update(
            created.id,
            name=area["name"],
            floor_id=floor_ids.get(area.get("floor_id") or ""),
        )
    zha = MockConfigEntry(domain="zha")
    zha.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for cover in snapshot_json("physical_covers.json")["covers"]:
        if cover["platform"] == DOMAIN:
            continue
        device = dev_reg.async_get_or_create(
            config_entry_id=zha.entry_id,
            identifiers={("zha", cover["device_id"])},
            name=cover["device_name"],
        )
        dev_reg.async_update_device(device.id, area_id=cover["device_area_id"])
        platform_domain, object_id = cover["entity_id"].split(".", 1)
        ent_reg.async_get_or_create(
            platform_domain,
            "zha",
            cover["entity_id"],
            config_entry=zha,
            device_id=device.id,
            suggested_object_id=object_id,
        )
        ent_reg.async_update_entity(
            cover["entity_id"], area_id=cover["registry_area_id"]
        )
        hass.states.async_set(
            cover["entity_id"],
            cover["state_now"],
            {"current_position": cover["current_position_now"]},
        )
    for sensor in (
        "sensor.upstairs_indoor_temperature",
        "sensor.downstairs_indoor_temperature",
    ):
        hass.states.async_set(sensor, "72", {"unit_of_measurement": "°F"})
    hass.states.async_set("weather.forecast_home_2", "sunny")
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0}
    )


def load_consolidated_house(hass) -> MockConfigEntry:
    """Put the v2.0-consolidated live house into hass; return the house entry."""
    _load_places(hass)
    stored = fixture_json("house.json")
    record = stored["house"]
    house = MockConfigEntry(
        domain=DOMAIN,
        entry_id=record["entry_id"],
        title=record["title"],
        unique_id=record["unique_id"],
        data=record["data"],
        options=record["options"],
        version=record["version"],
        minor_version=record["minor_version"],
        subentries_data=record["subentries"],
    )
    house.add_to_hass(hass)
    for window in stored["disabled_windows"]:
        MockConfigEntry(
            domain=DOMAIN,
            entry_id=window["entry_id"],
            title=window["title"],
            data=window["data"],
            options=window["options"],
            version=window["version"],
            minor_version=window["minor_version"],
            disabled_by=ConfigEntryDisabler.USER,
        ).add_to_hass(hass)

    registry = fixture_json("registry.json")
    dev_reg = dr.async_get(hass)
    device_ids: dict[tuple[str, str], str] = {}
    # The house device first: the window devices hang off it.
    devices = sorted(registry["devices"], key=lambda device: device["via"] is not None)
    for device in devices:
        identifier = tuple(device["identifier"])
        created = dev_reg.async_get_or_create(
            config_entry_id=device["config_entry_id"],
            config_subentry_id=device["config_subentry_id"],
            identifiers={identifier},
            name=device["name"],
            entry_type=dr.DeviceEntryType(device["entry_type"])
            if device["entry_type"]
            else None,
            via_device=tuple(device["via"]) if device["via"] else None,
        )
        dev_reg.async_update_device(
            created.id, name_by_user=device["name_by_user"], area_id=device["area_id"]
        )
        device_ids[identifier] = created.id

    ent_reg = er.async_get(hass)
    for row in registry["entities"]:
        _domain, object_id = row["entity_id"].split(".", 1)
        created = ent_reg.async_get_or_create(
            row["domain"],
            DOMAIN,
            row["unique_id"],
            config_entry=house,
            config_subentry_id=row["config_subentry_id"],
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
    return house
