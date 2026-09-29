"""The entity surface: category, default visibility and name key per role.

One table, keyed by (platform, unique_id suffix), drives both

- the entity classes, which set it on NEW registry rows, and
- the config-entry migration 1.1 -> 1.2, which applies it to EXISTING rows.
  HA turns ``entity_registry_enabled_default`` into ``disabled_by`` only
  when a row is created, so an upgrade needs an explicit update. (HA
  refreshes ``entity_category`` on every load; the migration sets it too,
  so the rows are right before the platforms load.)

so a fresh install and an upgraded house end up with the same surface.
See docs/refactor_plan.md, "Entity surface" and "P1".

Unique_ids are never changed here: the suffix is only used as a lookup key.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity import Entity

from .const import CONF_ENTITIES, DOMAIN

# Hub unique_ids are f"{HUB_UNIQUE_ID}_{suffix}". Defined here (hub.py
# imports it) so this module does not import the hub.
HUB_UNIQUE_ID = "adaptive_cover_hub"


@dataclass(frozen=True)
class SurfaceSpec:
    """How one entity role appears in HA.

    translation_key names the entity through strings.json ("<Device> <Role>").
    category None means a primary entity.
    """

    translation_key: str | None
    category: EntityCategory | None = None
    enabled_default: bool = True


_DIAG = EntityCategory.DIAGNOSTIC
_CONFIG = EntityCategory.CONFIG

# Per-window entities, keyed by (platform, unique_id suffix after the
# "{entry_id}_" prefix). The suffixes are historical and frozen.
WINDOW_SURFACE: dict[tuple[str, str], SurfaceSpec] = {
    # Primary: what a person uses day to day.
    ("sensor", "Cover Position"): SurfaceSpec("target_position"),
    ("select", "mode_select"): SurfaceSpec("mode"),
    ("button", "Reset Manual Override"): SurfaceSpec("return_to_auto"),
    # Diagnostic, enabled: the card and the mutation tier read these.
    ("binary_sensor", "Manual Override"): SurfaceSpec("manual_override", _DIAG),
    ("binary_sensor", "Sun Infront"): SurfaceSpec("sun_motion", _DIAG),
    ("sensor", "Control Method"): SurfaceSpec("control", _DIAG),
    # Diagnostic, enabled for now: the dashboard card still reads the sun
    # and change sensors. They become disabled-by-default once the card reads
    # the Position attributes instead (P6).
    ("sensor", "Start Sun"): SurfaceSpec("start_sun", _DIAG),
    ("sensor", "End Sun"): SurfaceSpec("end_sun", _DIAG),
    ("sensor", "Next State Change"): SurfaceSpec("next_change", _DIAG),
    ("sensor", "Last State Change"): SurfaceSpec("last_change", _DIAG),
    # Config: still functional until P5 replaces them with Mode and house
    # settings.
    ("switch", "Toggle Control"): SurfaceSpec("control_toggle", _CONFIG),
    ("switch", "Manual Override"): SurfaceSpec("manual_toggle", _CONFIG),
    ("switch", "Climate Mode"): SurfaceSpec("switch_mode", _CONFIG),
    ("switch", "Outside Temperature"): SurfaceSpec("temp_toggle", _CONFIG),
    ("switch", "Lux"): SurfaceSpec("lux_toggle", _CONFIG),
    ("switch", "Irradiance"): SurfaceSpec("irradiance_toggle", _CONFIG),
}

# Number entities: unique_id suffix f"number_{option_key}", translation key
# = the option key.
NUMBER_SUFFIX_PREFIX = "number_"

# Hub entities, keyed by (platform, unique_id suffix after HUB_UNIQUE_ID_).
# All primary: the plan's house-level primary set.
HUB_SURFACE: dict[tuple[str, str], SurfaceSpec] = {
    ("cover", "cover"): SurfaceSpec(None),  # takes the device name
    ("select", "house_mode"): SurfaceSpec("house_mode"),
    ("button", "reset_all"): SurfaceSpec("return_all_to_auto"),
}


def window_surface(platform: str, suffix: str) -> SurfaceSpec | None:
    """Return the surface of a per-window entity, or None if unknown."""
    if platform == "number" and suffix.startswith(NUMBER_SUFFIX_PREFIX):
        return SurfaceSpec(suffix.removeprefix(NUMBER_SUFFIX_PREFIX), _CONFIG)
    return WINDOW_SURFACE.get((platform, suffix))


def apply_surface(entity: Entity, spec: SurfaceSpec | None) -> None:
    """Set an entity's name key, category and default visibility."""
    if spec is None:
        return
    entity._attr_translation_key = spec.translation_key
    entity._attr_entity_category = spec.category
    entity._attr_entity_registry_enabled_default = spec.enabled_default


