"""Updating the live house from v1.19.x straight to v2.1 (ADR 0008; consolidate.py).

From the live house as v1.19.x runs it (tests/v1_19_house.py: 15 window
entries and the lifted hub at 1.5, the hidden switch aliases, one window
held, one with an edit v1.19.x stored in the flat option only), the first
start of v2.1 moves every window into the house and migrates it to 3.1,
with no click:

- nothing a person sees changes: every kept entity's registry row (id,
  entity_id, unique_id, name, area, device, visibility, category), every
  device (id, name, area), each window's resolved settings and provenance
  (what v2.0 showed for the same house: tests/fixtures/consolidated_v2_0),
  its Mode and its hold;
- the window entries are gone, the house is 3.1 with a subentry per
  window, the 60 switch alias rows are removed (P8), the disabled "SE"
  entries are left alone; a snapshot is written once and a notification
  says what was done, each phase logged at INFO;
- a start after a crash part way resumes and finishes;
- a verification that fails removes nothing: every entry, row and device
  is back as v1.19.x left it, the house keeps its version, and the
  ``upgrade_stopped`` repair says why. A row Home Assistant removed while
  moving asks for the backup instead.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    mock_restore_cache,
)

from custom_components.adaptive_cover import consolidate
from custom_components.adaptive_cover.const import DOMAIN
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID

from .consolidated_house import fixture_json
from .live_house import load_live_house
from .v1_19_house import EDIT_VALUE, load_v1_19_house
from .window_handle import WindowHandle, window_settings

WINDOW_COUNT = 15
ALIAS_COUNT = 60
RECORD_KEYS = {
    "window_key",
    "name",
    "cover_entity_id",
    "cover_type",
    "geometry",
    "overrides",
}
LAYER_KEYS = {"house", "floors", "areas", "temperature_unit"}

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


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _is_alias(uid: str) -> bool:
    return uid.endswith("#switch") and not uid.startswith(HUB_UNIQUE_ID)


def _devices(hass) -> dict[str, tuple]:
    """Every adaptive_cover device by id: what a person sees of it."""
    dev_reg = dr.async_get(hass)
    found = {}
    for device in dev_reg.devices.values():
        keys = sorted(value for domain, value in device.identifiers if domain == DOMAIN)
        if keys:
            found[device.id] = (
                device.id,
                keys[0],
                device.name,
                device.name_by_user,
                device.area_id,
            )
    return found


def _rows(hass) -> dict[str, tuple]:
    """Every adaptive_cover entity row: what a person sees of it (registry ids too)."""
    devices = _devices(hass)
    return {
        f"{row.unique_id}#{row.domain}": (
            row.id,
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
            devices.get(row.device_id),
        )
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN
    }


def _placement(hass) -> dict[str, tuple]:
    """Where every row and device belongs (config entry, subentry, via)."""
    dev_reg = dr.async_get(hass)
    rows = {
        f"row {row.unique_id}#{row.domain}": (
            row.config_entry_id,
            row.config_subentry_id,
            row.device_id,
        )
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN
    }
    devices = {
        f"device {device.id}": (
            device.config_entry_id,
            device.config_subentry_id,
            device.via_device_id,
        )
        for device in dev_reg.devices.values()
        if any(domain == DOMAIN for domain, _ in device.identifiers)
    }
    return rows | devices


def _entries(hass) -> dict[str, tuple]:
    return {
        entry.entry_id: (
            entry.version,
            entry.minor_version,
            entry.unique_id,
            dict(entry.data),
            dict(entry.options),
            {sid: dict(s.data) for sid, s in entry.subentries.items()},
        )
        for entry in hass.config_entries.async_entries(DOMAIN)
    }


def _seed_restore(hass, held_until: dt.datetime) -> None:
    """Restore each Mode select as v1.19.x left it (the held window's hold runs on)."""
    expected = _expected()
    states = []
    for entity_id, state in expected["states"].items():
        attributes = dict(state["attributes"])
        row = er.async_get(hass).async_get(entity_id)
        if row is not None and row.unique_id == f"{expected['held']}_mode_select":
            attributes["until"] = dt_util.as_local(held_until).isoformat()
        states.append(State(entity_id, state["state"], attributes))
    mock_restore_cache(hass, states)


async def _start(hass, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _notifications(hass, hass_ws_client) -> dict[str, dict[str, Any]]:
    assert await async_setup_component(hass, "persistent_notification", {})
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "persistent_notification/get"})
    result = await client.receive_json()
    assert result["success"], result
    return {item["notification_id"]: item for item in result["result"]}


