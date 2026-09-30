"""The entity surface: category, default visibility and name key per role.

One table, keyed by (platform, unique_id suffix), drives the entity
classes, which set it on their registry rows. (Until v2.1 the config-entry
migrations 1.2 and 1.5 also applied it to existing rows; every house that
runs v2.1 went through them on v2.0.x.) See docs/refactor_plan.md,
"Entity surface" and "P1".

Unique_ids are never changed here: the suffix is only used as a lookup key.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity import Entity

from .windows import WindowEntry

# Hub unique_ids are f"{HUB_UNIQUE_ID}_{suffix}". Defined here (hub.py
# imports it) so this module does not import the hub.
HUB_UNIQUE_ID = "adaptive_cover_hub"


@dataclass(frozen=True)
class SurfaceSpec:
    """How one entity role appears in HA.

    translation_key names the entity through strings.json ("<Device> <Role>").
    category None means a primary entity. visible_default False hides the
    entity (hidden_by integration) but keeps it enabled.
    """

    translation_key: str | None
    category: EntityCategory | None = None
    enabled_default: bool = True
    visible_default: bool = True


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
    # The six per-window switches (hidden aliases since the P5 flip) are
    # gone since v2.1: migration 3.1 removes their rows (upgrade.py).
}

# Hub entities, keyed by (platform, unique_id suffix after HUB_UNIQUE_ID_).
# The plan's house-level primary set, then the house settings (P5 flip,
# house_settings.py): the Climate switch is primary, the rest CONFIG.
HUB_SURFACE: dict[tuple[str, str], SurfaceSpec] = {
    ("cover", "cover"): SurfaceSpec(None),  # takes the device name
    ("select", "house_mode"): SurfaceSpec("house_mode"),
    ("button", "reset_all"): SurfaceSpec("return_all_to_auto"),
    ("switch", "climate_on"): SurfaceSpec("climate_on"),
    ("switch", "manual_detection"): SurfaceSpec("manual_detection", _CONFIG),
    ("switch", "use_outside_temp"): SurfaceSpec("use_outside_temp", _CONFIG),
    ("switch", "use_lux"): SurfaceSpec("use_lux", _CONFIG),
    ("switch", "use_irradiance"): SurfaceSpec("use_irradiance", _CONFIG),
    ("number", "temp_low"): SurfaceSpec("temp_low", _CONFIG),
    ("number", "temp_high"): SurfaceSpec("temp_high", _CONFIG),
    ("number", "manual_override_duration"): SurfaceSpec(
        "manual_override_duration", _CONFIG
    ),
    ("number", "eye_height"): SurfaceSpec("eye_height", _CONFIG),
    ("number", "occupied_distance"): SurfaceSpec("occupied_distance", _CONFIG),
    ("number", "privacy_offset"): SurfaceSpec("privacy_offset", _CONFIG),
    ("time", "end_time"): SurfaceSpec("end_time", _CONFIG),
    ("time", "quiet_start"): SurfaceSpec("quiet_start", _CONFIG),
    ("time", "quiet_end"): SurfaceSpec("quiet_end", _CONFIG),
}


def window_surface(platform: str, suffix: str) -> SurfaceSpec | None:
    """Return the surface of a per-window entity, or None if unknown."""
    return WINDOW_SURFACE.get((platform, suffix))


def apply_surface(entity: Entity, spec: SurfaceSpec | None) -> None:
    """Set an entity's name key, category and default visibility."""
    if spec is None:
        return
    entity._attr_translation_key = spec.translation_key
    entity._attr_entity_category = spec.category
    entity._attr_entity_registry_enabled_default = spec.enabled_default
    entity._attr_entity_registry_visible_default = spec.visible_default


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
def async_copy_cover_area(hass: HomeAssistant, window: WindowEntry) -> str | None:
    """Give the window device its physical cover's area if it has none.

    Never overwrites an area already on the device (the user's choice).
    Returns the area_id that was set, or None.
    """
    from .windows import window_device

    dev_reg = dr.async_get(hass)
    device = window_device(hass, window)
    if device is None or device.area_id is not None:
        return None
    area_id = cover_area_id(hass, window.covers)
    if area_id is None:
        return None
    dev_reg.async_update_device(device.id, area_id=area_id)
    return area_id
