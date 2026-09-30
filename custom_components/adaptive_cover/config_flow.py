"""Config flow for Adaptive Cover integration.

Adding a window is one screen (plan P6): an expanded Window section (the
cover, its type, where the window faces and the geometry that type needs)
and collapsed sections for everything else, all generated from the option
spec (``settings/schema.py``). A cover and an azimuth are enough; every
other field starts at its spec default. "Copy from" pre-fills the form from
another window and a preset fills typical geometry.

The same screen without the recurring exceptions is the Reconfigure step,
for the one-time settings (cover, type, geometry). The options form stays
the everyday editor.

The form is ``WindowForm`` plus plain functions (``setup_errors``,
``new_window_options``, ``reconfigured_window``), so a ConfigSubentryFlow
(P7) can drive it too; the flow classes only show it and store the result.

Since the P5 flip the forms show what a window acts on (its resolved
settings, ``layers.py``) and store edits where they belong: one-time
settings in the window's options, recurring ones as the window's sparse
overrides (a value equal to what it inherits, or a cleared field, means
"inherit"). A new window starts from the house's settings, and "Copy
from" copies what the source window acts on.

A window drives one cover (ADR 0002): the forms refuse a cover another
window drives (window_cover.cover_problem), and a new window's unique_id
is its cover's entity-registry id.

The house entry is the integration's one config entry (ADR 0001;
``single_config_entry``). A fresh install creates it with its first window
(the config flow's user step, ``initial_house_options``); after that every
window is added as a subentry ("Add window" on the integration page,
``WindowSubentryFlow``). A window subentry's Reconfigure is the whole
one-screen form: its one-time settings and, collapsed, its exceptions
(subentries have no options flow). The house entry's options are the house
settings (``HouseOptionsFlow``).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

import voluptuous as vol
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.util.ulid import ulid_now

from .const import (
    _LOGGER,
    CONF_CLIMATE_ON,
    CONF_COVER_ENTITY,
    CONF_MANUAL_DETECTION,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    DOMAIN,
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    SensorType,
)
from .layers import (
    copied_options,
    effective_options,
    initial_house_options,
    new_window_record,
    new_window_values,
    window_record_after,
)
from .settings.spec import Group, Kind, Level, Opt, Scope
from .settings.window_record import GEOMETRY_KEYS, WindowRecord, record_from_options
from .windows import (
    WINDOW_SUBENTRY,
    WindowEntry,
    all_windows,
    find_window,
)
from .settings.lift import same_value
from .settings.normalize import with_cover
from .settings.schema import (
    CLEARABLE_KEYS,
    FIELD_COPY_FROM,
    FIELD_NAME,
    FIELD_PRESET,
    FIELD_SENSOR_TYPE,
    PRESETS,
    SETUP_OPTION_KEYS,
    copy_from_values,
    form_validator,
    flatten_sections,
    preset_values,
    setup_schema,
    setup_section,
    setup_section_fields,
)
from .settings.spec import OPTS, OPTS_BY_KEY
from .settings.validate import cross_field_errors
from .window_cover import cover_problem, cover_registry_id

# The picked cover cannot move the way the picked cover type needs.
ERROR_COVER_TYPE: Final = "cover_type_unsupported"
# "Add window" on a house that has not migrated to 3.x (upgrade.py).
ABORT_CONSOLIDATE_FIRST: Final = "consolidate_first"

_TYPE_FEATURE: Final = {
    SensorType.BLIND: CoverEntityFeature.SET_POSITION,
    SensorType.AWNING: CoverEntityFeature.SET_POSITION,
    SensorType.TILT: CoverEntityFeature.SET_TILT_POSITION,
}


def _temperature_unit(hass: HomeAssistant) -> str:
    """HA's temperature unit: climate thresholds are stored in it."""
    return hass.config.units.temperature_unit


# ------------------------------------------------------------ window form


def cover_supports_type(hass: HomeAssistant, cover: str, cover_type: str) -> bool:
    """Return whether ``cover`` can move the way ``cover_type`` needs.

    A blind or awning sets a position, a tilted blind sets a tilt. Only a
    cover whose state says it lacks that feature is refused; a cover
    without a state (yet) passes.
    """
    state = hass.states.get(cover)
    features = state.attributes.get(ATTR_SUPPORTED_FEATURES) if state else None
    if features is None:
        return True
    return bool(int(features) & _TYPE_FEATURE[cover_type])


