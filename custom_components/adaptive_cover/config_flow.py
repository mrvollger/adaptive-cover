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
window drives (window_cover.cover_problem), and a new entry's unique_id is
its cover's entity-registry id.

P7 (ADR 0001): where a new window goes depends on the house
(``windows.uses_subentries``). A fresh install creates the house entry
with the first window as its subentry; a consolidated house adds windows
as subentries ("Add window" on the integration page, ``WindowSubentryFlow``,
or the config flow's user step, which adds one and says so); a house that
still has window entries keeps adding window entries until the owner
consolidates it. A window subentry's Reconfigure is the whole one-screen
form: its one-time settings and, collapsed, its exceptions (subentries
have no options flow). The house entry's options are the house settings
(``HouseOptionsFlow``).
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
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.util.ulid import ulid_now

from .const import (
    _LOGGER,
    CONF_CLIMATE_MODE,
    CONF_CLIMATE_ON,
    CONF_COVER_ENTITY,
    CONF_MANUAL_DETECTION,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_USE_IRRADIANCE,
    CONF_USE_LUX,
    CONF_USE_OUTSIDE_TEMP,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    SensorType,
)
from .layers import (
    copied_options,
    effective_options,
    is_layered,
    new_window_values,
    window_options_after,
)
from .settings.spec import Group, Kind, Level, Opt, Scope
from .windows import (
    WINDOW_KEY,
    WINDOW_SUBENTRY,
    WindowEntry,
    WindowLike,
    all_windows,
    find_window,
    house_entry,
    uses_subentries,
    window_subentry_data,
)
from .settings.lift import same_value
from .settings.normalize import normalize_cover, window_cover, with_cover
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
    options_section_fields,
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
# Reconfigure was opened on the house entry, which has no window setup.
ABORT_NOT_A_WINDOW: Final = "not_a_window"
# The config flow added a window to the house (P7): the flow ends here.
ABORT_WINDOW_ADDED: Final = "window_added"
# "Add window" on a house that still has window entries.
ABORT_CONSOLIDATE_FIRST: Final = "consolidate_first"
# The house options before the house has layered settings.
ABORT_NOT_LIFTED: Final = "house_not_lifted"

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

    Every window (entries, disabled ones too, and the house's subentries)
    but ``exclude_entry_id`` (the key of the one being reconfigured); never
    the house entry.
    """
    windows = [
        window
        for window in all_windows(hass, include_disabled=True)
        if window.window_key != exclude_entry_id
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


def window_data(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new window's entry data: its name and cover type."""
    return {"name": values[FIELD_NAME], CONF_SENSOR_TYPE: values[FIELD_SENSOR_TYPE]}


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


def reconfigured_window(
    data: Mapping[str, Any], options: Mapping[str, Any], values: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a window's entry data and options after the Reconfigure step.

    The form's values replace the stored ones; every option the form did
    not show (the recurring settings, another type's geometry) is kept.
    """
    changed = {key: value for key, value in values.items() if key in SETUP_OPTION_KEYS}
    new_options = with_cover({**options, **changed}, values.get(CONF_COVER_ENTITY))
    return {**data, **window_data(values)}, new_options


def _is_recurring(key: str) -> bool:
    opt = OPTS_BY_KEY.get(key)
    return opt is not None and opt.scope is Scope.RECURRING


def reconfigured_window_with_exceptions(
    hass: HomeAssistant, window: WindowLike, values: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a window's data and options after its whole-form Reconfigure.

    The one-time values replace the stored ones (``reconfigured_window``);
    a recurring value that differs from what the window acts on becomes
    the window's own value, sparsely (``layers.window_options_after``: a
    value equal to what it inherits, or a cleared field, inherits).
    """
    shown = effective_options(hass, window) if is_layered(hass, window) else {}
    shown = shown or dict(window.options)
    exceptions = {
        key: value
        for key, value in values.items()
        if _is_recurring(key) and not same_value(value, shown.get(key))
    }
    options = window_options_after(hass, window, exceptions)
    one_time = {key: value for key, value in values.items() if not _is_recurring(key)}
    return reconfigured_window(window.data, options, one_time)


def _copy_source(hass: HomeAssistant, window_key: str) -> WindowEntry | None:
    """Return the "Copy from" window with this key (a disabled entry too)."""
    return find_window(hass, window_key)


@callback
def async_promote_house(hass: HomeAssistant, house: ConfigEntry) -> None:
    """Make the house a 2.x entry before it holds a window subentry.

    Older versions then refuse the house entry instead of running it
    without its windows (ADR 0001: the rollback is the backup).
    """
    if house.version < HOUSE_ENTRY_VERSION:
        hass.config_entries.async_update_entry(
            house,
            version=HOUSE_ENTRY_VERSION,
            minor_version=HOUSE_ENTRY_MINOR_VERSION,
        )


def new_window_subentry_data(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new window subentry's data from the finished form values.

    A new window's key is its subentry_id, so its data holds no key.
    """
    return window_subentry_data(None, window_data(values), new_window_options(values))


@callback
def async_add_window_subentry(
    hass: HomeAssistant,
    house: ConfigEntry,
    data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> WindowEntry:
    """Add a window to the house as a subentry; return it.

    ``data`` and ``options`` are what a window entry would hold. The key
    of the new window is its subentry_id; its unique_id is its cover's
    registry id. The house's update listener starts it.
    """
    async_promote_house(hass, house)
    subentry = ConfigSubentry(
        data=MappingProxyType(window_subentry_data(None, data, options)),
        subentry_id=ulid_now(),
        subentry_type=WINDOW_SUBENTRY,
        title=str(data["name"]),
        unique_id=cover_registry_id(hass, window_cover(options)),
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
        cls, hass: HomeAssistant, entry: WindowLike, *, recurring: bool = False
    ) -> WindowForm:
        """Return the Reconfigure form of a window: its one-time settings shown.

        ``recurring=True`` also shows the exceptions sections, pre-filled
        with what the window acts on (a window subentry's Reconfigure).
        """
        options = dict(entry.options)
        if recurring and is_layered(hass, entry):
            options = effective_options(hass, entry)
        values = {
            **options,
            FIELD_NAME: entry.title,
            CONF_COVER_ENTITY: window_cover(entry.options),
        }
        return cls(
            hass,
            cover_type=entry.data.get(CONF_SENSOR_TYPE) or SensorType.BLIND,
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
                    window.data, copied_options(self.hass, window)
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
    """Add a window (one screen) and reconfigure its one-time settings.

    The flow's version is the house's (2.x): Home Assistant then loads a
    consolidated house. Window entries and a house that still has them
    are created at 1.x (``_legacy_version``), as before P7.
    """

    VERSION = HOUSE_ENTRY_VERSION
    MINOR_VERSION = HOUSE_ENTRY_MINOR_VERSION

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self._form: WindowForm | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow: the house settings, or a window's options."""
        from .hub import is_hub_entry

        if is_hub_entry(config_entry):
            return HouseOptionsFlow()
        return OptionsFlowHandler(config_entry)

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

    def _legacy_version(self) -> None:
        """Create the next entry at 1.x: the legacy model (a downgrade reads it)."""
        self.VERSION = CONFIG_ENTRY_VERSION
        self.MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    async def async_step_import(self, import_data: dict[str, Any] | None = None):
        """Programmatic entry creation.

        Two shapes: {} bootstraps the singleton hub (a window entry set up
        without one: the legacy model); {name, sensor_type, options}
        creates a window entry (used by the add_entry service on a house
        that still has window entries, and by the split repair).
        """
        from .hub import CONF_IS_HUB, HUB_ENTRY_NAME, HUB_UNIQUE_ID

        self._legacy_version()
        if import_data and import_data.get("name") and not import_data.get(CONF_IS_HUB):
            options = normalize_cover(import_data.get("options", {}))
            await self._async_set_cover_unique_id(window_cover(options))
            return self.async_create_entry(
                title=import_data["name"],
                data={
                    "name": import_data["name"],
                    CONF_SENSOR_TYPE: import_data.get(
                        CONF_SENSOR_TYPE, SensorType.BLIND
                    ),
                },
                options=options,
            )

        await self.async_set_unique_id(HUB_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=HUB_ENTRY_NAME,
            data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
            options={},
        )

    async def _async_set_cover_unique_id(self, cover: str | None) -> None:
        """Key the new entry by its cover's registry id; abort a duplicate."""
        await self.async_set_unique_id(
            cover_registry_id(self.hass, cover), raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

    def _show(self, form: WindowForm, step_id: str) -> ConfigFlowResult:
        return self.async_show_form(
            step_id=step_id, data_schema=form.schema(), errors=_form_errors(form)
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a window: the one-screen form (pre-filled from the house).

        Where it goes (P7): a fresh install creates the house with this
        window as its first subentry; a house that uses subentries gets
        one more (the flow then ends with "window added"); a house that
        still has window entries gets another window entry.
        """
        if self._form is None:
            self._form = WindowForm(self.hass, values=new_window_values(self.hass))
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                return await self._async_add_window(values)
        return self._show(self._form, "user")

    async def _async_add_window(self, values: Mapping[str, Any]) -> ConfigFlowResult:
        from .hub import CONF_IS_HUB, HUB_ENTRY_NAME, HUB_UNIQUE_ID

        house = house_entry(self.hass)
        if house is not None and uses_subentries(self.hass):
            async_add_window_subentry(
                self.hass, house, window_data(values), new_window_options(values)
            )
            return self.async_abort(
                reason=ABORT_WINDOW_ADDED,
                description_placeholders={"window": values[FIELD_NAME]},
            )
        if house is None and not all_windows(self.hass, include_disabled=True):
            # A fresh install: the house, with this window as its subentry.
            await self.async_set_unique_id(HUB_UNIQUE_ID)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=HUB_ENTRY_NAME,
                data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
                options={},
                subentries=[
                    {
                        "data": new_window_subentry_data(values),
                        "subentry_type": WINDOW_SUBENTRY,
                        "title": values[FIELD_NAME],
                        "unique_id": cover_registry_id(
                            self.hass, values[CONF_COVER_ENTITY]
                        ),
                    }
                ],
            )
        self._legacy_version()
        await self._async_set_cover_unique_id(values[CONF_COVER_ENTITY])
        return self.async_create_entry(
            title=values[FIELD_NAME],
            data=window_data(values),
            options=new_window_options(values),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change a window's one-time settings: the same form, no exceptions."""
        from .hub import is_hub_entry

        entry = self._get_reconfigure_entry()
        if is_hub_entry(entry):
            return self.async_abort(reason=ABORT_NOT_A_WINDOW)
        if self._form is None:
            self._form = WindowForm.for_entry(self.hass, entry)
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                data, options = reconfigured_window(entry.data, entry.options, values)
                # The entry's update listener reloads it.
                return self.async_update_and_abort(
                    entry, title=data["name"], data=data, options=options
                )
        return self._show(self._form, "reconfigure")


class OptionsFlowHandler(OptionsFlow):
    """Single-page options flow.

    Every applicable setting on one form, grouped into collapsible
    sections, with current values pre-filled.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry_id = config_entry.entry_id
        self.current_config: dict = dict(config_entry.data)
        # What the form shows: the settings the window acts on (P5 flip).
        self.options: dict[str, Any] = {}
        self.sensor_type: str = (
            self.current_config.get(CONF_SENSOR_TYPE) or SensorType.BLIND
        )
        self._shown_keys: set[str] = set()

    def _entry(self) -> ConfigEntry:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        assert entry is not None
        return entry

    def _section_fields(self) -> dict[str, dict]:
        """Build {section_name: fields} for this entry's type and features."""
        return options_section_fields(
            self.sensor_type,
            climate_on=bool(self.options.get(CONF_CLIMATE_MODE)),
            # The cover field shows the cover the window drives (none for
            # an entry from before P3 with several: the split repair fixes it).
            options={**self.options, CONF_COVER_ENTITY: window_cover(self.options)},
            temperature_unit=_temperature_unit(self.hass),
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and process the single options page."""
        entry = self._entry()
        # Before the house is lifted the window acts on its options.
        self.options = (
            effective_options(self.hass, entry)
            if is_layered(self.hass, entry)
            else dict(entry.options)
        )
        section_fields = self._section_fields()
        self._shown_keys = {
            marker.schema for fields in section_fields.values() for marker in fields
        }

        if user_input is not None:
            flat: dict = {}
            for section_data in user_input.values():
                if isinstance(section_data, dict):
                    flat.update(section_data)
            # Absent clearable fields were cleared by the user
            for key in CLEARABLE_KEYS & self._shown_keys:
                if key not in flat:
                    flat[key] = None
            # The wizard's cross-field checks, on the options as they would
            # be saved; and no cover another window drives.
            errors = cross_field_errors({**self.options, **flat})
            if cover := flat.get(CONF_COVER_ENTITY):
                if problem := cover_problem(
                    self.hass, [cover], exclude_entry_id=self._entry_id
                ):
                    errors[CONF_COVER_ENTITY] = problem
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(section_fields),
                    errors={"base": next(iter(errors.values()))},
                )
            edits = {
                key: value
                for key, value in flat.items()
                if not same_value(value, self.options.get(key))
            }
            changed = sorted(key for key, value in edits.items() if value is not None)
            cleared = sorted(key for key, value in edits.items() if value is None)
            if changed or cleared:
                _LOGGER.info(
                    "Options updated for '%s': changed=%s cleared=%s",
                    self.current_config.get("name"),
                    changed,
                    cleared,
                )
            # One-time settings to the options, recurring ones to the
            # window's overrides (layers.window_options_after).
            options = window_options_after(self.hass, entry, edits)
            if CONF_COVER_ENTITY in edits:
                options = with_cover(options, edits[CONF_COVER_ENTITY])
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init", data_schema=self._build_schema(section_fields)
        )

    def _build_schema(self, section_fields: dict[str, dict]) -> vol.Schema:
        """Assemble the sectioned one-page schema."""
        return vol.Schema(
            {
                vol.Required(name): section(
                    vol.Schema(fields),
                    {"collapsed": name != "covers_geometry"},
                )
                for name, fields in section_fields.items()
            }
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
        if not uses_subentries(self.hass):
            return self.async_abort(reason=ABORT_CONSOLIDATE_FIRST)
        if self._form is None:
            self._form = WindowForm(self.hass, values=new_window_values(self.hass))
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                async_promote_house(self.hass, self._get_entry())
                return self.async_create_entry(
                    title=values[FIELD_NAME],
                    data=new_window_subentry_data(values),
                    unique_id=cover_registry_id(self.hass, values[CONF_COVER_ENTITY]),
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
                data, options = reconfigured_window_with_exceptions(
                    self.hass, window, values
                )
                stored = window_subentry_data(
                    subentry.data.get(WINDOW_KEY), data, options
                )
                # The house's update listener rebuilds this window alone.
                return self.async_update_and_abort(
                    house,
                    subentry,
                    title=data["name"],
                    data=stored,
                    unique_id=cover_registry_id(self.hass, window_cover(options)),
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
        from .shadow import lifted_hub

        if lifted_hub(self.hass) is None:
            return self.async_abort(reason=ABORT_NOT_LIFTED)
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