async def _assert_upgraded(hass, house, *, before, devices_before, held_until) -> None:
    """The house is 3.1 and holds every window; nothing a person sees changed."""
    assert house.state is ConfigEntryState.LOADED
    assert (house.version, house.minor_version) == (3, 1)
    assert set(house.options) == LAYER_KEYS
    # Every window entry is gone; the disabled ones are left alone.
    left = [e for e in hass.config_entries.async_entries(DOMAIN) if e is not house]
    assert len(left) == 3
    assert all(e.disabled_by is not None for e in left)
    # One subentry per window, in the 3.1 shape, keyed by the old entry_id.
    assert len(house.subentries) == WINDOW_COUNT
    expected = _expected()
    keys = {subentry.data["window_key"] for subentry in house.subentries.values()}
    assert keys == set(expected["windows"])
    for subentry in house.subentries.values():
        assert set(subentry.data) == RECORD_KEYS, subentry.title
        assert (
            subentry.title == expected["windows"][subentry.data["window_key"]]["title"]
        )
    # Every row and device a person sees is unchanged (the 60 aliases go).
    after = _rows(hass)
    aliases = {uid for uid in before if _is_alias(uid)}
    assert len(aliases) == ALIAS_COUNT
    assert after == {uid: view for uid, view in before.items() if uid not in aliases}
    assert _devices(hass) == devices_before
    # ... and belongs to the house and its window's subentry.
    subentry_of = {
        subentry.data["window_key"]: subentry.subentry_id
        for subentry in house.subentries.values()
    }
    for row in er.async_get(hass).entities.values():
        if row.platform != DOMAIN:
            continue
        assert row.config_entry_id == house.entry_id, row.entity_id
        key = row.unique_id.split("_", 1)[0]
        assert row.config_subentry_id == subentry_of.get(key), row.entity_id
    # Each window acts on what it acted on, in the same Mode.
    for key, was in expected["windows"].items():
        handle = WindowHandle(hass, was["cover"])
        assert handle.window_key == key
        assert handle.available, was["title"]
        assert _jsonable(await window_settings(hass, key)) == was["settings"], was[
            "title"
        ]
        assert handle.attributes.get("provenance") == was["provenance"], was["title"]
        if key == expected["held"]:
            assert handle.mode == "hold"
            assert handle.hold_until == dt_util.as_local(held_until).isoformat()
        else:
            assert handle.mode == was["mode"]
    # The edit v1.19.x stored in the flat option survives.
    edited = await window_settings(hass, expected["edited"])
    assert edited["sunset_position"] == EDIT_VALUE


# ------------------------------------------------------------ the upgrade


async def test_live_house_upgrades_from_1_19_in_one_start(
    hass, hass_storage, hass_ws_client, caplog
):
    caplog.set_level("INFO", logger="custom_components.adaptive_cover")
    hub, windows = load_v1_19_house(hass)
    before = _rows(hass)
    devices_before = _devices(hass)
    held_until = dt_util.utcnow().replace(microsecond=0) + dt.timedelta(hours=1)
    _seed_restore(hass, held_until)

    await _start(hass, hub)

    await _assert_upgraded(
        hass,
        hub,
        before=before,
        devices_before=devices_before,
        held_until=held_until,
    )
    # A snapshot of the 1.x house, written once; the 2.0 one after it.
    snapshot = hass_storage["adaptive_cover.v1_snapshot"]["data"]
    assert snapshot["house"]["version"] == 1
    assert len(snapshot["windows"]) == WINDOW_COUNT + 3
    stored = {f"{row['unique_id']}#{row['domain']}" for row in snapshot["entities"]}
    assert stored == set(before)
    assert all(row["config_subentry_id"] is None for row in snapshot["entities"]), (
        "the snapshot shows the house before anything moved"
    )
    assert "adaptive_cover.v2_0_snapshot" in hass_storage
    # Each phase is logged; a notification says what was done.
    for phase in range(1, 7):
        assert f"Upgrade phase {phase}" in caplog.text
    notices = await _notifications(hass, hass_ws_client)
    notice = notices[consolidate.NOTIFICATION_ID]
    assert (
        f"upgraded your {WINDOW_COUNT} windows into one house entry"
        in notice["message"]
    )
    assert "Nothing changed" in notice["message"]
    assert "adaptive_cover.v1_snapshot" in notice["message"]
    assert "Leanne's south" in notice["message"]  # its edit was kept
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, consolidate.STOPPED_ISSUE) is None
    assert registry.async_get_issue(DOMAIN, "consolidate_first") is None


async def test_the_upgraded_house_restarts_unchanged(hass, hass_storage):
    hub, _windows = load_v1_19_house(hass)
    await _start(hass, hub)
    rows = _rows(hass)
    stored = _entries(hass)
    snapshot = hass_storage["adaptive_cover.v1_snapshot"]
    await hass.config_entries.async_reload(hub.entry_id)
    await hass.async_block_till_done()
    assert hub.state is ConfigEntryState.LOADED
    assert _rows(hass) == rows
    assert _entries(hass) == stored
    assert hass_storage["adaptive_cover.v1_snapshot"] is snapshot


