"""One window drives one cover, and a cover belongs to one window (ADR 0002).

Through the public surfaces: the add form (a fresh install's, and "Add
window" on the house), a window's Reconfigure, the ``add_entry`` service.
A cover another window already drives is refused with a clear error;
``add_entry`` takes ``cover`` (and still ``covers`` with exactly one
item). A window stores its cover as ``cover_entity_id`` only (since v2.1
nothing writes the ``group`` list), and a new window's unique_id is its
cover's entity-registry id.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    DOMAIN,
)

from .conftest import COMMON_OPTIONS
from .house_model import Window, mock_house
from .test_config_flow import AUTOMATION_STEP_INPUT, VERTICAL_STEP_INPUT
from .window_form import (
    add_window,
    prefilled,
    record,
    start_add_window,
    start_reconfigure,
    submit,
    window_subentries,
)

TAKEN = "cover.taken"
FREE = "cover.free"


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload what the flows set up (incl. the hub's polling cover)."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is config_entries.ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _window(cover: str, **kwargs) -> Window:
    return Window(
        name=f"Window {cover}",
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
        },
        **kwargs,
    )


def _house(hass, *windows: Window) -> MockConfigEntry:
    return mock_house(hass, list(windows))


def _register(hass, cover: str) -> str:
    """Put ``cover`` in the entity registry; return its registry id."""
    domain, object_id = cover.split(".")
    row = er.async_get(hass).async_get_or_create(
        domain, "demo", f"uid-{object_id}", suggested_object_id=object_id
    )
    assert row.entity_id == cover
    return row.id


def _subentry(house, key: str):
    return next(
        subentry
        for subentry in window_subentries(house)
        if (subentry.data.get("window_key") or subentry.subentry_id) == key
    )


# ------------------------------------------------------------ setup form


@pytest.mark.usefixtures("stub_sun_integration")
async def test_wizard_refuses_a_cover_another_window_drives(hass):
    house = _house(hass, _window(TAKEN))
    result = await start_add_window(hass, house)
    result = await submit(
        hass, result, {**VERTICAL_STEP_INPUT, CONF_COVER_ENTITY: TAKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Shown above the form: HA shows no error on a field inside a section.
    assert result["errors"] == {"base": "cover_in_use"}


@pytest.mark.usefixtures("stub_sun_integration")
async def test_wizard_stores_one_cover_and_keys_the_entry_by_it(hass):
    registry_id = _register(hass, FREE)
    result = await add_window(
        hass, {**VERTICAL_STEP_INPUT, **AUTOMATION_STEP_INPUT, CONF_COVER_ENTITY: FREE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (window,) = window_subentries(result["result"])
    assert window.data[CONF_COVER_ENTITY] == FREE
    assert CONF_ENTITIES not in window.data  # no group list since v2.1
    assert window.unique_id == registry_id


@pytest.mark.usefixtures("stub_sun_integration")
async def test_wizard_aborts_a_second_window_for_a_registered_cover(hass):
    """A window keeps its cover's registry id as unique_id: HA refuses a
    second window for that cover even where no window lists it (the id
    stays when a window moved to another cover outside the forms)."""
    registry_id = _register(hass, FREE)
    house = _house(hass, _window("cover.other", unique_id=registry_id))
    result = await add_window(
        hass,
        {**VERTICAL_STEP_INPUT, **AUTOMATION_STEP_INPUT, CONF_COVER_ENTITY: FREE},
        start=lambda hass: start_add_window(hass, house),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(window_subentries(house)) == 1


# ------------------------------------------------------------ reconfigure


async def _reconfigure_cover(hass, house, window: Window, cover: str):
    result = await start_reconfigure(hass, house, window.subentry_id)
    return await submit(hass, result, {**prefilled(result), CONF_COVER_ENTITY: cover})


@pytest.mark.usefixtures("stub_sun_integration")
async def test_reconfigure_shows_the_window_cover(hass):
    window = _window(FREE)
    house = _house(hass, window)
    result = await start_reconfigure(hass, house, window.subentry_id)
    assert prefilled(result)[CONF_COVER_ENTITY] == FREE


@pytest.mark.usefixtures("stub_sun_integration")
async def test_reconfigure_refuses_a_cover_another_window_drives(hass):
    window = _window(FREE)
    house = _house(hass, _window(TAKEN), window)
    result = await _reconfigure_cover(hass, house, window, TAKEN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_in_use"}
    assert record(_subentry(house, window.key)).cover == FREE


@pytest.mark.usefixtures("stub_sun_integration")
async def test_reconfigure_moves_the_window_to_another_cover(hass):
    registry_id = _register(hass, "cover.other")
    window = _window(FREE)
    house = _house(hass, window)
    result = await _reconfigure_cover(hass, house, window, "cover.other")
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = _subentry(house, window.key)
    assert record(subentry).cover == "cover.other"
    assert subentry.unique_id == registry_id


@pytest.mark.usefixtures("stub_sun_integration")
async def test_reconfigure_keeps_its_own_cover(hass):
    window = _window(FREE)
    house = _house(hass, window)
    result = await _reconfigure_cover(hass, house, window, FREE)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert record(_subentry(house, window.key)).cover == FREE


# ------------------------------------------------------------- add_entry


@pytest.fixture
async def running_window(hass, mock_sun_entity):
    """The house with one running window (so the services are registered)."""
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(TAKEN, "open", {"current_position": 50})
    house = _house(hass, _window(TAKEN))
    await hass.config_entries.async_setup(house.entry_id)
    await hass.async_block_till_done()
    return house


async def _add_entry(hass, **data):
    return await hass.services.async_call(
        DOMAIN,
        "add_entry",
        {"name": "Added", CONF_AZIMUTH: 90, **data},
        blocking=True,
        return_response=True,
    )


async def test_add_entry_takes_one_cover(hass, running_window):
    registry_id = _register(hass, FREE)
    response = await _add_entry(hass, cover=FREE)
    await hass.async_block_till_done()
    subentry = _subentry(running_window, response["entry_id"])
    assert subentry.data[CONF_COVER_ENTITY] == FREE
    assert CONF_ENTITIES not in subentry.data
    assert subentry.unique_id == registry_id


async def test_add_entry_still_accepts_a_one_item_covers_list(hass, running_window):
    response = await _add_entry(hass, covers=[FREE])
    await hass.async_block_till_done()
    subentry = _subentry(running_window, response["entry_id"])
    assert subentry.data[CONF_COVER_ENTITY] == FREE
    assert CONF_ENTITIES not in subentry.data


async def test_add_entry_refuses_a_second_cover(hass, running_window):
    before = len(window_subentries(running_window))
    with pytest.raises(ServiceValidationError, match="exactly one cover"):
        await _add_entry(hass, covers=[FREE, "cover.second"])
    assert len(window_subentries(running_window)) == before


async def test_add_entry_refuses_a_cover_another_window_drives(hass, running_window):
    before = len(window_subentries(running_window))
    with pytest.raises(ServiceValidationError, match="already driven by"):
        await _add_entry(hass, cover=TAKEN)
    assert len(window_subentries(running_window)) == before


@pytest.mark.parametrize(
    "data",
    [{}, {"covers": []}, {"cover": FREE, "covers": [FREE]}],
    ids=["no_cover", "empty_list", "both_forms"],
)
async def test_add_entry_needs_exactly_one_form_of_the_cover(
    hass, running_window, data
):
    with pytest.raises(ServiceValidationError, match="cover"):
        await _add_entry(hass, **data)
