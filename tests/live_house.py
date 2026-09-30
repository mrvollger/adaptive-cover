"""The sanitized live house (tests/fixtures/house_snapshot) inside a test hass.

``load_live_house`` puts the house's floors, areas, physical covers, the
adaptive_cover config entries (at 1.1, as captured) and their device and
entity registry rows into hass, without setting anything up. Used by the
P1 surface upgrade test and the P7 consolidation tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)

SNAPSHOT = Path(__file__).parent / "fixtures" / "house_snapshot"


def snapshot_json(name: str) -> dict:
    """One snapshot file."""
    return json.loads((SNAPSHOT / name).read_text())


def load_live_house(
    hass, *, disabled: bool = False, floors: bool = False
) -> tuple[list[dict], list[dict], dict[str, str | None]]:
    """Put the live house's registries and 1.1 entries into hass.

    Returns (window and hub entries, their registry rows, cover -> the
    cover's effective area). ``disabled`` also adds the 3 disabled "SE"
    multi-cover entries (disabled by the user, as captured); ``floors``
    creates the house's floors and puts the areas on them.
    """
    snapshot_entries = snapshot_json("config_entries.json")["entries"]
    entries = [
        entry for entry in snapshot_entries if entry["role"] in ("window", "hub")
    ]
    entry_ids = {entry["entry_id"] for entry in entries}
    rows = [
        row
        for row in snapshot_json("entity_registry.json")["entities"]
        if row["config_entry_id"] in entry_ids
    ]
    covers = [
        cover
        for cover in snapshot_json("physical_covers.json")["covers"]
        if cover["platform"] != DOMAIN
    ]
    registry = snapshot_json("floors_areas.json")
    floor_ids: dict[str, str] = {}
    if floors:
        floor_reg = fr.async_get(hass)
        for floor in registry["floors"]:
            created_floor = floor_reg.async_create(floor["name"])
            floor_ids[floor["floor_id"]] = created_floor.floor_id
    area_reg = ar.async_get(hass)
    for area in registry["areas"]:
        created = area_reg.async_create(area["area_id"])
        assert created.id == area["area_id"]
        area_reg.async_update(
            created.id,
            name=area["name"],
            floor_id=floor_ids.get(area.get("floor_id") or "") if floors else None,
        )

    # The physical covers belong to another integration, with their areas.
    zha = MockConfigEntry(domain="zha")
    zha.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for cover in covers:
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

    for entry in entries:
        MockConfigEntry(
            domain=DOMAIN,
            entry_id=entry["entry_id"],
            title=entry["title"],
            data=entry["data"],
            options=entry["options"],
            version=1,
            minor_version=1,
        ).add_to_hass(hass)
        if temp := entry["options"].get(CONF_TEMP_ENTITY):
            hass.states.async_set(temp, "72", {"unit_of_measurement": "°F"})
        if weather := entry["options"].get(CONF_WEATHER_ENTITY):
            hass.states.async_set(weather, "sunny")
    if disabled:
        for entry in snapshot_entries:
            if entry["role"] != "disabled_legacy":
                continue
            MockConfigEntry(
                domain=DOMAIN,
                entry_id=entry["entry_id"],
                title=entry["title"],
                data={"name": entry["title"], CONF_SENSOR_TYPE: "cover_blind"},
                options=entry["options"],
                version=1,
                minor_version=1,
                disabled_by=ConfigEntryDisabler.USER,
            ).add_to_hass(hass)

    for device in snapshot_json("device_registry.json")["devices"]:
        (entry_id,) = device["config_entries"]
        created = dev_reg.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={tuple(identifier) for identifier in device["identifiers"]},
            name=device["name"],
        )
        dev_reg.async_update_device(
            created.id, name_by_user=device["name_by_user"], area_id=device["area_id"]
        )

    for row in rows:
        platform_domain, object_id = row["entity_id"].split(".", 1)
        created = ent_reg.async_get_or_create(
            platform_domain,
            DOMAIN,
            row["unique_id"],
            config_entry=hass.config_entries.async_get_entry(row["config_entry_id"]),
            suggested_object_id=object_id,
            has_entity_name=True,
            original_name=row["original_name"],
        )
        assert created.entity_id == row["entity_id"]

    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0}
    )
    cover_areas = {cover["entity_id"]: cover["effective_area_id"] for cover in covers}
    return entries, rows, cover_areas