class _Crash(BaseException):
    """A restart part way: nothing after it runs, nothing is undone."""


async def test_a_crash_part_way_resumes_at_the_next_start(hass, hass_storage):
    """The power goes out between a window's entity moves and its device move."""
    hub, windows = load_v1_19_house(hass)
    before = _rows(hass)
    devices_before = _devices(hass)
    held_until = dt_util.utcnow().replace(microsecond=0) + dt.timedelta(hours=1)
    _seed_restore(hass, held_until)
    plan = consolidate.upgrade_plan(hass, hub, windows)
    victim = plan.windows[5].window_key
    real_update = dr.DeviceRegistry.async_update_device

    def crash_on_victim(self, device_id, **changes):
        device = self.async_get(device_id)
        if (
            changes.get("new_config_entry_id")
            and (DOMAIN, victim) in device.identifiers
        ):
            raise _Crash
        return real_update(self, device_id, **changes)

    with (
        patch.object(dr.DeviceRegistry, "async_update_device", crash_on_victim),
        pytest.raises(_Crash),
    ):
        await consolidate.async_upgrade_house(hass, hub, windows)

    # Five windows moved and one half-moved; nothing was removed or bumped.
    assert (hub.version, hub.minor_version) == (1, 5)
    assert len(hub.subentries) == 6
    assert all(hass.config_entries.async_get_entry(w.entry_id) for w in windows)
    victim_rows = [
        row
        for row in er.async_get(hass).entities.values()
        if row.unique_id.startswith(f"{victim}_")
    ]
    assert victim_rows
    assert all(row.config_entry_id == hub.entry_id for row in victim_rows)

    await _start(hass, hub)

    await _assert_upgraded(
        hass,
        hub,
        before=before,
        devices_before=devices_before,
        held_until=held_until,
    )


async def test_a_failed_verification_removes_nothing(hass, hass_storage, caplog):
    """A device that does not move: the moves are undone, v1.19.x runs the house."""
    hub, windows = load_v1_19_house(hass)
    before = _rows(hass)
    placement = _placement(hass)
    stored = _entries(hass)
    stuck = windows[7].entry_id
    real_update = dr.DeviceRegistry.async_update_device

    def device_stays(self, device_id, **changes):
        device = self.async_get(device_id)
        if (
            changes.get("new_config_entry_id") == hub.entry_id
            and (DOMAIN, stuck) in device.identifiers
        ):
            return device  # Home Assistant did not move it
        return real_update(self, device_id, **changes)

    with patch.object(dr.DeviceRegistry, "async_update_device", device_stays):
        await _start(hass, hub)

    # Nothing removed, no version changed, every row and device back in place.
    assert _entries(hass) == stored
    assert _rows(hass) == before
    assert _placement(hass) == placement
    assert hub.state is ConfigEntryState.SETUP_ERROR
    assert "upgrade into the house stopped" in (hub.reason or "")
    for window in windows:
        assert window.state is not ConfigEntryState.LOADED
    issue = ir.async_get(hass).async_get_issue(DOMAIN, consolidate.STOPPED_ISSUE)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_key == consolidate.STOPPED_ISSUE
    assert "not moved" in issue.translation_placeholders["reason"]
    assert "Upgrade phase 6" not in caplog.text
    assert not hass.states.async_entity_ids("select")


async def test_a_row_lost_while_moving_asks_for_the_backup(hass, hass_storage):
    """Home Assistant removed a row while it moved: only the backup restores it."""
    hub, windows = load_v1_19_house(hass)
    stored = _entries(hass)
    victim = windows[2].entry_id
    ent_reg = er.async_get(hass)
    real_update = dr.DeviceRegistry.async_update_device

    def drops_a_row(self, device_id, **changes):
        device = self.async_get(device_id)
        if (
            changes.get("new_config_entry_id") == hub.entry_id
            and (DOMAIN, victim) in device.identifiers
        ):
            row = next(
                r
                for r in er.async_entries_for_device(ent_reg, device_id)
                if r.domain == "sensor"
            )
            ent_reg.async_remove(row.entity_id)
        return real_update(self, device_id, **changes)

    with patch.object(dr.DeviceRegistry, "async_update_device", drops_a_row):
        await _start(hass, hub)

    assert _entries(hass) == stored  # nothing removed, no version changed
    issue = ir.async_get(hass).async_get_issue(DOMAIN, consolidate.STOPPED_ISSUE)
    assert issue is not None
    assert issue.translation_key == f"{consolidate.STOPPED_ISSUE}_restore_backup"
    assert "removed while moving" in issue.translation_placeholders["reason"]
    assert hub.state is ConfigEntryState.SETUP_ERROR


