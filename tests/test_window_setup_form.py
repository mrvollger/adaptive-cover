"""The one-screen window form: add a window, reconfigure it (plan P6, P8).

Through the config-entry and subentry flow managers and entry states only:

- the add form is one screen (a fresh install's first window, or "Add
  window" on the house); recurring settings sit only in collapsed sections
  labelled as per-window exceptions;
- a window made from only a cover and an azimuth is valid and resolves to
  the house defaults;
- "Copy from" pre-fills everything but the name and the cover; presets
  fill geometry only;
- Reconfigure (a window subentry's) shows the same form, the exceptions
  collapsed, and changes the one-time settings without touching the
  recurring ones.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

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
    CONF_SUNSET_POS,
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
from custom_components.adaptive_cover.settings.spec import (
    OPTS,
    OPTS_BY_KEY,
    Level,
    Scope,
)

from .conftest import COMMON_OPTIONS
from .house_model import Window, mock_house
from .window_form import (
    add_window,
    collapsed,
    only_window,
    prefilled,
    record,
    show_type,
    shown,
    start_add,
    start_add_window,
    start_reconfigure,
    submit,
    window_subentries,
)
from .window_handle import window_settings

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


# Every recurring setting at its spec default (°C): the house a window of
# these tests lives in holds a value for each (as a real house does).
RECURRING_DEFAULTS = {
    key: value
    for key, value in legacy_flat({}, temperature_unit="°C").items()
    if OPTS_BY_KEY[key].scope is Scope.RECURRING
}


def _awning(cover: str, *, title: str = "Den south", **options) -> Window:
    """An existing window: an awning with its own geometry and exceptions."""
    return Window(
        name=title,
        sensor_type=SensorType.AWNING,
        options={
            **RECURRING_DEFAULTS,
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


async def _house(hass, *windows: Window):
    """A running house with ``windows`` (their covers exist)."""
    for window in windows:
        hass.states.async_set(window.options[CONF_COVER_ENTITY], "open", {})
    entry = mock_house(hass, list(windows))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _subentry(entry, cover: str):
    return next(
        subentry
        for subentry in window_subentries(entry)
        if subentry.data[CONF_COVER_ENTITY] == cover
    )


def _position_sensor(hass, key: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id("sensor", DOMAIN, f"{key}_Cover Position")


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

    The window stores its one-time setup only; the house, lifted from this
    one window, holds every recurring setting at its spec default, and the
    window overrides none of them.
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
    window = only_window(entry)
    stored = record(window)
    assert stored.cover_type == SensorType.BLIND
    assert hass.states.get(_position_sensor(hass, window.subentry_id)).state not in (
        None,
        "unknown",
        "unavailable",
    )

    # The house is lifted from this one window, which then stores no
    # override of its own (everything else is inherited).
    assert stored.overrides.values == {}
    assert stored.overrides.legacy == {}
    unit = hass.config.units.temperature_unit
    flat = legacy_flat(stored.options, temperature_unit=unit)
    setup = {opt.key: flat[opt.key] for opt in OPTS if opt.home is Level.WINDOW}
    profiles = Profiles(
        house=HouseProfile({}, temperature_unit=unit),
        windows={window.subentry_id: WindowOverrides(setup=setup)},
    )
    resolution = resolve_with_provenance(window.subentry_id, profiles)
    assert dict(resolution.values) == flat
    recurring = [opt.key for opt in OPTS if opt.scope is Scope.RECURRING]
    assert {key: resolution.provenance[key] for key in recurring} == dict.fromkeys(
        recurring, Source.DEFAULT
    )
    # ... and the house holds exactly those defaults: the window acts on them.
    settings = await window_settings(hass, window.subentry_id)
    assert {key: settings[key] for key in recurring} == {
        key: resolution.values[key] for key in recurring
    }
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
    window = only_window(result["result"])
    assert window.title == "Study blind"
    assert record(window).name == "Study blind"


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
    stored = record(only_window(result["result"]))
    assert stored.cover_type == SensorType.TILT
    # A tilted blind has no window height: the blind default was not kept.
    assert stored.geometry[CONF_HEIGHT_WIN] is None


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
    assert record(only_window(result["result"])).cover_type == SensorType.TILT


# ------------------------------------------------------ copy from, presets


async def test_copy_from_prefills_everything_but_name_and_cover(hass):
    source_window = _awning(OTHER, **{CONF_TEMP_HIGH: 25.5})
    entry = await _house(hass, source_window)
    source = _subentry(entry, OTHER)
    source_settings = await window_settings(hass, source.subentry_id)
    hass.states.async_set(COVER, "open", {})
    result = await start_add_window(hass, entry)
    assert "copy_from" in shown(result)["window"]
    result = await submit(
        hass, result, {"copy_from": source.subentry_id, CONF_COVER_ENTITY: COVER}
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
        assert values[key] == source_window.options[key], key
    # ... but not its identity: this window's cover stays, no name copied.
    assert values[CONF_COVER_ENTITY] == COVER
    assert "name" not in values

    result = await submit(hass, result, {**values, "name": "Study"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    copy = _subentry(entry, COVER)
    assert copy.title == "Study"
    assert record(copy).cover_type == SensorType.AWNING
    copied = record(copy).geometry
    for key, value in record(source).geometry.items():
        assert copied[key] == value, key
    # The copy acts on what its source acts on, but on its own cover.
    copy_settings = await window_settings(hass, copy.subentry_id)
    for key in source_window.options:
        if key not in (CONF_COVER_ENTITY, CONF_ENTITIES):
            assert copy_settings[key] == source_settings[key], key
    assert copy_settings[CONF_COVER_ENTITY] == COVER
    assert copy_settings[CONF_ENTITIES] == [COVER]


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
    await hass.async_block_till_done()
    window = only_window(result["result"])
    for key, value in expected.items():
        assert record(window).geometry[key] == value, key
    settings = await window_settings(hass, window.subentry_id)
    assert settings[CONF_DEFAULT_HEIGHT] == 80


# ------------------------------------------------------------ reconfigure


async def test_reconfigure_shows_the_window_setup_and_its_exceptions(hass):
    entry = await _house(hass, _awning(OTHER))
    result = await start_reconfigure(hass, entry, _subentry(entry, OTHER).subentry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert list(shown(result)) == ["window", "sun_limits", "advanced", *EXCEPTIONS]
    folded = collapsed(result)
    assert [name for name, closed in folded.items() if not closed] == ["window"]
    values = prefilled(result)
    assert values[CONF_COVER_ENTITY] == OTHER
    assert values["name"] == "Den south"
    assert values[CONF_LENGTH_AWNING] == 3.0
    assert values[CONF_DEFAULT_HEIGHT] == 97  # what it acts on
    assert "copy_from" not in shown(result)["window"]  # no other window


async def test_reconfigure_changes_setup_and_keeps_recurring_settings(hass):
    entry = await _house(hass, _awning(OTHER, **{CONF_TEMP_HIGH: 25.5}))
    hass.states.async_set(COVER, "open", {})
    key = _subentry(entry, OTHER).subentry_id
    before = await window_settings(hass, key)
    result = await start_reconfigure(hass, entry, key)
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
    window = entry.subentries[key]
    stored = record(window)
    assert window.title == "Den door"
    assert (stored.name, stored.cover_type) == ("Den door", SensorType.AWNING)
    assert stored.geometry[CONF_HEIGHT_WIN] == 2.2
    assert stored.geometry[CONF_OVERHANG_DEPTH] is None
    assert stored.cover == COVER
    # Recurring settings: untouched (shown as they are, so no exception).
    assert stored.overrides.values == {}
    after = await window_settings(hass, key)
    for option in (CONF_DEFAULT_HEIGHT, CONF_TEMP_HIGH):
        assert after[option] == before[option]


async def test_reconfigure_keeps_the_shadow_overrides(hass):
    """Reconfigure must keep the window's own recurring values (its overrides).

    A geometry change must not drop an exception the window stores.
    """
    entry = await _house(hass, _awning(OTHER))
    key = _subentry(entry, OTHER).subentry_id
    await hass.services.async_call(
        DOMAIN,
        "change_settings",
        {"config_entry": key, CONF_SUNSET_POS: 5},
        blocking=True,
    )
    await hass.async_block_till_done()
    overrides = entry.subentries[key].data["overrides"]
    assert overrides == {"values": {CONF_SUNSET_POS: 5}, "legacy": {}}
    result = await start_reconfigure(hass, entry, key)
    result = await submit(hass, result, {**prefilled(result), CONF_HEIGHT_WIN: 2.2})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[key].data["overrides"] == overrides
    assert record(entry.subentries[key]).geometry[CONF_HEIGHT_WIN] == 2.2


async def test_reconfigure_changes_the_cover_type(hass):
    entry = await _house(hass, _awning(OTHER))
    key = _subentry(entry, OTHER).subentry_id
    result = await start_reconfigure(hass, entry, key)
    result = await submit(
        hass, result, {**prefilled(result), CONF_SENSOR_TYPE: SensorType.BLIND}
    )
    assert result["type"] is FlowResultType.FORM
    assert CONF_LENGTH_AWNING not in shown(result)["window"]
    assert prefilled(result)[CONF_HEIGHT_WIN] == 2.4  # kept across the switch
    result = await submit(hass, result, prefilled(result))
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    stored = record(entry.subentries[key])
    assert stored.cover_type == SensorType.BLIND
    # The awning's geometry stays stored (the runtime ignores it).
    assert stored.geometry[CONF_LENGTH_AWNING] == 3.0


async def test_reconfigure_refuses_a_cover_another_window_drives(hass):
    entry = await _house(hass, _awning(OTHER), _awning(COVER, title="Office"))
    key = _subentry(entry, OTHER).subentry_id
    result = await start_reconfigure(hass, entry, key)
    result = await submit(hass, result, {**prefilled(result), CONF_COVER_ENTITY: COVER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cover_in_use"}
    assert record(entry.subentries[key]).cover == OTHER
