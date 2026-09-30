"""Consolidating the live house into one house entry (P7, ADR 0001).

On the sanitized live snapshot (15 window entries, the hub, the 3 disabled
"SE" entries), through the "Consolidate" repair fix flow the owner runs:

- a dry run lists what moves and changes nothing;
- the move keeps every entity_id, unique_id, name, area, device, Mode and
  hold, and every resolved setting; each window becomes a ``window``
  subentry of the house (key = its old entry_id) and its rows are
  re-parented, not recreated;
- an interrupted move (a crash after window k, then a restart) resumes,
  and a run after a finished one changes nothing;
- the house card's discovery reads the same attributes and rows.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.adaptive_cover import consolidate
from custom_components.adaptive_cover.const import (
    CONF_COVER_ENTITY,
    CONF_ENTITIES,
    CONF_SUNSET_POS,
    DOMAIN,
)
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID

from .consolidation import (
    consolidate_issue,
    consolidate_via_repair,
    open_consolidation,
)
from .live_house import load_live_house
from .window_handle import WindowHandle, window_configs, window_settings

WINDOW_COUNT = 15

pytestmark = pytest.mark.usefixtures("stub_sun_integration")


@pytest.fixture
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


async def _live_house(hass) -> tuple[list[dict], dict[str, str | None]]:
    """The live house, set up (15 windows, the hub, 3 disabled entries)."""
    entries, _rows, cover_areas = load_live_house(hass, disabled=True, floors=True)
    windows = [entry for entry in entries if entry["role"] == "window"]
    first = hass.config_entries.async_get_entry(windows[0]["entry_id"])
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    for window in windows:
        entry = hass.config_entries.async_get_entry(window["entry_id"])
        assert entry.state is ConfigEntryState.LOADED, entry.title
    return windows, cover_areas


def _house(hass):
    return next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get("is_hub")
    )


def _row_view(row: er.RegistryEntry) -> tuple:
    """What a person sees of an entity (and what must not change)."""
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
        row.id,
    )


def _device_view(device: dr.DeviceEntry) -> tuple:
    return (device.id, device.name, device.name_by_user, device.area_id)


def _adaptive_rows(hass) -> dict[str, er.RegistryEntry]:
    """Every adaptive_cover row, by "<unique_id>#<domain>".

    ("X_Manual Override" is both a switch and a binary sensor.)
    """
    return {
        f"{row.unique_id}#{row.domain}": row
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN
    }


def _window_device(hass, key: str) -> dr.DeviceEntry:
    (device,) = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, key)})
    return device


async def _capture(hass, windows: list[dict]) -> dict:
    """Everything consolidation must keep, per window and for the house."""
    rows = _adaptive_rows(hass)
    captured = {
        "rows": {uid: _row_view(row) for uid, row in rows.items()},
        "hub_rows": {
            uid: (row.entity_id, row.device_id)
            for uid, row in rows.items()
            if uid.startswith(HUB_UNIQUE_ID)
        },
        "windows": {},
    }
    for window in windows:
        key = window["entry_id"]
        (cover,) = window["options"][CONF_ENTITIES]
        handle = WindowHandle(hass, cover)
        mode = handle.state("mode")
        captured["windows"][key] = {
            "device": _device_view(_window_device(hass, key)),
            "settings": await window_settings(hass, key),
            "provenance": handle.attributes.get("provenance"),
            "mode": (mode.state, mode.attributes.get("until")),
            "manual": handle.is_manual,
            "override_until": handle.attributes.get("override_until"),
            "cover": cover,
        }
    return captured


async def _hold(hass, cover: str) -> None:
    """Hold one window for an hour through the hold service."""
    handle = WindowHandle(hass, cover)
    await hass.services.async_call(
        DOMAIN,
        "hold",
        {"entity_id": handle.entity_id("mode"), "duration": dt.timedelta(hours=1)},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert handle.mode == "hold"


def _assert_consolidated(hass, windows: list[dict], before: dict) -> None:
    """Every window is a house subentry; nothing a person sees changed."""
    house = _house(hass)
    assert (house.version, house.minor_version) == (2, 1)
    assert house.state is ConfigEntryState.LOADED
    subentries = {
        subentry.data["window_key"]: subentry
        for subentry in house.subentries.values()
        if subentry.subentry_type == "window"
    }
    assert set(subentries) == {window["entry_id"] for window in windows}
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    house_device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, HUB_UNIQUE_ID), config_entry_id=house.entry_id
    )
    rows = _adaptive_rows(hass)
    # The same rows, no more, no fewer, and nothing a person sees changed.
    assert {uid: _row_view(row) for uid, row in rows.items()} == before["rows"]
    for window in windows:
        key = window["entry_id"]
        subentry = subentries[key]
        assert hass.config_entries.async_get_entry(key) is None, window["title"]
        assert subentry.title == window["title"]
        cover = before["windows"][key]["cover"]
        assert subentry.unique_id == ent_reg.async_get(cover).id
        assert subentry.data["options"][CONF_COVER_ENTITY] == cover
        device = _window_device(hass, key)
        assert _device_view(device) == before["windows"][key]["device"]
        assert device.config_entry_id == house.entry_id
        assert device.config_subentry_id == subentry.subentry_id
        assert device.via_device_id == house_device.id
        window_rows = [row for uid, row in rows.items() if uid.startswith(f"{key}_")]
        assert window_rows, window["title"]
        for row in window_rows:
            assert row.config_entry_id == house.entry_id, row.entity_id
            assert row.config_subentry_id == subentry.subentry_id, row.entity_id
            assert row.device_id == device.id, row.entity_id
    # The hub keeps its entities and device.
    for uid, (entity_id, device_id) in before["hub_rows"].items():
        assert (rows[uid].entity_id, rows[uid].device_id) == (entity_id, device_id)
    assert consolidate_issue(hass) is None


async def _assert_same_behavior(hass, windows: list[dict], before: dict) -> None:
    """Each window runs on the same settings, Mode and hold."""
    for window in windows:
        key = window["entry_id"]
        was = before["windows"][key]
        handle = WindowHandle(hass, was["cover"])
        assert handle.window_key == key
        assert handle.attributes["window_key"] == key  # the card binding key
        assert handle.attributes["cover_entity"] == was["cover"]
        assert handle.available, window["title"]
        assert await window_settings(hass, key) == was["settings"], window["title"]
        assert handle.attributes.get("provenance") == was["provenance"]
        mode = handle.state("mode")
        assert (mode.state, mode.attributes.get("until")) == was["mode"]
        assert handle.is_manual == was["manual"]
        assert handle.attributes.get("override_until") == was["override_until"]


# ------------------------------------------------------------ the move


async def test_live_house_consolidates_with_nothing_a_person_sees_changed(
    hass, cover_calls, hass_storage
):
    windows, _areas = await _live_house(hass)
    assert len(windows) == WINDOW_COUNT
    held = windows[3]["options"][CONF_ENTITIES][0]
    await _hold(hass, held)
    # An edit made since the P5 flip lives only in the window's overrides.
    edited = windows[5]["entry_id"]
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": edited, CONF_SUNSET_POS: 42},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (await window_settings(hass, edited))[CONF_SUNSET_POS] == 42
    before = await _capture(hass, windows)
    assert before["windows"][windows[3]["entry_id"]]["mode"][0] == "hold"
    assert consolidate_issue(hass) is not None

    result = await consolidate_via_repair(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    assert sorted(result["data"]["moved"]) == sorted(w["entry_id"] for w in windows)

    _assert_consolidated(hass, windows, before)
    await _assert_same_behavior(hass, windows, before)
    # The disabled "SE" entries are left as they are.
    disabled = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.disabled_by is not None
    ]
    assert len(disabled) == 3
    # The snapshot was written once, before anything moved.
    snapshot = hass_storage["adaptive_cover.v1_snapshot"]["data"]
    assert {w["entry_id"] for w in snapshot["windows"]} >= {
        w["entry_id"] for w in windows
    }
    assert len(snapshot["entities"]) >= len(before["rows"])


async def test_window_configs_are_the_window_entries_verbatim(hass, cover_calls):
    """The subentry stores what the entry held (ADR 0006)."""
    windows, _areas = await _live_house(hass)
    stored = {
        window["entry_id"]: (
            dict(hass.config_entries.async_get_entry(window["entry_id"]).data),
            dict(hass.config_entries.async_get_entry(window["entry_id"]).options),
        )
        for window in windows
    }
    await consolidate_via_repair(hass)
    house = _house(hass)
    for subentry in house.subentries.values():
        data, options = stored[subentry.data["window_key"]]
        assert subentry.data["data"] == data
        assert subentry.data["options"] == options
    assert window_configs(hass).keys() == stored.keys()


async def test_the_dry_run_lists_what_moves_and_changes_nothing(hass, cover_calls):
    windows, _areas = await _live_house(hass)
    entries_before = {entry.entry_id for entry in hass.config_entries.async_entries()}
    rows_before = {uid: _row_view(row) for uid, row in _adaptive_rows(hass).items()}

    _flow, result = await open_consolidation(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "preview"
    placeholders = result["description_placeholders"]
    assert placeholders["count"] == str(WINDOW_COUNT)
    moving = sum(
        1
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN and not row.unique_id.startswith(HUB_UNIQUE_ID)
    )
    assert placeholders["entities"] == f"{moving}/{moving}"
    for window in windows:
        assert window["title"] in placeholders["windows"]
    assert "SE south shades" in placeholders["left_alone"]

    assert {e.entry_id for e in hass.config_entries.async_entries()} == entries_before
    assert {uid: _row_view(r) for uid, r in _adaptive_rows(hass).items()} == rows_before
    assert not _house(hass).subentries


async def test_a_backup_must_be_confirmed(hass, cover_calls):
    await _live_house(hass)
    result = await consolidate_via_repair(hass, backup=False)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "backup_required"}
    assert not _house(hass).subentries
    assert _house(hass).version == 1


async def test_a_window_with_two_covers_blocks_the_move(hass, cover_calls):
    windows, _areas = await _live_house(hass)
    entry = hass.config_entries.async_get_entry(windows[0]["entry_id"])
    second = windows[1]["options"][CONF_ENTITIES][0]
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_ENTITIES: [*entry.options[CONF_ENTITIES], second],
        },
    )
    await hass.async_block_till_done()

    _flow, result = await open_consolidation(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "blocked"
    assert "split repair" in result["description_placeholders"]["problems"]
    assert not _house(hass).subentries


# ------------------------------------------------------------ resuming


async def _restart(hass) -> None:
    """Every entry of the integration unloads and sets up again."""
    entries = hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    for entry in entries:
        if entry.disabled_by is None and entry.state is ConfigEntryState.NOT_LOADED:
            await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("crash_after", [0, 3, WINDOW_COUNT - 1])
@pytest.mark.parametrize("crash_at", ["reparent", "remove"])
async def test_an_interrupted_consolidation_resumes(
    hass, cover_calls, crash_at, crash_after
):
    """A crash after window k, then a restart: the next run finishes the move.

    The crash hits window k+1 right after its subentry was added
    (``reparent``: its rows are still on its entry), or while its entry is
    removed (``remove``: its rows and device moved already, the worst
    place). After the restart that entry runs as a window entry again (the
    house skips its pending subentry), and the second run moves the rest.
    """
    windows, _areas = await _live_house(hass)
    before = await _capture(hass, windows)
    done = 0
    step = {
        "reparent": "async_reparent_window",
        "remove": "_async_remove_legacy_entry",
    }[crash_at]
    real_step = getattr(consolidate, step)

    async def crash_after_k(*args):
        nonlocal done
        if done == crash_after:
            raise RuntimeError("power cut")
        done += 1
        await real_step(*args)

    def crash_after_k_sync(*args):
        nonlocal done
        if done == crash_after:
            raise RuntimeError("power cut")
        done += 1
        real_step(*args)

    fake = crash_after_k if crash_at == "remove" else crash_after_k_sync
    # contract: internal (crash injection inside the move)
    with (
        patch.object(consolidate, step, fake),
        pytest.raises(RuntimeError, match="power cut"),
    ):
        await consolidate.async_consolidate(hass, _house(hass))
    await hass.async_block_till_done()
    assert len(consolidate.windows_to_move(hass)) == WINDOW_COUNT - crash_after
    assert consolidate_issue(hass) is not None

    await _restart(hass)
    for entry in consolidate.windows_to_move(hass):
        assert entry.state is ConfigEntryState.LOADED, entry.title

    result = await consolidate_via_repair(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    _assert_consolidated(hass, windows, before)
    await _assert_same_behavior(hass, windows, before)

    # A run after a finished one changes nothing.
    rows = {uid: _row_view(row) for uid, row in _adaptive_rows(hass).items()}
    subentries = dict(_house(hass).subentries)
    report = await consolidate.async_consolidate(hass, _house(hass))
    assert report.moved == ()
    assert {uid: _row_view(r) for uid, r in _adaptive_rows(hass).items()} == rows
    assert dict(_house(hass).subentries) == subentries


async def test_after_consolidation_the_house_adds_windows_as_subentries(
    hass, cover_calls
):
    await _live_house(hass)
    await consolidate_via_repair(hass)
    result = await hass.config_entries.subentries.async_init(
        (_house(hass).entry_id, "window"), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    hass.config_entries.subentries.async_abort(result["flow_id"])


async def test_a_consolidated_house_survives_a_restart(hass, cover_calls):
    windows, _areas = await _live_house(hass)
    await consolidate_via_repair(hass)
    before = await _capture(hass, windows)
    await _restart(hass)
    _assert_consolidated(hass, windows, before)
    for window in windows:
        assert WindowHandle(
            hass, before["windows"][window["entry_id"]]["cover"]
        ).available


# ------------------------------------------------------------ the card


async def test_card_discovery_reads_the_same_windows(hass, cover_calls):
    """The house card finds windows by the Position sensor's window_key and
    the unique_id prefix, never by config_entry_id (card/src/lib)."""
    windows, _areas = await _live_house(hass)
    await consolidate_via_repair(hass)
    house = _house(hass)
    ent_reg = er.async_get(hass)
    for window in windows:
        key = window["entry_id"]
        (cover,) = window["options"][CONF_ENTITIES]
        position = WindowHandle(hass, cover).entity_id("position")
        state = hass.states.get(position)
        assert state.attributes["window_key"] == key
        assert state.attributes["cover_entity"] == cover
        row = ent_reg.async_get(position)
        assert row.unique_id == f"{key}_Cover Position"
        assert row.platform == DOMAIN
        # The settings link goes to the subentry (card/src/lib/settings-link).
        assert row.config_entry_id == house.entry_id
        assert house.subentries[row.config_subentry_id].data["window_key"] == key
