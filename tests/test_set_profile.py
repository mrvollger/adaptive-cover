"""adaptive_cover.set_profile: house, floor and room settings (P5 flip).

The service stores recurring settings at the house, a floor or an area
(room), checked against the levels the option spec allows. Every window
inherits them unless a narrower level or the window itself has its own
value (ADR 0003), and acts on them at once, without a reload.

Observed through the hub's config entry (where the value went), the
diagnostics settings (what each window acts on), the Position sensor's
provenance and entity states.
"""

from __future__ import annotations

import pytest
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
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_SUNSET_POS,
    CONF_TEMP_LOW,
    DOMAIN,
)

from .conftest import COMMON_OPTIONS
from .house_model import Window, mock_house
from .window_handle import WindowHandle, window_settings

OFFICE_COVER = "cover.office"
DEN_COVER = "cover.den"


def _window(name: str, cover: str) -> Window:
    return Window(
        name=name,
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: [cover],
        },
    )


def _place(hass, window: Window, area_id: str) -> None:
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, window.key), config_entry_id=_hub(hass).entry_id
    )
    devices.async_update_device(device.id, area_id=area_id)


@pytest.fixture
async def house(hass, mock_sun_entity):
    """Two windows: the office (Upstairs) and the den (Downstairs)."""
    async_mock_service(hass, "cover", "set_cover_position")
    floors = fr.async_get(hass)
    upstairs = floors.async_create("Upstairs", level=1)
    downstairs = floors.async_create("Downstairs", level=0)
    areas = ar.async_get(hass)
    office = areas.async_create("Office", floor_id=upstairs.floor_id)
    den = areas.async_create("Den", floor_id=downstairs.floor_id)
    windows = {
        "Office": _window("Office", OFFICE_COVER),
        "Den": _window("Den", DEN_COVER),
    }
    for cover in (OFFICE_COVER, DEN_COVER):
        hass.states.async_set(cover, "open", {"current_position": 60})
    entry = mock_house(hass, list(windows.values()))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    _place(hass, windows["Office"], office.id)
    _place(hass, windows["Den"], den.id)
    await hass.async_block_till_done()
    return {
        "office": windows["Office"],
        "den": windows["Den"],
        "office_area": office.id,
        "den_area": den.id,
        "upstairs": upstairs.floor_id,
        "downstairs": downstairs.floor_id,
    }


async def _set_profile(hass, **data):
    response = await hass.services.async_call(
        DOMAIN, "set_profile", data, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    return response


def _hub(hass) -> MockConfigEntry:
    (hub,) = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("is_hub")
    ]
    return hub


async def test_house_setting_reaches_every_window_without_a_reload(hass, house):
    handles = {
        name: WindowHandle.by_key(hass, house[name].key) for name in ("office", "den")
    }
    before = {name: handle.teardowns for name, handle in handles.items()}

    response = await _set_profile(hass, scope="house", **{CONF_SUNSET_POS: 20})

    assert response == {"scope": "house", "id": None, "changed": [CONF_SUNSET_POS]}
    assert _hub(hass).options["house"][CONF_SUNSET_POS] == 20
    for name in ("office", "den"):
        settings = await window_settings(hass, house[name].key)
        assert settings[CONF_SUNSET_POS] == 20, name
        assert handles[name].teardowns == before[name], name
    # Setting it again changes nothing.
    response = await _set_profile(hass, scope="house", **{CONF_SUNSET_POS: 20})
    assert response["changed"] == []


async def test_room_setting_overrides_the_house_for_that_room(hass, house):
    office, den = house["office"], house["den"]
    house_default = _hub(hass).options["house"][CONF_DEFAULT_HEIGHT]

    await _set_profile(
        hass, scope="area", id=house["office_area"], **{CONF_DEFAULT_HEIGHT: 80}
    )

    assert _hub(hass).options["areas"][house["office_area"]] == {
        CONF_DEFAULT_HEIGHT: 80
    }
    assert (await window_settings(hass, office.key))[CONF_DEFAULT_HEIGHT] == 80
    assert (await window_settings(hass, den.key))[CONF_DEFAULT_HEIGHT] == house_default
    assert WindowHandle.by_key(hass, office.key).attributes["provenance"] == {
        CONF_DEFAULT_HEIGHT: "area"
    }

    # null removes the room's value: the room inherits the house again.
    await _set_profile(
        hass, scope="area", id=house["office_area"], **{CONF_DEFAULT_HEIGHT: None}
    )
    assert house["office_area"] not in _hub(hass).options["areas"]
    assert (await window_settings(hass, office.key))[
        CONF_DEFAULT_HEIGHT
    ] == house_default


async def test_floor_setting_and_precedence(hass, house):
    office = house["office"]
    await _set_profile(hass, scope="floor", id=house["upstairs"], **{CONF_TEMP_LOW: 18})
    await _set_profile(
        hass, scope="area", id=house["office_area"], **{CONF_TEMP_LOW: 19}
    )
    assert (await window_settings(hass, office.key))[CONF_TEMP_LOW] == 19
    # The area beats the floor; without it the floor applies.
    await _set_profile(
        hass, scope="area", id=house["office_area"], **{CONF_TEMP_LOW: None}
    )
    assert (await window_settings(hass, office.key))[CONF_TEMP_LOW] == 18
    assert (await window_settings(hass, house["den"].key))[CONF_TEMP_LOW] != 18


async def test_window_value_beats_the_room(hass, house):
    office = house["office"]
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": office.key, CONF_EYE_HEIGHT: 1.6},
        blocking=True,
    )
    await hass.async_block_till_done()
    await _set_profile(
        hass, scope="area", id=house["office_area"], **{CONF_EYE_HEIGHT: 1.3}
    )
    assert (await window_settings(hass, office.key))[CONF_EYE_HEIGHT] == 1.6


async def test_a_window_moved_to_another_room_takes_its_settings(hass, house):
    office, den = house["office"], house["den"]
    await _set_profile(
        hass, scope="area", id=house["den_area"], **{CONF_DEFAULT_HEIGHT: 70}
    )
    _place(hass, office, house["den_area"])
    # The next refresh (a sun update) reads the new room.
    hass.states.async_set("sun.sun", "above_horizon", {"azimuth": 181, "elevation": 44})
    await hass.async_block_till_done()
    assert (await window_settings(hass, office.key))[CONF_DEFAULT_HEIGHT] == 70
    assert (await window_settings(hass, den.key))[CONF_DEFAULT_HEIGHT] == 70


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"scope": "area", "id": "office", CONF_DELTA_TIME: 5},
            "not settable on a area",
        ),
        (
            {"scope": "house", "id": "office", CONF_DELTA_TIME: 5},
            "the house takes no id",
        ),
        ({"scope": "area", "id": "attic", CONF_DEFAULT_HEIGHT: 5}, "no area 'attic'"),
        ({"scope": "floor", CONF_TEMP_LOW: 18}, "a floor needs its id"),
        ({"scope": "house"}, "No settings provided"),
        ({"scope": "house", CONF_DELTA_TIME: None}, "the house needs a value"),
    ],
    ids=[
        "house_only_on_an_area",
        "house_with_an_id",
        "unknown_area",
        "floor_without_id",
        "empty",
        "house_without_a_value",
    ],
)
async def test_rejects_what_the_spec_or_registries_do_not_allow(
    hass, house, data, message
):
    before = dict(_hub(hass).options)
    with pytest.raises(ServiceValidationError, match=message):
        await hass.services.async_call(DOMAIN, "set_profile", data, blocking=True)
    assert dict(_hub(hass).options) == before