def cover_name(hass: HomeAssistant, cover: str) -> str:
    """Return a new window's default name: its cover's name."""
    if (state := hass.states.get(cover)) is not None:
        return state.name
    if (row := er.async_get(hass).async_get(cover)) is not None:
        return row.name or row.original_name or cover
    return cover


def copy_sources(
    hass: HomeAssistant, *, exclude_entry_id: str | None = None
) -> dict[str, str]:
    """Return the windows "Copy from" offers: window key -> title, by title.

    Every window of the house but ``exclude_entry_id`` (the key of the one
    being reconfigured).
    """
    windows = [
        window for window in all_windows(hass) if window.window_key != exclude_entry_id
    ]
    windows.sort(key=lambda window: (window.title.casefold(), window.window_key))
    return {window.window_key: window.title for window in windows}


def setup_errors(
    hass: HomeAssistant,
    values: Mapping[str, Any],
    cover_type: str,
    *,
    exclude_entry_id: str | None = None,
) -> dict[str, str]:
    """Return the setup form's problems as ``{field: error_key}``.

    The cross-field rules (settings/validate.py), then the cover: exactly
    one, driven by no other window (``exclude_entry_id`` is the window being
    reconfigured), and able to move the way the cover type needs.
    """
    errors = cross_field_errors(values)
    cover = values.get(CONF_COVER_ENTITY)
    covers = [cover] if cover else []
    if problem := cover_problem(hass, covers, exclude_entry_id=exclude_entry_id):
        errors[CONF_COVER_ENTITY] = problem
    elif cover and not cover_supports_type(hass, cover, cover_type):
        errors[CONF_COVER_ENTITY] = ERROR_COVER_TYPE
    return errors


