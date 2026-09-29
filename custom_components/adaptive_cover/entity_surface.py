"""The entity surface: category, default visibility and name key per role.

One table, keyed by (platform, unique_id suffix), drives the entity
classes. HA turns ``entity_registry_enabled_default`` into ``disabled_by``
only when a registry row is created.
See docs/refactor_plan.md, "Entity surface" and "P1".

Unique_ids are never changed here: the suffix is only used as a lookup key.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import Entity

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
    # Diagnostic, disabled by default.
    ("sensor", "Start Sun"): SurfaceSpec("start_sun", _DIAG, enabled_default=False),
    ("sensor", "End Sun"): SurfaceSpec("end_sun", _DIAG, enabled_default=False),
    ("sensor", "Next State Change"): SurfaceSpec(
        "next_change", _DIAG, enabled_default=False
    ),
    ("sensor", "Last State Change"): SurfaceSpec(
        "last_change", _DIAG, enabled_default=False
    ),
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