def _surface_for_row(entry: ConfigEntry, row: er.RegistryEntry) -> SurfaceSpec | None:
    """Look up the surface of an existing registry row by its unique_id."""
    window_prefix = f"{entry.entry_id}_"
    hub_prefix = f"{HUB_UNIQUE_ID}_"
    if row.unique_id.startswith(window_prefix):
        return window_surface(row.domain, row.unique_id.removeprefix(window_prefix))
    if row.unique_id.startswith(hub_prefix):
        return HUB_SURFACE.get((row.domain, row.unique_id.removeprefix(hub_prefix)))
    return None


def _user_touched(row: er.RegistryEntry) -> bool:
    """Return True when the registry row carries a choice the user made.

    A user who renamed, re-iconed, labeled, aliased, categorized or placed
    an entity uses it; the migration must not hide it from them. Hidden or
    disabled rows already carry a visibility choice.
    """
    return bool(
        row.disabled_by is not None
        or row.hidden_by is not None
        or row.name is not None
        or row.icon is not None
        or row.area_id is not None
        or row.labels
        or row.categories
        or any(row.aliases)
    )


@callback
def async_apply_surface_to_registry(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Bring an entry's EXISTING registry rows to the current surface.

    - entity_category: always set to the surface value (users cannot set it).
    - disabled_by: set to INTEGRATION only for roles that are disabled by
      default, and only when the row carries no user choice (see
      _user_touched). Rows are never enabled here.

    Idempotent: a second run finds nothing to change. Returns the number of
    rows updated.
    """
    registry = er.async_get(hass)
    updated = 0
    for row in er.async_entries_for_config_entry(registry, entry.entry_id):
        if row.platform != DOMAIN:
            continue
        spec = _surface_for_row(entry, row)
        if spec is None:
            continue
        changes: dict = {}
        if row.entity_category != spec.category:
            changes["entity_category"] = spec.category
        if not spec.enabled_default and not _user_touched(row):
            changes["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION
        if changes:
            registry.async_update_entity(row.entity_id, **changes)
            updated += 1
    return updated


def cover_area_id(hass: HomeAssistant, covers: Iterable[str]) -> str | None:
    """Return the area of the first cover that has one.

    An entity's own area wins over its device's area, as in HA.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    areas = ar.async_get(hass)
    for cover in covers:
        row = ent_reg.async_get(cover)
        if row is None:
            continue
        area_id = row.area_id
        if area_id is None and row.device_id is not None:
            device = dev_reg.async_get(row.device_id)
            area_id = device.area_id if device is not None else None
        if area_id is not None and areas.async_get_area(area_id) is not None:
            return area_id
    return None


@callback
def async_copy_cover_area(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Give the window device its physical cover's area if it has none.

    Never overwrites an area already on the device (the user's choice).
    Returns the area_id that was set, or None.
    """
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device is None or device.area_id is not None:
        return None
    area_id = cover_area_id(hass, entry.options.get(CONF_ENTITIES) or [])
    if area_id is None:
        return None
    dev_reg.async_update_device(device.id, area_id=area_id)
    return area_id