def new_window_options(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return the options a window added from the form stores.

    Every form option: the value the form sent, or None where the form did
    not show it (another cover type's geometry). The cover goes into both
    cover keys (``with_cover``).
    """
    options = {
        opt.key: values.get(opt.key) for opt in OPTS if opt.key in SETUP_OPTION_KEYS
    }
    options[CONF_MODE] = OPTS_BY_KEY[CONF_MODE].default
    return with_cover(options, values.get(CONF_COVER_ENTITY))


def _is_recurring(key: str) -> bool:
    opt = OPTS_BY_KEY.get(key)
    return opt is not None and opt.scope is Scope.RECURRING


def reconfigured_window(
    hass: HomeAssistant, window: WindowEntry, values: Mapping[str, Any]
) -> WindowRecord:
    """Return a window's record after its whole-form Reconfigure.

    The one-time values (the name, the cover, the cover type, the
    geometry) replace the stored ones; every one-time setting the form did
    not show (another type's geometry) is kept. A recurring value that
    differs from what the window acts on becomes the window's own value,
    sparsely (``layers.window_record_after``: a value equal to what it
    inherits, or a cleared field, inherits).
    """
    shown = effective_options(hass, window)
    exceptions = {
        key: value
        for key, value in values.items()
        if _is_recurring(key) and not same_value(value, shown.get(key))
    }
    record = window_record_after(hass, window, exceptions)
    geometry = {
        **record.geometry,
        **{key: value for key, value in values.items() if key in GEOMETRY_KEYS},
    }
    return record.with_changes(
        name=values[FIELD_NAME],
        cover=values.get(CONF_COVER_ENTITY) or None,
        cover_type=values[FIELD_SENSOR_TYPE],
        geometry=geometry,
    )


def _copy_source(hass: HomeAssistant, window_key: str) -> WindowEntry | None:
    """Return the "Copy from" window with this key."""
    return find_window(hass, window_key)


@callback
def async_add_window_subentry(
    hass: HomeAssistant,
    house: ConfigEntry,
    name: str,
    cover_type: str,
    options: Mapping[str, Any],
) -> WindowEntry:
    """Add a window to the house as a subentry; return it.

    ``options`` are the flat values the window is created with (a form's
    or a service's). The key of the new window is its subentry_id; its
    unique_id is its cover's registry id. The house's update listener
    starts it.
    """
    record = new_window_record(hass, house, name, cover_type, options)
    subentry = ConfigSubentry(
        data=MappingProxyType(record.as_data()),
        subentry_id=ulid_now(),
        subentry_type=WINDOW_SUBENTRY,
        title=name,
        unique_id=cover_registry_id(hass, record.cover),
    )
    hass.config_entries.async_add_subentry(house, subentry)
    return WindowEntry(house, subentry.subentry_id)


class WindowForm:
    """The one-screen window form, between one show and the next.

    Plain state and two calls, no flow API, so the ConfigFlow steps below
    and a ConfigSubentryFlow (P7) drive the same form:

    - ``schema()``: the form to show now;
    - ``submit(user_input)``: the finished values, or None when the form
      must show again. It shows again, filled in, right after "Copy from",
      a preset or another cover type is picked (so the user sees what
      changed), and with ``errors`` when a check fails.

    The finished values are the flat form values plus ``name`` (the
    cover's name when left empty) and ``sensor_type``.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        cover_type: str = SensorType.BLIND,
        values: Mapping[str, Any] | None = None,
        recurring: bool = True,
        entry_id: str | None = None,
    ) -> None:
        """Start a form for ``cover_type`` pre-filled with ``values``.

        ``recurring=False`` leaves out the exceptions sections;
        ``entry_id`` is the window being reconfigured (its own cover is not
        "in use", and it is not offered as a copy source).
        """
        self.hass = hass
        self.cover_type = cover_type
        self.values: dict[str, Any] = dict(values or {})
        self.recurring = recurring
        self.entry_id = entry_id
        self.errors: dict[str, str] = {}
        self._expanded: frozenset[str] = frozenset()
        # The copy source and preset already filled in (not applied again).
        self._applied: dict[str, str | None] = {
            FIELD_COPY_FROM: None,
            FIELD_PRESET: None,
        }

    @classmethod
    def for_entry(
        cls, hass: HomeAssistant, entry: WindowEntry, *, recurring: bool = False
    ) -> WindowForm:
        """Return the Reconfigure form of a window: its one-time settings shown.

        ``recurring=True`` also shows the exceptions sections, pre-filled
        with what the window acts on (a window subentry's Reconfigure).
        """
        options = effective_options(hass, entry) if recurring else entry.options
        values = {
            **options,
            FIELD_NAME: entry.title,
            CONF_COVER_ENTITY: entry.cover,
        }
        return cls(
            hass,
            cover_type=entry.cover_type,
            values=values,
            recurring=recurring,
            entry_id=entry.entry_id,
        )

    def _section_fields(self) -> dict[str, dict[vol.Marker, Any]]:
        return setup_section_fields(
            self.cover_type,
            values=self.values,
            temperature_unit=_temperature_unit(self.hass),
            windows=copy_sources(self.hass, exclude_entry_id=self.entry_id),
            recurring=self.recurring,
        )

    def schema(self) -> vol.Schema:
        """Return the form to show now."""
        return setup_schema(self._section_fields(), expanded=self._expanded)

    def submit(self, user_input: Mapping[str, Any]) -> dict[str, Any] | None:
        """Take one submitted form; return the finished values or None."""
        shown = {
            str(marker)
            for fields in self._section_fields().values()
            for marker in fields
        }
        flat = flatten_sections(user_input)
        # A clearable field left empty clears the option.
        for key in CLEARABLE_KEYS & shown:
            flat.setdefault(key, None)
        picked = {field: flat.pop(field, None) for field in self._applied}
        cover_type = flat.pop(FIELD_SENSOR_TYPE, None) or self.cover_type
        filled = self._template_values(picked)
        cover_type = filled.pop(FIELD_SENSOR_TYPE, cover_type)
        self._applied = picked
        self.errors = {}
        # Earlier values stay underneath: a field the form does not show now
        # (another type's geometry) keeps its value for a later switch back.
        if filled or cover_type != self.cover_type:
            # Show the form again with the new values; open the sections
            # they changed.
            self._expanded = frozenset(
                setup_section(OPTS_BY_KEY[key])
                for key, value in filled.items()
                if value != flat.get(key)
            )
            self.values = {**self.values, **flat, **filled, **picked}
            self.cover_type = cover_type
            return None
        self._expanded = frozenset()
        self.values = {**self.values, **flat, **picked}
        self.errors = setup_errors(
            self.hass, flat, cover_type, exclude_entry_id=self.entry_id
        )
        if self.errors:
            return None
        cover = flat[CONF_COVER_ENTITY]
        return {
            **flat,
            FIELD_NAME: flat.get(FIELD_NAME) or cover_name(self.hass, cover),
            FIELD_SENSOR_TYPE: cover_type,
        }

    def _template_values(self, picked: Mapping[str, str | None]) -> dict[str, Any]:
        """Return the values a newly picked copy source and preset fill in."""
        filled: dict[str, Any] = {}
        source = picked[FIELD_COPY_FROM]
        if source and source != self._applied[FIELD_COPY_FROM]:
            if (window := _copy_source(self.hass, source)) is not None:
                filled |= copy_from_values(
                    {CONF_SENSOR_TYPE: window.cover_type},
                    copied_options(self.hass, window),
                )
        preset = picked[FIELD_PRESET]
        if preset and preset in PRESETS and preset != self._applied[FIELD_PRESET]:
            filled |= preset_values(preset)
        return filled


# ------------------------------------------------------------------ flows


def _form_errors(form: WindowForm) -> dict[str, str] | None:
    """Return the form's first problem, shown above the form.

    HA shows no error on a field inside a section, so the options form and
    this form show one error for the whole form.
    """
    if not form.errors:
        return None
    return {"base": next(iter(form.errors.values()))}


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Create the house with its first window (the one-screen form).

    The integration has one config entry (``single_config_entry``): Home
    Assistant starts this flow only while there is none. Every later
    window is a subentry ("Add window", ``WindowSubentryFlow``).
    """

    VERSION = HOUSE_ENTRY_VERSION
    MINOR_VERSION = HOUSE_ENTRY_MINOR_VERSION

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self._form: WindowForm | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HouseOptionsFlow:
        """Get the options flow: the house settings."""
        return HouseOptionsFlow()

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Only the house has options (a 1.x window entry left behind has none)."""
        from .hub import is_hub_entry

        return is_hub_entry(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types: the house adds windows ("Add window")."""
        from .hub import is_hub_entry

        if is_hub_entry(config_entry):
            return {WINDOW_SUBENTRY: WindowSubentryFlow}
        return {}

    def _show(self, form: WindowForm, step_id: str) -> ConfigFlowResult:
        return self.async_show_form(
            step_id=step_id, data_schema=form.schema(), errors=_form_errors(form)
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the house with its first window: the one-screen form."""
        if self._form is None:
            self._form = WindowForm(self.hass, values=new_window_values(self.hass))
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                return await self._async_create_house(values)
        return self._show(self._form, "user")

    async def _async_create_house(self, values: Mapping[str, Any]) -> ConfigFlowResult:
        """Create the house, lifted from its first window, with that window in it."""
        from .hub import CONF_IS_HUB, HUB_ENTRY_NAME, HUB_UNIQUE_ID

        await self.async_set_unique_id(HUB_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        options = new_window_options(values)
        cover_type = values[FIELD_SENSOR_TYPE]
        house_options, overrides = initial_house_options(self.hass, cover_type, options)
        record = record_from_options(
            values[FIELD_NAME], cover_type, options, overrides=overrides
        )
        return self.async_create_entry(
            title=HUB_ENTRY_NAME,
            data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
            options=house_options,
            subentries=[
                {
                    "data": record.as_data(),
                    "subentry_type": WINDOW_SUBENTRY,
                    "title": values[FIELD_NAME],
                    "unique_id": cover_registry_id(self.hass, record.cover),
                }
            ],
        )


# ------------------------------------------------------------ subentries


class WindowSubentryFlow(ConfigSubentryFlow):
    """Add a window to the house, or reconfigure one ("window" subentries, P7).

    Add is the one-screen form, as the config flow's. Reconfigure is the
    same form with the window's values: its one-time settings and, in the
    collapsed exceptions sections, what it acts on (a subentry has no
    options flow). Edits land where they belong (one-time settings in the
    window's options, recurring ones as its sparse overrides); the house's
    update listener rebuilds only this window.
    """

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self._form: WindowForm | None = None

    def _show(self, step_id: str) -> SubentryFlowResult:
        assert self._form is not None
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._form.schema(),
            errors=_form_errors(self._form),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a window: the one-screen form (pre-filled from the house)."""
        from .upgrade import is_current_house

        house = self._get_entry()
        if not is_current_house(house):
            return self.async_abort(reason=ABORT_CONSOLIDATE_FIRST)
        if self._form is None:
            self._form = WindowForm(self.hass, values=new_window_values(self.hass))
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                record = new_window_record(
                    self.hass,
                    house,
                    values[FIELD_NAME],
                    values[FIELD_SENSOR_TYPE],
                    new_window_options(values),
                )
                return self.async_create_entry(
                    title=values[FIELD_NAME],
                    data=record.as_data(),
                    unique_id=cover_registry_id(self.hass, record.cover),
                )
        return self._show("user")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a window: its one-time settings and its exceptions."""
        house = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        window = WindowEntry(house, subentry.subentry_id)
        if self._form is None:
            self._form = WindowForm.for_entry(self.hass, window, recurring=True)
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                record = reconfigured_window(self.hass, window, values)
                # The house's update listener rebuilds this window alone.
                return self.async_update_and_abort(
                    house,
                    subentry,
                    title=record.name,
                    data=record.as_data(),
                    unique_id=cover_registry_id(self.hass, record.cover),
                )
        return self._show("reconfigure")


# ------------------------------------------------------------ the house

# The house form's sections: spec groups, in order. The toggles that
# replaced the per-window switches sit with their topic.
HOUSE_SECTIONS: Final[Mapping[str, tuple[Group, ...]]] = MappingProxyType(
    {
        "house_positions": (Group.COVER, Group.SUN),
        "house_schedule": (Group.AUTOMATION,),
        "house_climate": (Group.CLIMATE_TOGGLE, Group.CLIMATE, Group.WEATHER),
    }
)
HOUSE_TOGGLE_SECTIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        CONF_MANUAL_DETECTION: "house_schedule",
        CONF_CLIMATE_ON: "house_climate",
        CONF_USE_OUTSIDE_TEMP: "house_climate",
        CONF_USE_LUX: "house_climate",
        CONF_USE_IRRADIANCE: "house_climate",
    }
)
ERROR_HOUSE_SETTING: Final = "house_setting_invalid"


def house_opts() -> list[Opt]:
    """Return the settings the house form shows: every one the house may store."""
    from .layers import SPEC
    from .settings.resolve import allowed_levels

    return [
        opt
        for opt in SPEC.values()
        if opt.scope is Scope.RECURRING and Level.HOUSE in allowed_levels(opt)
    ]


def _house_section(opt: Opt) -> str:
    if opt.key in HOUSE_TOGGLE_SECTIONS:
        return HOUSE_TOGGLE_SECTIONS[opt.key]
    return next(name for name, groups in HOUSE_SECTIONS.items() if opt.group in groups)


def house_section_fields(
    values: Mapping[str, Any], temperature_unit: str | None
) -> dict[str, dict[vol.Marker, Any]]:
    """``{section: fields}`` of the house settings form, pre-filled with ``values``."""
    sections: dict[str, dict[vol.Marker, Any]] = {name: {} for name in HOUSE_SECTIONS}
    for opt in house_opts():
        marker = vol.Optional(
            opt.key, description={"suggested_value": values.get(opt.key)}
        )
        if opt.kind is Kind.INTERNAL:
            validator: Any = selector.BooleanSelector()
        else:
            validator = form_validator(
                opt, "options", temperature_unit=temperature_unit
            )
        sections[_house_section(opt)][marker] = validator
    return sections


class HouseOptionsFlow(OptionsFlow):
    """The house settings: every value the house holds, on one form (P7).

    The house entry's options. The same values as the house entities and
    ``adaptive_cover.set_profile`` (scope house); a floor, a room or a
    window may still have its own. Saving stores what changed
    (``layers.async_set_profile``) and every window acts on it at once.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open the house settings."""
        return await self.async_step_house(user_input)

    def _current(self) -> dict[str, Any]:
        from .layers import profile_values
        from .settings.resolve import spec_default

        unit = _temperature_unit(self.hass)
        stored = profile_values(self.config_entry.options, Level.HOUSE, None)
        return {
            opt.key: stored[opt.key] if opt.key in stored else spec_default(opt, unit)
            for opt in house_opts()
        }

    async def async_step_house(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the house settings."""
        from .layers import ProfileError, async_set_profile, async_settings_changed
        from .settings.schema import may_be_empty

        current = self._current()
        sections = house_section_fields(current, _temperature_unit(self.hass))
        errors: dict[str, str] | None = None
        if user_input is not None:
            flat = flatten_sections(user_input)
            changes: dict[str, Any] = {}
            for opt in house_opts():
                if opt.key in flat:
                    value = flat[opt.key]
                elif opt.clearable and may_be_empty(opt):
                    value = None  # a cleared field (the form leaves it out)
                else:
                    continue
                if not same_value(value, current.get(opt.key)):
                    changes[opt.key] = value
            try:
                changed = async_set_profile(self.hass, Level.HOUSE, None, changes)
            except ProfileError as err:
                _LOGGER.warning("House settings not saved: %s", err)
                errors = {"base": ERROR_HOUSE_SETTING}
            else:
                if changed:
                    _LOGGER.info("House settings changed: %s", changed)
                    await async_settings_changed(self.hass)
                return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="house",
            data_schema=vol.Schema(
                {
                    vol.Required(name): section(
                        vol.Schema(fields), {"collapsed": False}
                    )
                    for name, fields in sections.items()
                }
            ),
            errors=errors,
        )