# ------------------------------------------------------------ older houses


async def test_a_house_at_1_2_is_brought_to_1_5_then_moved(hass):
    """A house v1.18 never lifted: the upgrade runs 1.3, the lift and 1.5 itself."""
    entries, _rows_1x, _areas = load_live_house(hass, disabled=True, floors=True)
    for stored in entries:
        entry = hass.config_entries.async_get_entry(stored["entry_id"])
        hass.config_entries.async_update_entry(entry, minor_version=2)
    hub = next(e for e in entries if e["role"] == "hub")
    house = hass.config_entries.async_get_entry(hub["entry_id"])

    await _start(hass, house)

    assert house.state is ConfigEntryState.LOADED
    assert (house.version, house.minor_version) == (3, 1)
    assert len(house.subentries) == WINDOW_COUNT
    # Every window acts on what v2.0 showed for the same house (the edit
    # and the hold aside, which this house never had).
    expected = _expected()
    for key, was in expected["windows"].items():
        if key == expected["edited"]:
            continue
        assert _jsonable(await window_settings(hass, key)) == was["settings"], was[
            "title"
        ]


async def test_a_house_older_than_1_2_stops_and_changes_nothing(hass):
    """Entries stored before 1.2: the upgrade stops before writing anything."""
    entries, _rows_1x, _areas = load_live_house(hass, disabled=True, floors=True)
    stored = _entries(hass)
    rows = _rows(hass)
    hub = next(e for e in entries if e["role"] == "hub")

    await _start(hass, hass.config_entries.async_get_entry(hub["entry_id"]))

    assert _entries(hass) == stored
    assert _rows(hass) == rows
    issue = ir.async_get(hass).async_get_issue(DOMAIN, consolidate.STOPPED_ISSUE)
    assert issue is not None
    assert "older than 1.2" in issue.translation_placeholders["reason"]
    assert ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first") is None
    assert not hass.states.async_entity_ids("select")


async def test_a_window_entry_enabled_after_the_upgrade_gets_the_nag(hass):
    """ADR 0007 stands for a 3.x house: an old window entry enabled again."""
    hub, _windows = load_v1_19_house(hass)
    await _start(hass, hub)
    assert (hub.version, hub.minor_version) == (3, 1)
    stored = _entries(hass)
    old = next(e for e in hass.config_entries.async_entries(DOMAIN) if e.disabled_by)

    await hass.config_entries.async_set_disabled_by(old.entry_id, None)
    await hass.async_block_till_done()

    assert old.state is ConfigEntryState.SETUP_ERROR
    assert "not in the house yet" in (old.reason or "")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first")
    assert issue is not None
    assert issue.translation_placeholders["windows"] == old.title
    # The house keeps running and nothing is written.
    assert hub.state is ConfigEntryState.LOADED
    assert {k: v for k, v in _entries(hass).items() if k != old.entry_id} == {
        k: v for k, v in stored.items() if k != old.entry_id
    }


async def test_window_entries_of_a_disabled_house_get_the_nag(hass):
    """No enabled house to move them into: ADR 0007's nag, nothing written."""
    hub, windows = load_v1_19_house(hass)
    await hass.config_entries.async_set_disabled_by(
        hub.entry_id, ConfigEntryDisabler.USER
    )
    stored = _entries(hass)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert windows[0].state is ConfigEntryState.SETUP_ERROR
    assert "not in the house yet" in (windows[0].reason or "")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_first")
    assert issue is not None
    assert issue.translation_placeholders["count"] == str(WINDOW_COUNT)
    assert _entries(hass) == stored


async def test_an_unexpected_error_while_moving_is_undone(hass, hass_storage):
    """Home Assistant raises mid-move: the moves are undone, nothing removed."""
    hub, windows = load_v1_19_house(hass)
    before = _rows(hass)
    placement = _placement(hass)
    stored = _entries(hass)
    victim = windows[4].entry_id
    real_update = dr.DeviceRegistry.async_update_device

    def raises_on_victim(self, device_id, **changes):
        device = self.async_get(device_id)
        if (
            changes.get("new_config_entry_id") == hub.entry_id
            and (DOMAIN, victim) in device.identifiers
        ):
            raise ValueError("registry refused")
        return real_update(self, device_id, **changes)

    with patch.object(dr.DeviceRegistry, "async_update_device", raises_on_victim):
        await _start(hass, hub)

    assert _entries(hass) == stored
    assert _rows(hass) == before
    assert _placement(hass) == placement
    issue = ir.async_get(hass).async_get_issue(DOMAIN, consolidate.STOPPED_ISSUE)
    assert issue is not None
    assert issue.translation_key == consolidate.STOPPED_ISSUE
    assert "registry refused" in issue.translation_placeholders["reason"]
