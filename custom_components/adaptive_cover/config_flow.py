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

A window drives one cover (ADR 0002): the forms refuse a cover another
window drives (window_cover.cover_problem), and a new entry's unique_id is
its cover's entity-registry id.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import voluptuous as vol
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import entity_registry as er

from .const import (
    _LOGGER,
    CONF_CLIMATE_MODE,
    CONF_COVER_ENTITY,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SensorType,
)
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
    """Return the windows "Copy from" offers: entry_id -> title, by title.

    Every window but ``exclude_entry_id`` (the one being reconfigured);
    never the house entry.
    """
    from .hub import is_hub_entry

    windows = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False)
        if entry.entry_id != exclude_entry_id and not is_hub_entry(entry)
    ]
    windows.sort(key=lambda entry: (entry.title.casefold(), entry.entry_id))
    return {entry.entry_id: entry.title for entry in windows}


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
    def for_entry(cls, hass: HomeAssistant, entry: ConfigEntry) -> WindowForm:
        """Return the Reconfigure form of ``entry``: its one-time settings shown."""
        values = {
            **entry.options,
            FIELD_NAME: entry.title,
            CONF_COVER_ENTITY: window_cover(entry.options),
        }
        return cls(
            hass,
            cover_type=entry.data.get(CONF_SENSOR_TYPE) or SensorType.BLIND,
            values=values,
            recurring=False,
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
            if (entry := self.hass.config_entries.async_get_entry(source)) is not None:
                filled |= copy_from_values(entry.data, entry.options)
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
    """Add a window (one screen) and reconfigure its one-time settings."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self._form: WindowForm | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_import(self, import_data: dict[str, Any] | None = None):
        """Programmatic entry creation.

        Two shapes: {} bootstraps the singleton hub; {name, sensor_type,
        options} creates a regular entry (used by the add_entry service so
        new windows never require the form).
        """
        from .hub import CONF_IS_HUB, HUB_ENTRY_NAME, HUB_UNIQUE_ID

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
        """Add a window: the one-screen form."""
        if self._form is None:
            self._form = WindowForm(self.hass)
        if user_input is not None:
            if (values := self._form.submit(user_input)) is not None:
                await self._async_set_cover_unique_id(values[CONF_COVER_ENTITY])
                return self.async_create_entry(
                    title=values[FIELD_NAME],
                    data=window_data(values),
                    options=new_window_options(values),
                )
        return self._show(self._form, "user")

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
        self.options = dict(config_entry.options)
        self.sensor_type: str = (
            self.current_config.get(CONF_SENSOR_TYPE) or SensorType.BLIND
        )
        self._shown_keys: set[str] = set()

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
            changed = {
                key: value
                for key, value in flat.items()
                if self.options.get(key) != value and value is not None
            }
            cleared = sorted(
                key
                for key, value in flat.items()
                if value is None and self.options.get(key) is not None
            )
            if changed or cleared:
                _LOGGER.info(
                    "Options updated for '%s': changed=%s cleared=%s",
                    self.current_config.get("name"),
                    sorted(changed),
                    cleared,
                )
            self.options.update(flat)
            if CONF_COVER_ENTITY in flat:
                self.options = with_cover(self.options, flat[CONF_COVER_ENTITY])
            return await self._update_options()

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

    async def _update_options(self) -> FlowResult:
        """Update config entry options."""
        return self.async_create_entry(title="", data=self.options)
