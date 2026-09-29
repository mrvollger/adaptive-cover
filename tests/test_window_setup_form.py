"""The one-screen window form: add a window, reconfigure it (plan P6).

Through the config-entry flow manager and entry states only:

- the add form is one screen; recurring settings sit only in collapsed
  sections labelled as per-window exceptions;
- a window made from only a cover and an azimuth is valid and resolves to
  the house defaults;
- "Copy from" pre-fills everything but the name and the cover; presets
  fill geometry only;
- Reconfigure shows the same form without the exceptions and changes only
  the one-time settings.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_AWNING_ANGLE,
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_DEFAULT_HEIGHT,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_HEIGHT_WIN,
    CONF_LENGTH_AWNING,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_OVERHANG_DEPTH,
    CONF_OVERHANG_HEIGHT,
    CONF_SENSOR_TYPE,
    CONF_TEMP_HIGH,
    CONF_TILT_DEPTH,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.settings.lift import legacy_flat
from custom_components.adaptive_cover.settings.resolve import (
    HouseProfile,
    Profiles,
    Source,
    WindowOverrides,
    resolve_with_provenance,
    spec_default,
)
from custom_components.adaptive_cover.settings.spec import OPTS, Level, Scope

from .conftest import COMMON_OPTIONS
from .window_form import (
    add_window,
    collapsed,
    prefilled,
    show_type,
    shown,
    start_add,
    start_reconfigure,
    submit,
)

pytestmark = pytest.mark.usefixtures("stub_sun_integration")

COVER = "cover.study"
OTHER = "cover.hall"
EXCEPTIONS = ("exceptions_positions", "exceptions_schedule", "exceptions_climate")


@pytest.fixture(autouse=True)
async def unload_all_entries(hass):
    """Unload what the flows set up (incl. the hub's polling cover)."""
    yield
    for entry in hass.config_entries.async_entries():
        if entry.state is config_entries.ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _window(
    hass, cover: str, *, title: str = "Den south", **options
) -> MockConfigEntry:
    """An existing window: an awning with its own geometry and exceptions."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={"name": title, CONF_SENSOR_TYPE: SensorType.AWNING},
        options={
            **COMMON_OPTIONS,
            CONF_AZIMUTH: 190,
            CONF_HEIGHT_WIN: 2.4,
            CONF_DISTANCE: 0.3,
            CONF_LENGTH_AWNING: 3.0,
            CONF_AWNING_ANGLE: 10,
            CONF_OVERHANG_DEPTH: 1.2,
            CONF_OVERHANG_HEIGHT: 2.6,
            CONF_DEFAULT_HEIGHT: 97,
            CONF_ENTITIES: [cover],
            CONF_COVER_ENTITY: cover,
            **options,
        },
    )
    entry.add_to_hass(hass)
    return entry


def _position_sensor(hass, entry) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_Cover Position"
    )


# ------------------------------------------------------------- the screen


@pytest.mark.parametrize(
    "cover_type", [SensorType.BLIND, SensorType.AWNING, SensorType.TILT]
)
async def test_recurring_settings_only_in_collapsed_exceptions(hass, cover_type):
    """One-time settings up front; house-level ones only as exceptions."""
    result = await start_add(hass)
    if cover_type != SensorType.BLIND:
        result = await show_type(hass, result, cover_type, COVER)
    sections = shown(result)
    assert list(sections) == [
        "window",
        "sun_limits",
        "advanced",
        *EXCEPTIONS,
    ]
    folded = collapsed(result)
    assert [name for name, closed in folded.items() if not closed] == ["window"]

    scope = {opt.key: opt.scope for opt in OPTS}
    for name, fields in sections.items():
        options = [key for key in fields if key in scope]
        expected = Scope.RECURRING if name in EXCEPTIONS else Scope.ONE_TIME
        assert {scope[key] for key in options} <= {expected}, name
    # Every setting this type uses is on the screen.
    on_form = {key for fields in sections.values() for key in fields}
    assert {
        opt.key
        for opt in OPTS
        if opt.scope is not Scope.INTERNAL and cover_type in opt.cover_types
    } - {CONF_ENTITIES} <= on_form


async def test_window_section_is_cover_type_and_facing_first(hass):
    result = await start_add(hass)
    assert list(shown(result)["window"])[:7] == [
        "preset",
        "name",
        CONF_COVER_ENTITY,
        CONF_SENSOR_TYPE,
        CONF_AZIMUTH,
        CONF_FOV_LEFT,
        CONF_FOV_RIGHT,
    ]


# ----------------------------------------------------------- minimal path


async def test_window_from_only_a_cover_and_azimuth_resolves_to_house_defaults(hass):
    """Plan P6: a cover and an azimuth are a valid window; the rest is default.

    The stored options are exactly the window's one-time setup on top of an
    empty house: every recurring setting resolves from the house defaults
    (the spec defaults until P5 stores a house), none from the window.
    """
    hass.states.async_set(COVER, "open", {"current_position": 50})
    result = await start_add(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "window": {CONF_COVER_ENTITY: COVER, CONF_AZIMUTH: 135},
            "sun_limits": {},
            "advanced": {},
            "exceptions_positions": {},
            "exceptions_schedule": {},
            "exceptions_climate": {},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_SENSOR_TYPE] == SensorType.BLIND
    assert hass.states.get(_position_sensor(hass, entry)).state not in (
        None,
        "unknown",
        "unavailable",
    )

    unit = hass.config.units.temperature_unit
    flat = legacy_flat(entry.options, temperature_unit=unit)
    setup = {opt.key: flat[opt.key] for opt in OPTS if opt.home is Level.WINDOW}
    profiles = Profiles(
        house=HouseProfile({}, temperature_unit=unit),
        windows={entry.entry_id: WindowOverrides(setup=setup)},
    )
    resolution = resolve_with_provenance(entry.entry_id, profiles)
    assert dict(resolution.values) == flat
    recurring = [opt.key for opt in OPTS if opt.scope is Scope.RECURRING]
    assert {key: resolution.provenance[key] for key in recurring} == dict.fromkeys(
        recurring, Source.DEFAULT
    )
    # Of the blind's own setup, everything but the cover and the azimuth is
    # the spec default too (another type's geometry is not stored).
    entered = {CONF_COVER_ENTITY, CONF_ENTITIES, CONF_AZIMUTH}
    blind = [
        opt
        for opt in OPTS
        if opt.home is Level.WINDOW and SensorType.BLIND in opt.cover_types
    ]
    assert {opt.key: setup[opt.key] for opt in blind if opt.key not in entered} == {
        opt.key: spec_default(opt, unit) for opt in blind if opt.key not in entered
    }
    assert {
        key: value
        for key, value in setup.items()
        if key not in {opt.key for opt in blind}
    } == dict.fromkeys(set(setup) - {opt.key for opt in blind})
    assert (setup[CONF_COVER_ENTITY], setup[CONF_AZIMUTH]) == (COVER, 135)


async def test_name_defaults_to_the_cover_name(hass):
    hass.states.async_set(COVER, "open", {"friendly_name": "Study blind"})
    result = await add_window(hass, {CONF_COVER_ENTITY: COVER})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Study blind"
    assert result["data"]["name"] == "Study blind"


async def test_cover_type_switch_keeps_what_was_entered(hass):
    result = await start_add(hass)
    result = await submit(
        hass,
        result,
        {
            "name": "Study",
            CONF_COVER_ENTITY: COVER,
            CONF_SENSOR_TYPE: SensorType.TILT,
            CONF_AZIMUTH: 100,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert CONF_TILT_DEPTH in shown(result)["window"]
    assert {
        key: prefilled(result)[key] for key in ("name", CONF_COVER_ENTITY, CONF_AZIMUTH)
    } == {"name": "Study", CONF_COVER_ENTITY: COVER, CONF_AZIMUTH: 100}

    result = await submit(hass, result, {CONF_COVER_ENTITY: COVER, CONF_AZIMUTH: 100})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.TILT
    # A tilted blind has no window height: the blind default was not kept.
    assert result["options"][CONF_HEIGHT_WIN] is None


async def test_switching_the_type_back_keeps_that_types_geometry(hass):
    result = await start_add(hass)
    result = await submit(
        hass,
        result,
        {
            CONF_COVER_ENTITY: COVER,
            CONF_SENSOR_TYPE: SensorType.TILT,
            CONF_HEIGHT_WIN: 2.4,
        },
    )
    assert CONF_HEIGHT_WIN not in shown(result)["window"]
    result = await submit(
        hass, result, {CONF_COVER_ENTITY: COVER, CONF_SENSOR_TYPE: SensorType.BLIND}
    )
    assert result["type"] is FlowResultType.FORM
    assert prefilled(result)[CONF_HEIGHT_WIN] == 2.4


async def test_a_cover_that_cannot_move_like_the_type_is_refused(hass):
    """The cover picker offers every cover now; the type is checked on submit."""
    hass.states.async_set(
        COVER,
        "open",
        {"supported_features": CoverEntityFeature.SET_TILT_POSITION},
    )
    result = await start_add(hass)
    result = await submit(hass, result, {CONF_COVER_ENTITY: COVER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_type_unsupported"}

    result = await submit(
        hass, result, {CONF_COVER_ENTITY: COVER, CONF_SENSOR_TYPE: SensorType.TILT}
    )
    result = await submit(hass, result, {CONF_COVER_ENTITY: COVER})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.TILT


# ------------------------------------------------------ copy from, presets


async def test_copy_from_prefills_everything_but_name_and_cover(hass):
    source = _window(hass, OTHER, **{CONF_TEMP_HIGH: 25.5})
    copied_from = dict(source.options)
    result = await start_add(hass)
    assert "copy_from" in shown(result)["window"]
    result = await submit(
        hass, result, {"copy_from": source.entry_id, CONF_COVER_ENTITY: COVER}
    )
    assert result["type"] is FlowResultType.FORM
    values = prefilled(result)
    # The source's type (the awning form), geometry and exceptions ...
    assert CONF_LENGTH_AWNING in shown(result)["window"]
    for key in (
        CONF_AZIMUTH,
        CONF_HEIGHT_WIN,
        CONF_LENGTH_AWNING,
        CONF_OVERHANG_DEPTH,
        CONF_DEFAULT_HEIGHT,
        CONF_TEMP_HIGH,
    ):
        assert values[key] == source.options[key], key
    # ... but not its identity: this window's cover stays, no name copied.
    assert values[CONF_COVER_ENTITY] == COVER
    assert "name" not in values

    result = await submit(hass, result, {**values, "name": "Study"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"name": "Study", CONF_SENSOR_TYPE: SensorType.AWNING}
    # (As copied: setting the new window up also migrates the source.)
    for key, value in copied_from.items():
        if key not in (CONF_COVER_ENTITY, CONF_ENTITIES):
            assert result["options"][key] == value, key
    assert result["options"][CONF_COVER_ENTITY] == COVER
    assert result["options"][CONF_ENTITIES] == [COVER]


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        (
            "glass_door_overhang",
            {
                CONF_HEIGHT_WIN: 2.0,
                CONF_DISTANCE: 0.1,
                CONF_FOV_LEFT: 40,
                CONF_FOV_RIGHT: 40,
                CONF_OVERHANG_DEPTH: 1.2,
                CONF_OVERHANG_HEIGHT: 2.3,
                CONF_MIN_ELEVATION: 5,
                CONF_MAX_ELEVATION: 40,
            },
        ),
        (
            "window",
            {
                CONF_HEIGHT_WIN: 2.0,
                CONF_DISTANCE: 0.1,
                CONF_FOV_LEFT: 60,
                CONF_FOV_RIGHT: 60,
                CONF_OVERHANG_DEPTH: None,
                CONF_OVERHANG_HEIGHT: None,
                CONF_MIN_ELEVATION: None,
                CONF_MAX_ELEVATION: None,
            },
        ),
    ],
    ids=["glass_door_overhang", "window"],
)
async def test_preset_fills_geometry_only(hass, preset, expected):
    entered = {
        "name": "Deck door",
        CONF_COVER_ENTITY: COVER,
        CONF_AZIMUTH: 145,
        CONF_DEFAULT_HEIGHT: 80,
        CONF_OVERHANG_DEPTH: 0.5,
    }
    result = await start_add(hass)
    result = await submit(hass, result, {**entered, "preset": preset})
    assert result["type"] is FlowResultType.FORM
    values = prefilled(result)
    for key, value in expected.items():
        assert values.get(key) == value, key
    # The name, cover, azimuth and a recurring value are the user's.
    assert {key: values[key] for key in ("name", CONF_COVER_ENTITY, CONF_AZIMUTH)} == {
        "name": "Deck door",
        CONF_COVER_ENTITY: COVER,
        CONF_AZIMUTH: 145,
    }
    assert values[CONF_DEFAULT_HEIGHT] == 80
    # Sun limits the preset set are shown open.
    assert collapsed(result)["sun_limits"] is (expected[CONF_MIN_ELEVATION] is None)

    result = await submit(hass, result, {**values, "preset": preset})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    for key, value in expected.items():
        assert result["options"][key] == value, key
    assert result["options"][CONF_DEFAULT_HEIGHT] == 80


# ------------------------------------------------------------ reconfigure


async def test_reconfigure_shows_the_one_time_settings_only(hass):
    entry = _window(hass, OTHER)
    result = await start_reconfigure(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert list(shown(result)) == ["window", "sun_limits", "advanced"]
    values = prefilled(result)
    assert values[CONF_COVER_ENTITY] == OTHER
    assert values["name"] == "Den south"
    assert values[CONF_LENGTH_AWNING] == 3.0
    assert "copy_from" not in shown(result)["window"]  # no other window


async def test_reconfigure_changes_setup_and_keeps_recurring_settings(hass):
    entry = _window(hass, OTHER, **{CONF_TEMP_HIGH: 25.5})
    before = dict(entry.options)
    result = await start_reconfigure(hass, entry)
    values = prefilled(result)
    del values[CONF_OVERHANG_DEPTH]  # the user clears it
    result = await submit(
        hass,
        result,
        {**values, "name": "Den door", CONF_COVER_ENTITY: COVER, CONF_HEIGHT_WIN: 2.2},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.title == "Den door"
    assert entry.data == {"name": "Den door", CONF_SENSOR_TYPE: SensorType.AWNING}
    assert entry.options[CONF_HEIGHT_WIN] == 2.2
    assert entry.options[CONF_OVERHANG_DEPTH] is None
    assert entry.options[CONF_COVER_ENTITY] == COVER
    assert entry.options[CONF_ENTITIES] == [COVER]
    # Recurring settings are the options form's: untouched.
    for key in (CONF_DEFAULT_HEIGHT, CONF_TEMP_HIGH):
        assert entry.options[key] == before[key]


async def test_reconfigure_keeps_the_shadow_overrides(hass):
    """Reconfigure must keep the window's P5 `overrides` (migration 1.4).

    Dropping them would make the next setup re-adopt the window and absorb
    the edit, so a real difference could never raise the settings repair.
    """
    overrides = {"window_key": "w", "values": {"sunset_position": 5}, "legacy": {}}
    entry = _window(hass, OTHER, overrides=overrides)
    result = await start_reconfigure(hass, entry)
    result = await submit(hass, result, {**prefilled(result), CONF_HEIGHT_WIN: 2.2})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.options["overrides"] == overrides


async def test_reconfigure_changes_the_cover_type(hass):
    entry = _window(hass, OTHER)
    result = await start_reconfigure(hass, entry)
    result = await submit(
        hass, result, {**prefilled(result), CONF_SENSOR_TYPE: SensorType.BLIND}
    )
    assert result["type"] is FlowResultType.FORM
    assert CONF_LENGTH_AWNING not in shown(result)["window"]
    assert prefilled(result)[CONF_HEIGHT_WIN] == 2.4  # kept across the switch
    result = await submit(hass, result, prefilled(result))
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_SENSOR_TYPE] == SensorType.BLIND
    # The awning's geometry stays stored (the runtime ignores it).
    assert entry.options[CONF_LENGTH_AWNING] == 3.0


async def test_reconfigure_refuses_a_cover_another_window_drives(hass):
    entry = _window(hass, OTHER)
    _window(hass, COVER, title="Office")
    result = await start_reconfigure(hass, entry)
    result = await submit(hass, result, {**prefilled(result), CONF_COVER_ENTITY: COVER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_in_use"}
    assert entry.options[CONF_COVER_ENTITY] == OTHER


async def test_reconfigure_of_the_house_entry_aborts(hass):
    hub = MockConfigEntry(
        domain=DOMAIN, title="Adaptive Cover All", data={"is_hub": True}, options={}
    )
    hub.add_to_hass(hass)
    result = await start_reconfigure(hass, hub)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_a_window"
