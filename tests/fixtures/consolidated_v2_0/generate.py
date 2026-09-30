"""Generate the consolidated-v2.0 house fixture (runs on v2.0.x code ONLY).

The P8 upgrade test (``tests/test_upgrade_2_1.py``) starts from the live
house as the owner will have it just before installing v2.1: consolidated
on v2.0.x (every window a ``window`` subentry of the house, stored
verbatim, ADR 0006). v2.1 no longer has the consolidation code, so this
fixture was produced once by running the v2.0 code (integ/v2.0.0 at
14b4e27, with temp_hysteresis) on the sanitized live snapshot (``tests/fixtures/house_snapshot``)
and dumping what Home Assistant stores afterwards:

- ``house.json``: the house entry (2.1, its options and its 15 window
  subentries with their ids), the 3 disabled "SE" window entries;
- ``registry.json``: every adaptive_cover entity row and device row
  (device links by identifier);
- ``expected.json``: what the v2.0 code showed for each window: its
  resolved settings and provenance (diagnostics), its Mode (one window
  held, one with an edit made after the P5 flip), and the house device.

Regenerate (only needed if the snapshot changes) from a checkout of
v2.0.x (``git worktree add /tmp/v2 v2.0.0``), with this file copied in:

    pytest tests/fixtures/consolidated_v2_0/generate.py -p no:randomly

It is not collected by the normal test run (the file name does not start
with ``test_``).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.adaptive_cover.const import (
    CONF_ENTITIES,
    CONF_SUNSET_POS,
    DOMAIN,
)
from tests.consolidation import consolidate_via_repair
from tests.live_house import load_live_house
from tests.window_handle import WindowHandle, window_settings

OUT = Path(__file__).parent
HELD = 3  # windows[HELD] is held for an hour through the hold service
EDITED = 5  # windows[EDITED] gets sunset_position 42 through change_settings

pytestmark = pytest.mark.usefixtures("stub_sun_integration")


def _dump(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _identifier(device: dr.DeviceEntry | None) -> list | None:
    if device is None:
        return None
    return sorted(list(identifier) for identifier in device.identifiers)[0]


async def test_generate(hass, hass_storage):
    async_mock_service(hass, "cover", "set_cover_position")
    entries, _rows, _areas = load_live_house(hass, disabled=True, floors=True)
    windows = [entry for entry in entries if entry["role"] == "window"]
    first = hass.config_entries.async_get_entry(windows[0]["entry_id"])
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()

    held = windows[HELD]["options"][CONF_ENTITIES][0]
    handle = WindowHandle(hass, held)
    await hass.services.async_call(
        DOMAIN,
        "hold",
        {"entity_id": handle.entity_id("mode"), "duration": dt.timedelta(hours=1)},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": windows[EDITED]["entry_id"], CONF_SUNSET_POS: 42},
        blocking=True,
    )
    await hass.async_block_till_done()

    result = await consolidate_via_repair(hass)
    assert result["type"] == "create_entry", result
    house = next(
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    )
    assert (house.version, house.minor_version) == (2, 1)

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    devices = [
        device
        for device in dev_reg.devices.values()
        if any(domain == DOMAIN for domain, _ in device.identifiers)
    ]
    rows = [row for row in ent_reg.entities.values() if row.platform == DOMAIN]

    expected: dict = {"windows": {}}
    for window in windows:
        key = window["entry_id"]
        (cover,) = window["options"][CONF_ENTITIES]
        handle = WindowHandle(hass, cover)
        mode = handle.state("mode")
        expected["windows"][key] = {
            "title": window["title"],
            "cover": cover,
            "settings": await window_settings(hass, key),
            "provenance": handle.attributes.get("provenance"),
            "mode": mode.state,
            "mode_until": mode.attributes.get("until"),
        }
    expected["held"] = windows[HELD]["entry_id"]
    expected["edited"] = windows[EDITED]["entry_id"]
    expected["states"] = {
        row.entity_id: {
            "state": state.state,
            "attributes": {
                k: v for k, v in state.attributes.items() if k in ("until",)
            },
        }
        for row in rows
        if row.domain == "select" and (state := hass.states.get(row.entity_id))
    }

    disabled = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.disabled_by is not None
    ]
    _dump(
        "house.json",
        {
            "house": {
                "entry_id": house.entry_id,
                "title": house.title,
                "unique_id": house.unique_id,
                "version": house.version,
                "minor_version": house.minor_version,
                "data": dict(house.data),
                "options": dict(house.options),
                "subentries": [
                    {
                        "subentry_id": subentry.subentry_id,
                        "subentry_type": subentry.subentry_type,
                        "title": subentry.title,
                        "unique_id": subentry.unique_id,
                        "data": dict(subentry.data),
                    }
                    for subentry in sorted(
                        house.subentries.values(), key=lambda s: s.title
                    )
                ],
            },
            "disabled_windows": [
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "version": entry.version,
                    "minor_version": entry.minor_version,
                    "data": dict(entry.data),
                    "options": dict(entry.options),
                }
                for entry in sorted(disabled, key=lambda e: e.entry_id)
            ],
        },
    )
    _dump(
        "registry.json",
        {
            "devices": [
                {
                    "identifier": _identifier(device),
                    "name": device.name,
                    "name_by_user": device.name_by_user,
                    "area_id": device.area_id,
                    "entry_type": device.entry_type,
                    "config_entry_id": device.config_entry_id,
                    "config_subentry_id": device.config_subentry_id,
                    "via": _identifier(
                        dev_reg.async_get(device.via_device_id)
                        if device.via_device_id
                        else None
                    ),
                }
                for device in sorted(devices, key=lambda d: _identifier(d))
            ],
            "entities": [
                {
                    "entity_id": row.entity_id,
                    "unique_id": row.unique_id,
                    "domain": row.domain,
                    "config_entry_id": row.config_entry_id,
                    "config_subentry_id": row.config_subentry_id,
                    "device": _identifier(
                        dev_reg.async_get(row.device_id) if row.device_id else None
                    ),
                    "area_id": row.area_id,
                    "name": row.name,
                    "icon": row.icon,
                    "disabled_by": row.disabled_by,
                    "hidden_by": row.hidden_by,
                    "entity_category": row.entity_category,
                    "has_entity_name": row.has_entity_name,
                    "original_name": row.original_name,
                    "translation_key": row.translation_key,
                    "labels": sorted(row.labels),
                }
                for row in sorted(rows, key=lambda r: (r.unique_id, r.domain))
            ],
        },
    )
    _dump("expected.json", expected)
    for entry in hass.config_entries.async_entries():
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
