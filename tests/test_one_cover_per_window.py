"""One window drives one cover, and a cover belongs to one window (ADR 0002).

Through the public surfaces: the setup form, the options form, the
``add_entry`` service. A cover another window already drives is refused
with a clear error; ``add_entry`` takes ``cover`` (and still ``covers``
with exactly one item). Every writer stores the cover as
``cover_entity_id`` and as ``group: [cover]`` (for a downgrade), and a new
window's unique_id is its cover's entity-registry id.
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
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .test_config_flow import AUTOMATION_STEP_INPUT, VERTICAL_STEP_INPUT
from .window_form import add_legacy_house, add_window, start_add, submit

TAKEN = "cover.taken"
FREE = "cover.free"


@pytest.fixture(autouse=True)
def legacy_model(hass):
    """Pin the window-entry flows: a house that still has window entries (P7).

    A fresh install creates the house with subentries instead
    (tests/test_house_subentries.py).
    """
    add_legacy_house(hass)


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload what the flows set up (incl. the hub's polling cover)."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is config_entries.ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _window(hass, cover: str, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Window {cover}",
        data={"name": f"Window {cover}", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
        },
        **kwargs,
    )
    entry.add_to_hass(hass)
    return entry


def _register(hass, cover: str) -> str:
    """Put ``cover`` in the entity registry; return its registry id."""
    domain, object_id = cover.split(".")
    row = er.async_get(hass).async_get_or_create(
        domain, "demo", f"uid-{object_id}", suggested_object_id=object_id
    )
    assert row.entity_id == cover
    return row.id


# ------------------------------------------------------------ setup form


@pytest.mark.usefixtures("stub_sun_integration")
async def test_wizard_refuses_a_cover_another_window_drives(hass):
    _window(hass, TAKEN)
    result = await start_add(hass)
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
    assert result["options"][CONF_COVER_ENTITY] == FREE
    assert result["options"][CONF_ENTITIES] == [FREE]  # read by older versions
    assert result["result"].unique_id == registry_id


@pytest.mark.usefixtures("stub_sun_integration")
async def test_wizard_aborts_a_second_window_for_a_registered_cover(hass):
    """A disabled window still owns its registered cover's unique_id."""
    registry_id = _register(hass, FREE)
    _window(
        hass,
        FREE,
        unique_id=registry_id,
        disabled_by=config_entries.ConfigEntryDisabler.USER,
    )
    result = await add_window(
        hass, {**VERTICAL_STEP_INPUT, **AUTOMATION_STEP_INPUT, CONF_COVER_ENTITY: FREE}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ------------------------------------------------------------ options form


async def _submit_cover(hass, entry, cover: str):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "covers_geometry": {CONF_COVER_ENTITY: cover},
            "sun_behavior": {},
            "automation_timing": {},
            "climate": {},
        },
    )


async def test_options_form_shows_the_window_cover(hass, mock_sun_entity):
    entry = _window(hass, FREE)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    geometry = next(
        value.schema.schema
        for marker, value in result["data_schema"].schema.items()
        if str(marker) == "covers_geometry"
    )
    marker = next(m for m in geometry if str(m) == CONF_COVER_ENTITY)
    assert marker.description == {"suggested_value": FREE}


async def test_options_form_refuses_a_cover_another_window_drives(
    hass, mock_sun_entity
):
    _window(hass, TAKEN)
    entry = _window(hass, FREE)
    result = await _submit_cover(hass, entry, TAKEN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_in_use"}
    assert entry.options[CONF_ENTITIES] == [FREE]


async def test_options_form_moves_the_window_to_another_cover(hass, mock_sun_entity):
    entry = _window(hass, FREE)
    result = await _submit_cover(hass, entry, "cover.other")
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_COVER_ENTITY] == "cover.other"
    assert entry.options[CONF_ENTITIES] == ["cover.other"]


async def test_options_form_keeps_its_own_cover(hass, mock_sun_entity):
    entry = _window(hass, FREE)
    result = await _submit_cover(hass, entry, FREE)
    assert result["type"] is FlowResultType.CREATE_ENTRY


# ------------------------------------------------------------- add_entry


@pytest.fixture
async def running_window(hass, mock_sun_entity):
    """One loaded window (so the services are registered) driving TAKEN."""
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(TAKEN, "open", {"current_position": 50})
    entry = _window(hass, TAKEN)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


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
    entry = hass.config_entries.async_get_entry(response["entry_id"])
    assert entry.options[CONF_COVER_ENTITY] == FREE
    assert entry.options[CONF_ENTITIES] == [FREE]
    assert entry.unique_id == registry_id


async def test_add_entry_still_accepts_a_one_item_covers_list(hass, running_window):
    response = await _add_entry(hass, covers=[FREE])
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(response["entry_id"])
    assert entry.options[CONF_COVER_ENTITY] == FREE
    assert entry.options[CONF_ENTITIES] == [FREE]


async def test_add_entry_refuses_a_second_cover(hass, running_window):
    before = len(hass.config_entries.async_entries(DOMAIN))
    with pytest.raises(ServiceValidationError, match="exactly one cover"):
        await _add_entry(hass, covers=[FREE, "cover.second"])
    assert len(hass.config_entries.async_entries(DOMAIN)) == before


async def test_add_entry_refuses_a_cover_another_window_drives(hass, running_window):
    before = len(hass.config_entries.async_entries(DOMAIN))
    with pytest.raises(ServiceValidationError, match="already driven by"):
        await _add_entry(hass, cover=TAKEN)
    assert len(hass.config_entries.async_entries(DOMAIN)) == before


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
