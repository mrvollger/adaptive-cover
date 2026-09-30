"""adaptive_cover.get_profile: read the stored layered settings.

A response-only, read-only service any user may call (the house card reads
it instead of the admin-only diagnostics). Pinned here: the response
shapes for no scope, the house, a floor, an area and a window (by window
key and by its Mode select entity), the errors, and that a non-admin user
can call it.
"""

from __future__ import annotations

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import floor_registry as fr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_SENSOR_TYPE,
    CONF_TEMP_LOW,
    DOMAIN,
    SensorType,
)

from .conftest import COMMON_OPTIONS
from .window_handle import WindowHandle, window_settings

COVER = "cover.office"
TOGGLES = {
    "climate_on",
    "use_outside_temp",
    "use_lux",
    "use_irradiance",
    "manual_detection",
}


@pytest.fixture
async def house(hass, mock_sun_entity):
    """One window in the Office (Upstairs), with a room and a floor value."""
    async_mock_service(hass, "cover", "set_cover_position")
    hass.states.async_set(COVER, "open", {"current_position": 60})
    upstairs = fr.async_get(hass).async_create("Upstairs", level=1)
    office = ar.async_get(hass).async_create("Office", floor_id=upstairs.floor_id)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office north",
        data={"name": "Office north", CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [COVER],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), config_entry_id=entry.entry_id
    )
    devices.async_update_device(device.id, area_id=office.id)
    for data in (
        {"scope": "area", "id": office.id, CONF_DEFAULT_HEIGHT: 80},
        {"scope": "floor", "id": upstairs.floor_id, CONF_TEMP_LOW: 18},
    ):
        await hass.services.async_call(DOMAIN, "set_profile", data, blocking=True)
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": entry.entry_id, CONF_EYE_HEIGHT: 1.6},
        blocking=True,
    )
    await hass.async_block_till_done()
    return {"entry": entry, "office": office.id, "upstairs": upstairs.floor_id}


async def _get(hass, context: Context | None = None, **data):
    return await hass.services.async_call(
        DOMAIN,
        "get_profile",
        data,
        blocking=True,
        return_response=True,
        context=context,
    )


async def test_everything_without_a_scope(hass, house):
    response = await _get(hass)
    assert set(response) == {"house", "floors", "areas"}
    assert set(response["house"]) == {"values", "temperature_unit"}
    assert set(response["house"]["values"]) >= TOGGLES
    assert response["house"]["temperature_unit"] == hass.config.units.temperature_unit
    assert response["floors"] == {house["upstairs"]: {CONF_TEMP_LOW: 18}}
    assert response["areas"] == {house["office"]: {CONF_DEFAULT_HEIGHT: 80}}


async def test_the_house(hass, house):
    response = await _get(hass, scope="house")
    assert set(response) == {"scope", "id", "values", "temperature_unit"}
    assert response["scope"] == "house"
    assert response["id"] is None
    assert set(response["values"]) >= TOGGLES
    assert response["values"]["climate_on"] is True


async def test_a_floor_and_an_area(hass, house):
    assert await _get(hass, scope="floor", id=house["upstairs"]) == {
        "scope": "floor",
        "id": house["upstairs"],
        "values": {CONF_TEMP_LOW: 18},
    }
    assert await _get(hass, scope="area", id=house["office"]) == {
        "scope": "area",
        "id": house["office"],
        "values": {CONF_DEFAULT_HEIGHT: 80},
    }
    # A room that stores nothing: an empty profile.
    den = ar.async_get(hass).async_create("Den")
    assert (await _get(hass, scope="area", id=den.id))["values"] == {}


@pytest.mark.parametrize("by", ["window_key", "mode_select"])
async def test_a_window(hass, house, by):
    entry = house["entry"]
    ref = (
        entry.entry_id
        if by == "window_key"
        else WindowHandle.by_key(hass, entry.entry_id).entity_id("mode")
    )
    response = await _get(hass, scope="window", id=ref)
    assert set(response) == {
        "scope",
        "id",
        "title",
        "area_id",
        "floor_id",
        "overrides",
        "settings",
        "provenance",
    }
    assert response["id"] == entry.entry_id
    assert response["title"] == "Office north"
    assert (response["area_id"], response["floor_id"]) == (
        house["office"],
        house["upstairs"],
    )
    assert response["overrides"] == {"values": {CONF_EYE_HEIGHT: 1.6}, "legacy": {}}
    assert response["settings"] == await window_settings(hass, entry.entry_id)
    assert {
        key: response["provenance"][key]
        for key in (CONF_EYE_HEIGHT, CONF_DEFAULT_HEIGHT, CONF_TEMP_LOW, "set_azimuth")
    } == {
        CONF_EYE_HEIGHT: "window",
        CONF_DEFAULT_HEIGHT: "area",
        CONF_TEMP_LOW: "floor",
        "set_azimuth": "window",
    }
    assert response["provenance"]["climate_on"] == "house"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"scope": "window"}, "a window needs its id"),
        ({"scope": "window", "id": "nope"}, "No Adaptive Cover window"),
        ({"scope": "window", "id": "sun.sun"}, "is not an Adaptive Cover entity"),
        ({"scope": "area", "id": "attic"}, "no area 'attic'"),
        ({"scope": "floor"}, "a floor needs its id"),
        ({"scope": "house", "id": "x"}, "the house takes no id"),
    ],
    ids=[
        "window_no_id",
        "window_unknown",
        "not_ours",
        "area_unknown",
        "floor_no_id",
        "house_id",
    ],
)
async def test_errors(hass, house, data, message):
    with pytest.raises(ServiceValidationError, match=message):
        await _get(hass, **data)


async def test_any_user_may_read(hass, house, hass_read_only_user):
    response = await _get(
        hass, context=Context(user_id=hass_read_only_user.id), scope="house"
    )
    assert response["scope"] == "house"
