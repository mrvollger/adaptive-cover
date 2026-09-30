"""The house entry with window subentries (P7, ADR 0001), through public surfaces.

A fresh install starts in the house model: the add form creates the house
entry (the hub) with the window as its first ``window`` subentry. Each
window gets its own device, hanging off the house device, and its entities
are the window subentry's. Windows are added with "Add window" (the
subentry flow), changed with its Reconfigure (one-time settings and the
window's exceptions), and removed by deleting the subentry; each of these
touches that window alone. A window that cannot set up gets a repair
issue while the rest of the house runs. The house entry's options are the
house settings.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    CONF_SUNSET_POS,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    DOMAIN,
)
from custom_components.adaptive_cover.hub import HUB_UNIQUE_ID

from .window_form import add_legacy_house, sectioned, start_add, submit
from .window_handle import WindowHandle, window_configs, window_settings

pytestmark = pytest.mark.usefixtures("stub_sun_integration")

EAST = "cover.east"
WEST = "cover.west"
SOUTH = "cover.south"


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload what the flows set up (the house's polling cover too)."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


def _world(hass) -> None:
    hass.states.async_set(
        "sun.sun", "above_horizon", {"azimuth": 180.0, "elevation": 45.0}
    )
    for cover in (EAST, WEST, SOUTH):
        # Registered first: a cover with a registry id keys its window.
        er.async_get(hass).async_get_or_create(
            "cover", "demo", cover, suggested_object_id=cover.split(".")[1]
        )
        hass.states.async_set(
            cover,
            "open",
            {"current_position": 60, "supported_features": 15},
        )


def _house(hass) -> MockConfigEntry:
    return next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get("is_hub")
    )


def _window_subentries(hass) -> dict[str, config_entries.ConfigSubentry]:
    """The house's window subentries by cover."""
    return {
        subentry.data["options"][CONF_COVER_ENTITY]: subentry
        for subentry in _house(hass).subentries.values()
        if subentry.subentry_type == "window"
    }


