"""Updating the live house from v2.0 to v2.1 (P8, ADR 0007; upgrade.py).

From the live house as v2.0.x consolidated it (tests/fixtures/
consolidated_v2_0: the house at 2.1 with its 15 window subentries stored
verbatim, the hidden switch aliases, the hub's leftover options, one
window held and one with an edit made after the P5 flip), the first start
on v2.1 migrates the house to 3.1, and on to 3.2 (one Climate switch:
``climate_mode`` leaves the settings; every live window had it on, so
none gets ``ignore_climate``):

- nothing a person sees changes: every kept entity's registry row (entity
  id, unique_id, name, area, device, visibility, category, subentry),
  every device (name, area, subentry, via), each window's resolved
  settings and provenance, its Mode and its hold;
- each window subentry stores only what it uses (the 3.1 record), the 60
  switch alias rows are gone, the house options keep only the layers;
- a snapshot of what changed is written once; a second start changes
  nothing; a migration that stopped part way finishes.

A house v2.0.x consolidated part way (a window entry left) finishes the
move at the first start, then migrates (ADR 0008; the live house's own
path from v1.19.x is tests/test_upgrade_from_1_19.py). A window v2.0 never
ran (no layered settings of its own) refuses the migration: the house
stays 2.1, nothing is written, and there is no nag.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache,
)

from custom_components.adaptive_cover.const import DOMAIN
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID
from custom_components.adaptive_cover.settings.window_record import (
    record_from_v2_0,
)

from .consolidated_house import fixture_json, load_consolidated_house
from .window_handle import WindowHandle, window_settings

WINDOW_COUNT = 15
ALIASES = (
    "Toggle Control",
    "Manual Override",
    "Climate Mode",
    "Outside Temperature",
    "Lux",
    "Irradiance",
)
RECORD_KEYS = {
    "window_key",
    "name",
    "cover_entity_id",
    "cover_type",
    "geometry",
    "overrides",
}

pytestmark = pytest.mark.usefixtures("stub_sun_integration")


@pytest.fixture(autouse=True)
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload the house (its polling aggregate cover) after each test."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _expected() -> dict[str, Any]:
    return fixture_json("expected.json")


def _is_alias(row: er.RegistryEntry) -> bool:
    return (
        row.domain == "switch"
        and any(row.unique_id.endswith(f"_{suffix}") for suffix in ALIASES)
        and not row.unique_id.startswith(HUB_UNIQUE_ID)
    )


def _row_view(row: er.RegistryEntry, devices: dict[str, Any]) -> tuple:
    """What a person sees of an entity, and where it belongs."""
    return (
        row.entity_id,
        row.unique_id,
        row.name,
        row.icon,
        row.area_id,
        row.disabled_by,
        row.hidden_by,
        row.entity_category,
        frozenset(row.labels),
        row.has_entity_name,
        row.original_name,
        row.translation_key,
        row.config_entry_id,
        row.config_subentry_id,
        devices.get(row.device_id),
    )


def _devices(hass) -> dict[str, Any]:
    """Every adaptive_cover device (all on the house), by id: identity and placement."""
    dev_reg = dr.async_get(hass)
    house = next(
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    )
    found: dict[str, Any] = {}
    for device in dr.async_entries_for_config_entry(dev_reg, house.entry_id):
        keys = sorted(value for domain, value in device.identifiers if domain == DOMAIN)
        if not keys:
            continue
        via = dev_reg.async_get(device.via_device_id) if device.via_device_id else None
        found[device.id] = (
            keys[0],
            device.name,
            device.name_by_user,
            device.area_id,
            device.config_entry_id,
            device.config_subentry_id,
            sorted(value for _d, value in via.identifiers) if via else None,
        )
    return found


def _rows(hass) -> dict[str, tuple]:
    devices = _devices(hass)
    return {
        f"{row.unique_id}#{row.domain}": _row_view(row, devices)
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN
    }


def _seed_modes(hass, held_until: dt.datetime) -> None:
    """Restore each Mode select as v2.0 left it (the held window's hold runs on)."""
    expected = _expected()
    held = expected["held"]
    states = []
    for entity_id, state in expected["states"].items():
        attributes = dict(state["attributes"])
        row = er.async_get(hass).async_get(entity_id)
        if row is not None and row.unique_id == f"{held}_mode_select":
            attributes["until"] = dt_util.as_local(held_until).isoformat()
        states.append(State(entity_id, state["state"], attributes))
    mock_restore_cache(hass, states)


async def _start(hass, house: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(house.entry_id)
    await hass.async_block_till_done()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _as_3_2(settings: dict[str, Any]) -> dict[str, Any]:
    """v2.0's resolved settings as 3.2 shows them: one Climate switch.

    ``climate_mode`` is no setting; every live window had it on, so each
    one reads ``ignore_climate`` False and acts on what it did.
    """
    assert settings["climate_mode"] is True
    migrated = {k: v for k, v in settings.items() if k != "climate_mode"}
    return {**migrated, "ignore_climate": False}


def _house_3_2(values: dict[str, Any]) -> dict[str, Any]:
    """v2.0's house profile without ``climate_mode`` (migration 3.2)."""
    return {k: v for k, v in values.items() if k != "climate_mode"}


# ------------------------------------------------------------ the upgrade


async def test_consolidated_live_house_upgrades_with_nothing_a_person_sees_changed(
    hass, hass_storage
):
    house = load_consolidated_house(hass)
    before = _rows(hass)
    devices_before = sorted(_devices(hass).values())
    held_until = dt_util.utcnow().replace(microsecond=0) + dt.timedelta(hours=1)
    _seed_modes(hass, held_until)
    v2_0_subentries = {
        subentry_id: dict(subentry.data)
        for subentry_id, subentry in house.subentries.items()
    }

    await _start(hass, house)

    assert house.state is ConfigEntryState.LOADED
    assert (house.version, house.minor_version) == (3, 2)
    # The house options keep only the layers (without climate_mode, 3.2).
    assert set(house.options) == {"house", "floors", "areas", "temperature_unit"}
    assert house.options["house"] == _house_3_2(
        fixture_json("house.json")["house"]["options"]["house"]
    )
    # Each window subentry stores only what it uses.
    assert len(house.subentries) == WINDOW_COUNT
    for subentry_id, subentry in house.subentries.items():
        assert set(subentry.data) == RECORD_KEYS, subentry.title
        assert "group" not in subentry.data["geometry"]
        assert (
            subentry.data
            == record_from_v2_0(v2_0_subentries[subentry_id], subentry_id).as_data()
        )
    # The switch aliases are gone; every other row and device is unchanged.
    after = _rows(hass)
    aliases = {
        uid
        for uid in before
        if uid.endswith("#switch") and not uid.startswith(HUB_UNIQUE_ID)
    }
    assert len(aliases) == 60
    assert not aliases & set(after)
    assert after == {uid: view for uid, view in before.items() if uid not in aliases}
    assert sorted(_devices(hass).values()) == devices_before

    # Each window acts on exactly what it acted on in v2.0, in the same Mode.
    expected = _expected()
    for key, was in expected["windows"].items():
        handle = WindowHandle(hass, was["cover"])
        assert handle.window_key == key
        assert handle.available, was["title"]
        assert _jsonable(await window_settings(hass, key)) == _as_3_2(
            was["settings"]
        ), was["title"]
        assert handle.attributes.get("provenance") == was["provenance"]
        if key == expected["held"]:
            assert handle.mode == "hold"
            assert handle.hold_until == dt_util.as_local(held_until).isoformat()
        else:
            assert handle.mode == was["mode"]
    # The edit made after the P5 flip survives.
    edited = await window_settings(hass, expected["edited"])
    assert edited["sunset_position"] == 42

    # The snapshot of what changed, written once.
    snapshot = hass_storage["adaptive_cover.v2_0_snapshot"]["data"]
    assert snapshot["house"]["version"] == 2
    assert len(snapshot["house"]["subentries"]) == WINDOW_COUNT
    assert len(snapshot["removed_entities"]) == 60
    # The 3 disabled "SE" window entries drive nothing: no nag.
    assert ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first") is None


async def test_the_upgraded_house_restarts_unchanged(hass, hass_storage):
    house = load_consolidated_house(hass)
    await _start(hass, house)
    rows = _rows(hass)
    subentries = {sid: dict(s.data) for sid, s in house.subentries.items()}
    snapshot = hass_storage["adaptive_cover.v2_0_snapshot"]
    await hass.config_entries.async_reload(house.entry_id)
    await hass.async_block_till_done()
    assert house.state is ConfigEntryState.LOADED
    assert _rows(hass) == rows
    assert {sid: dict(s.data) for sid, s in house.subentries.items()} == subentries
    assert hass_storage["adaptive_cover.v2_0_snapshot"] is snapshot


async def test_a_migration_that_stopped_part_way_finishes(hass):
    """A crash after some subentries were rewritten: the next start finishes."""
    house = load_consolidated_house(hass)
    rewritten = list(house.subentries.values())[:5]
    for subentry in rewritten:
        record = record_from_v2_0(subentry.data, subentry.subentry_id)
        hass.config_entries.async_update_subentry(
            house, subentry, data=record.as_data()
        )
    await _start(hass, house)
    assert (house.version, house.minor_version) == (3, 2)
    expected = _expected()
    for key, was in expected["windows"].items():
        assert _jsonable(await window_settings(hass, key)) == _as_3_2(was["settings"])


# ------------------------------------------------------------ the nag


def _entries(hass) -> dict[str, tuple]:
    return {
        entry.entry_id: (
            entry.version,
            entry.minor_version,
            dict(entry.data),
            dict(entry.options),
            {sid: dict(s.data) for sid, s in entry.subentries.items()},
        )
        for entry in hass.config_entries.async_entries(DOMAIN)
    }


async def test_a_house_consolidated_part_way_on_2_0_finishes_at_the_first_start(
    hass,
):
    """A window entry v2.0.x did not move yet: v2.1 moves it, then migrates."""
    house = load_consolidated_house(hass)
    template = next(iter(house.subentries.values())).data
    left = MockConfigEntry(
        domain=DOMAIN,
        title="Left behind",
        data={"name": "Left behind", "sensor_type": "cover_blind"},
        options={
            **{k: v for k, v in template["options"].items() if k != "overrides"},
            "group": ["cover.left_behind"],
            "cover_entity_id": "cover.left_behind",
        },
        version=1,
        minor_version=5,
    )
    left.add_to_hass(hass)
    hass.states.async_set("cover.left_behind", "open", {"current_position": 100})
    v2_0_subentries = {sid: dict(s.data) for sid, s in house.subentries.items()}

    await _start(hass, house)

    assert house.state is ConfigEntryState.LOADED
    assert (house.version, house.minor_version) == (3, 2)
    assert hass.config_entries.async_get_entry(left.entry_id) is None
    assert len(house.subentries) == WINDOW_COUNT + 1
    for subentry_id, data in v2_0_subentries.items():
        assert (
            house.subentries[subentry_id].data
            == record_from_v2_0(data, subentry_id).as_data()
        )
    moved = WindowHandle(hass, "cover.left_behind")
    assert moved.window_key == left.entry_id
    assert moved.available
    assert ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first") is None


async def test_a_window_v2_0_never_ran_refuses_the_migration(hass, caplog):
    """No layered settings of its own: the house stays 2.1, without the nag."""
    house = load_consolidated_house(hass)
    subentry = next(iter(house.subentries.values()))
    data = dict(subentry.data)
    data["options"] = {k: v for k, v in data["options"].items() if k != "overrides"}
    hass.config_entries.async_update_subentry(house, subentry, data=data)
    stored = _entries(hass)

    await _start(hass, house)

    assert house.state is ConfigEntryState.SETUP_ERROR
    assert "could not be updated" in (house.reason or "")
    assert _entries(hass) == stored
    assert subentry.title in caplog.text
    assert ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first") is None
