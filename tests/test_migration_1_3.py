"""Config entry migration 1.2 -> 1.3 (P3, ADR 0002; migration.py).

On the live house snapshot (tests/fixtures/house_snapshot/, 15 windows):
every value a window reads through a code fallback is written into its
options, the cover is written as ``cover_entity_id`` next to
``group: [cover]``, the entry is keyed by its cover's registry id, and no
runtime read changes (``ShadeConfig.from_options`` before == after). The
house replay (tests/replay/) runs every window through this migration
too, and its goldens are unchanged.

An entry from before P3 with several covers keeps working and gets a
fixable "split" repair issue; fixing it gives each cover its own window.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_ENTITIES,
    CONF_TEMP_HYSTERESIS,
    DOMAIN,
)
from custom_components.adaptive_cover.migration import options_1_3
from custom_components.adaptive_cover.repairs import async_create_fix_flow
from custom_components.adaptive_cover.runtime.shade_config import ShadeConfig
from custom_components.adaptive_cover.settings.shadow import without_overrides
from custom_components.adaptive_cover.settings.spec import OPTS
from custom_components.adaptive_cover.window_cover import split_issue_id

from .test_entity_surface_v2 import _entry, _load_live_house, _set_world, _setup

SNAPSHOT = Path(__file__).parent / "fixtures" / "house_snapshot"
ENTRIES = json.loads((SNAPSHOT / "config_entries.json").read_text())["entries"]
WINDOWS = [entry for entry in ENTRIES if entry["role"] == "window"]

# What 1.3 writes into each live window: the keys it did not store, all
# written as None (the live windows store every key with a non-None
# fallback), plus the cover. The review artifact for the live house.
_PRIVACY = {"privacy_mode", "privacy_offset", "privacy_position"}
_SMOOTHING = {"max_moves_hour", "quiet_start", "quiet_end"}
_OVERHANG = {"overhang_depth", "overhang_height"}
WRITTEN: dict[str, set[str]] = {
    "Master trap": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Office north": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Office east": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Office door": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Leanne's door": _PRIVACY,
    "Leanne's south": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Den south": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Den southwest": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Den west": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Master east": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Family east": _PRIVACY | _SMOOTHING | _OVERHANG,
    "Master door": _PRIVACY | _SMOOTHING,
    "Family door": _PRIVACY | _SMOOTHING,
    "Master south": _SMOOTHING,
    "Family south": _SMOOTHING,
}

A = "cover.left"
B = "cover.right"


@pytest.fixture
def cover_calls(hass):
    """Record (and absorb) the commands the windows send."""
    return async_mock_service(hass, "cover", "set_cover_position")


def _ids(window: dict) -> str:
    return window["title"]


def _register(hass, cover: str) -> str:
    domain, object_id = cover.split(".")
    row = er.async_get(hass).async_get_or_create(
        domain, "demo", f"uid-{object_id}", suggested_object_id=object_id
    )
    return row.id


# ------------------------------------------------------ the live snapshot


def test_snapshot_has_fifteen_single_cover_windows():
    assert len(WINDOWS) == 15
    assert all(len(window["options"][CONF_ENTITIES]) == 1 for window in WINDOWS)
    assert set(WRITTEN) == {window["title"] for window in WINDOWS}


@pytest.mark.parametrize("window", WINDOWS, ids=_ids)
def test_migration_changes_no_runtime_read(window):
    before = window["options"]
    after = options_1_3(before)
    assert ShadeConfig.from_options(after) == ShadeConfig.from_options(before)


@pytest.mark.parametrize("window", WINDOWS, ids=_ids)
def test_migration_only_adds_keys(window):
    before = window["options"]
    after = options_1_3(before)
    assert {key: after[key] for key in before} == before
    (cover,) = before[CONF_ENTITIES]
    assert after[CONF_COVER_ENTITY] == cover
    written = {key: after[key] for key in after.keys() - before.keys()}
    assert written.pop(CONF_COVER_ENTITY) == cover
    # An option newer than the snapshot: its fallback, 0 (no hysteresis).
    assert written.pop(CONF_TEMP_HYSTERESIS) == 0
    assert set(written) == WRITTEN[window["title"]]
    assert set(written.values()) == {None}
    # every spec option is now stored: nothing a later layer resolves
    # (P5) falls back to a spec default
    assert {opt.key for opt in OPTS} <= set(after)


async def test_live_house_migrates_to_1_3(hass, cover_calls):
    entries, _rows, _areas = _load_live_house(hass)
    await _setup(hass, hass.config_entries.async_get_entry(WINDOWS[0]["entry_id"]))
    ent_reg = er.async_get(hass)

    for window in WINDOWS:
        entry = hass.config_entries.async_get_entry(window["entry_id"])
        assert entry.state is ConfigEntryState.LOADED, entry.title
        assert (entry.version, entry.minor_version) == (1, 5), entry.title
        # 1.4 only adds the window's lifted overrides (tests/test_shadow_settings.py)
        assert without_overrides(entry.options) == options_1_3(window["options"]), (
            entry.title
        )
        (cover,) = window["options"][CONF_ENTITIES]
        # rollback: older versions still find the cover in group
        assert entry.options[CONF_ENTITIES] == [cover]
        assert entry.options[CONF_COVER_ENTITY] == cover
        assert entry.unique_id == ent_reg.async_get(cover).id, entry.title

    (hub,) = (entry for entry in entries if entry["role"] == "hub")
    hub_entry = hass.config_entries.async_get_entry(hub["entry_id"])
    assert hub_entry.minor_version == 5
    # the hub is not a window: its leftover options stay as they were; 1.4
    # adds only the lifted layers
    assert {key: hub_entry.options[key] for key in hub["options"]} == hub["options"]
    assert set(hub_entry.options) - set(hub["options"]) == {
        "house",
        "temperature_unit",
        "floors",
        "areas",
    }
    # one cover per window already: nothing to split. (P7: the house is
    # offered the move to subentries, the only issue it has.)
    assert [
        issue.translation_key
        for (domain, _id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ] == ["consolidate_house"]


# ------------------------------------------------------ multi-cover entries


async def _split_issue(hass, entry):
    return ir.async_get(hass).async_get_issue(DOMAIN, split_issue_id(entry.entry_id))


async def _run_fix(hass, issue):
    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    flow.issue_id = issue.issue_id
    result = await flow.async_step_init()
    assert result["type"] is FlowResultType.FORM
    placeholders = result["description_placeholders"]
    result = await flow.async_step_confirm({})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return placeholders


def _windows_by_cover(hass) -> dict[str, list]:
    windows: dict[str, list] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("is_hub"):
            continue
        for cover in entry.options[CONF_ENTITIES]:
            windows.setdefault(cover, []).append(entry)
    return windows


async def test_multi_cover_entry_keeps_working_with_a_split_issue(hass, cover_calls):
    _set_world(hass)
    _register(hass, A)
    entry = _entry(hass, "Room", covers=(A, B), minor_version=2)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 5
    assert entry.options[CONF_ENTITIES] == [A, B]  # still drives both
    assert CONF_COVER_ENTITY not in entry.options
    assert entry.unique_id is None
    issue = await _split_issue(hass, entry)
    assert issue is not None
    assert issue.is_fixable
    assert issue.translation_key == "split_window"
    assert issue.translation_placeholders == {"window": "Room", "covers": f"{A}, {B}"}


async def test_split_gives_each_cover_its_own_window(hass, cover_calls):
    _set_world(hass)
    ids = {cover: _register(hass, cover) for cover in (A, B)}
    hass.states.async_set(B, "open", {"current_position": 60, "friendly_name": "Right"})
    entry = _entry(hass, "Room", covers=(A, B), minor_version=2, **{CONF_AZIMUTH: 222})
    await _setup(hass, entry)

    placeholders = await _run_fix(hass, await _split_issue(hass, entry))

    assert placeholders["kept"] == A
    assert placeholders["new_windows"] == B
    windows = _windows_by_cover(hass)
    assert [w.entry_id for w in windows[A]] == [entry.entry_id]
    (new,) = windows[B]
    assert new.title == "Right"  # named after its cover
    assert new.options[CONF_AZIMUTH] == 222  # a copy of the settings
    assert new.options[CONF_COVER_ENTITY] == B
    assert new.state is ConfigEntryState.LOADED
    assert entry.options[CONF_COVER_ENTITY] == A
    assert (entry.unique_id, new.unique_id) == (ids[A], ids[B])
    assert await _split_issue(hass, entry) is None


async def test_split_drops_a_cover_another_window_drives(hass, cover_calls):
    _set_world(hass)
    other = _entry(hass, "Other", covers=(B,), minor_version=3)
    entry = _entry(hass, "Room", covers=(A, B), minor_version=2)
    await _setup(hass, entry)

    placeholders = await _run_fix(hass, await _split_issue(hass, entry))

    assert placeholders["dropped"] == B
    windows = _windows_by_cover(hass)
    assert [w.entry_id for w in windows[A]] == [entry.entry_id]
    assert [w.entry_id for w in windows[B]] == [other.entry_id]


async def test_removing_a_multi_cover_entry_clears_its_issue(hass, cover_calls):
    _set_world(hass)
    entry = _entry(hass, "Room", covers=(A, B), minor_version=2)
    await _setup(hass, entry)
    assert await _split_issue(hass, entry) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert await _split_issue(hass, entry) is None


async def test_two_windows_on_one_cover_keep_one_unique_id(hass, cover_calls):
    """The first window keeps the cover's id; the second loads without one."""
    _set_world(hass)
    registry_id = _register(hass, A)
    first = _entry(hass, "First", covers=(A,), minor_version=2)
    second = _entry(hass, "Second", covers=(A,), minor_version=2)
    await _setup(hass, first)

    assert {first.unique_id, second.unique_id} == {registry_id, None}
    assert first.state is second.state is ConfigEntryState.LOADED