async def _fresh_install(hass, cover: str = EAST, name: str = "East") -> None:
    """The first window: the add form on an empty house."""
    result = await start_add(hass)
    result = await submit(
        hass,
        result,
        {"name": name, CONF_COVER_ENTITY: cover, CONF_AZIMUTH: 100},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()


async def _add_window(hass, cover: str, name: str, **values) -> dict:
    """ "Add window" on the house (the subentry flow)."""
    manager = hass.config_entries.subentries
    result = await manager.async_init(
        (_house(hass).entry_id, "window"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM, result
    result = await manager.async_configure(
        result["flow_id"],
        sectioned(
            {"name": name, CONF_COVER_ENTITY: cover, CONF_AZIMUTH: 250, **values},
            [str(name) for name in result["data_schema"].schema],
        ),
    )
    await hass.async_block_till_done()
    return result


async def _reconfigure(hass, cover: str, **values) -> dict:
    """A window subentry's Reconfigure, changing ``values``."""
    subentry = _window_subentries(hass)[cover]
    manager = hass.config_entries.subentries
    result = await manager.async_init(
        (_house(hass).entry_id, "window"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    assert result["step_id"] == "reconfigure", result
    shown = [str(name) for name in result["data_schema"].schema]
    filled = {
        str(field): field.description["suggested_value"]
        for section_schema in result["data_schema"].schema.values()
        for field in section_schema.schema.schema
        if field.description and field.description.get("suggested_value") is not None
    }
    result = await manager.async_configure(
        result["flow_id"], sectioned({**filled, **values}, shown)
    )
    await hass.async_block_till_done()
    return result


# ------------------------------------------------------------ fresh install


async def test_fresh_install_creates_the_house_with_the_window_as_subentry(
    hass, cover_calls
):
    _world(hass)
    office = ar.async_get(hass).async_create("Office")
    er.async_get(hass).async_update_entity(EAST, area_id=office.id)
    await _fresh_install(hass)

    (house,) = hass.config_entries.async_entries(DOMAIN)
    assert house.data["is_hub"] is True
    assert house.unique_id == HUB_UNIQUE_ID
    assert (house.version, house.minor_version) == (2, 1)
    assert house.state is ConfigEntryState.LOADED
    (subentry,) = house.subentries.values()
    assert subentry.subentry_type == "window"
    assert subentry.title == "East"
    assert subentry.unique_id == er.async_get(hass).async_get(EAST).id
    assert subentry.data["data"] == {"name": "East", CONF_SENSOR_TYPE: "cover_blind"}
    assert subentry.data["options"][CONF_ENTITIES] == [EAST]
    # A new window's key is its subentry_id.
    key = subentry.subentry_id
    assert window_configs(hass)[key][CONF_COVER_ENTITY] == EAST

    window = WindowHandle(hass, EAST)
    assert window.window_key == key
    assert window.attributes["window_key"] == key
    assert window.target is not None  # it runs
    ent_reg = er.async_get(hass)
    rows = [row for row in ent_reg.entities.values() if row.unique_id.startswith(key)]
    assert rows
    for row in rows:
        assert row.config_entry_id == house.entry_id
        assert row.config_subentry_id == key
    # One device per window, hanging off the house device.
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, key), config_entry_id=house.entry_id
    )
    house_device = dev_reg.async_get_device_by_identifier(
        (DOMAIN, HUB_UNIQUE_ID), config_entry_id=house.entry_id
    )
    assert device.config_subentry_id == key
    assert device.via_device_id == house_device.id
    assert device.area_id == office.id  # copied from the cover
    assert {row.device_id for row in rows} == {device.id}
    # The house settings live on the house (lifted from the first window).
    assert "house" in house.options
    # A fresh house has nothing to consolidate.
    assert ir.async_get(hass).async_get_issue(DOMAIN, "consolidate_house") is None


async def test_add_window_adds_a_subentry_and_leaves_the_others_running(
    hass, cover_calls
):
    _world(hass)
    await _fresh_install(hass)
    east = WindowHandle(hass, EAST)

    result = await _add_window(hass, WEST, "West")
    assert result["type"] is FlowResultType.CREATE_ENTRY, result

    subentries = _window_subentries(hass)
    assert set(subentries) == {EAST, WEST}
    west = WindowHandle(hass, WEST)
    assert west.window_key == subentries[WEST].subentry_id
    assert west.target is not None
    assert east.teardowns == 0  # the house did not reload East


async def test_the_config_flow_adds_a_window_to_the_house(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)

    result = await start_add(hass)
    result = await submit(
        hass, result, {"name": "West", CONF_COVER_ENTITY: WEST, CONF_AZIMUTH: 250}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "window_added"
    await hass.async_block_till_done()
    assert set(_window_subentries(hass)) == {EAST, WEST}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_cover_another_window_drives_is_refused(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)

    result = await _add_window(hass, EAST, "East again")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_in_use"}
    assert set(_window_subentries(hass)) == {EAST}


async def test_add_window_waits_for_the_consolidation(hass, cover_calls):
    """A house that still has window entries adds window entries (legacy)."""
    add_legacy_house(hass)
    result = await hass.config_entries.subentries.async_init(
        (_house(hass).entry_id, "window"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "consolidate_first"


# ------------------------------------------------------------ changes


async def test_reconfigure_rebuilds_only_that_window(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)
    await _add_window(hass, WEST, "West")
    east, west = WindowHandle(hass, EAST), WindowHandle(hass, WEST)

    result = await _reconfigure(hass, EAST, **{CONF_HEIGHT_WIN: 2.8, "name": "East 2"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    subentry = _window_subentries(hass)[EAST]
    assert subentry.title == "East 2"
    assert subentry.data["options"][CONF_HEIGHT_WIN] == 2.8
    assert east.teardowns == 1  # rebuilt with its new geometry
    assert west.teardowns == 0  # untouched
    assert east.target is not None
    assert east.window_key == subentry.subentry_id  # the key never changes


async def test_reconfigure_stores_an_exception_sparsely(hass, cover_calls):
    """A recurring value that differs from the house's is the window's own."""
    _world(hass)
    await _fresh_install(hass)
    east = WindowHandle(hass, EAST)
    inherited = (await east.settings())[CONF_SUNSET_POS]

    await _reconfigure(hass, EAST, **{CONF_SUNSET_POS: 42})
    overrides = _window_subentries(hass)[EAST].data["options"]["overrides"]
    assert overrides["values"] == {CONF_SUNSET_POS: 42}
    assert (await east.settings())[CONF_SUNSET_POS] == 42
    assert east.teardowns == 0  # an exception needs no rebuild

    await _reconfigure(hass, EAST, **{CONF_SUNSET_POS: inherited})
    overrides = _window_subentries(hass)[EAST].data["options"]["overrides"]
    assert overrides["values"] == {}


async def test_deleting_a_window_removes_it_alone(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)
    await _add_window(hass, WEST, "West")
    east = WindowHandle(hass, EAST)
    west_key = _window_subentries(hass)[WEST].subentry_id

    assert hass.config_entries.async_remove_subentry(_house(hass), west_key)
    await hass.async_block_till_done()

    assert set(_window_subentries(hass)) == {EAST}
    assert not [
        row
        for row in er.async_get(hass).entities.values()
        if row.unique_id.startswith(west_key)
    ]
    assert east.teardowns == 0
    assert east.target is not None


async def test_one_broken_window_does_not_fail_the_house(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)
    house = _house(hass)
    broken = config_entries.ConfigSubentry(
        data={"data": {}, "options": {CONF_ENTITIES: [WEST]}},
        subentry_type="window",
        title="Broken",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(house, broken)
    await hass.async_block_till_done()

    assert house.state is ConfigEntryState.LOADED
    assert WindowHandle(hass, EAST).target is not None
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"window_setup_failed_{broken.subentry_id}"
    )
    assert issue is not None
    assert issue.translation_placeholders["window"] == "Broken"

    # Deleting it clears its issue.
    hass.config_entries.async_remove_subentry(house, broken.subentry_id)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"window_setup_failed_{broken.subentry_id}"
        )
        is None
    )


# ------------------------------------------------------------ services


async def test_services_reach_window_subentries(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "South", "cover": SOUTH, CONF_HEIGHT_WIN: 2.2, CONF_DISTANCE: 0.4},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    south = _window_subentries(hass)[SOUTH]
    assert response == {"entry_id": south.subentry_id, "title": "South"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    handle = WindowHandle(hass, SOUTH)
    assert handle.target is not None

    # change_settings addresses a window by its key or its title.
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": "South", CONF_DEFAULT_HEIGHT: 33},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (await window_settings(hass, south.subentry_id))[CONF_DEFAULT_HEIGHT] == 33

    forecast = await hass.services.async_call(
        DOMAIN,
        "get_forecast",
        {"config_entry": south.subentry_id},
        blocking=True,
        return_response=True,
    )
    assert isinstance(forecast["forecast"], list)


async def test_house_options_are_the_house_settings(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)
    house = _house(hass)
    key = _window_subentries(hass)[EAST].subentry_id

    result = await hass.config_entries.options.async_init(house.entry_id)
    assert result["step_id"] == "house"
    thresholds = {CONF_TEMP_LOW: 18.0, CONF_TEMP_HIGH: 26.0}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            str(name): thresholds if str(name) == "house_climate" else {}
            for name in result["data_schema"].schema
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    assert house.options["house"][CONF_TEMP_LOW] == 18.0
    assert house.options["house"][CONF_TEMP_HIGH] == 26.0
    settings = await window_settings(hass, key)
    assert (settings[CONF_TEMP_LOW], settings[CONF_TEMP_HIGH]) == (18.0, 26.0)


async def test_a_house_setting_stays_when_saved_unchanged(hass, cover_calls):
    _world(hass)
    await _fresh_install(hass)
    house = _house(hass)
    before = dict(house.options)
    result = await hass.config_entries.options.async_init(house.entry_id)
    # Saved as shown: every field sends its pre-filled value.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            str(name): {
                str(field): field.description["suggested_value"]
                for field in section_schema.schema.schema
                if field.description["suggested_value"] is not None
            }
            for name, section_schema in result["data_schema"].schema.items()
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(house.options) == before
