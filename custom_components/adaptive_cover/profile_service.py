"""``adaptive_cover.get_profile``: read the stored layered settings (P5).

A read-only, response-only service (any user may call it) for dashboards
such as the house card, which need the stored house, floor, area and
window values without the admin-only diagnostics download.

Response shapes (``scope`` / ``id`` as called):

- no scope: ``{"house": {"values", "temperature_unit"}, "floors": {floor_id:
  values}, "areas": {area_id: values}}`` -- every stored profile;
- ``house``: ``{"scope": "house", "id": None, "values",
  "temperature_unit"}`` -- the house profile (every house-level setting,
  the five toggles included);
- ``floor`` / ``area`` with ``id``: ``{"scope", "id", "values"}`` -- that
  profile, sparse (``{}`` when it stores nothing);
- ``window`` with ``id`` (a window key, or the window's Mode select
  entity): ``{"scope": "window", "id": window_key, "title", "area_id",
  "floor_id", "overrides": {"values", "legacy"}, "settings", "provenance"}``
  -- what the window stores itself, what it acts on (every setting,
  resolved) and where each value comes from (``window``, ``legacy``,
  ``area``, ``floor``, ``house`` or ``default``).
"""

from __future__ import annotations

from typing import Any, Final, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .layers import (
    ProfileError,
    check_scope,
    effective_settings,
    profile_values,
    window_overrides,
)
from .settings.shadow import AREAS, FLOORS, TEMPERATURE_UNIT
from .settings.spec import Level
from .shadow import lifted_hub, window_placement

SERVICE_GET_PROFILE: Final = "get_profile"
MODE_SELECT_SUFFIX: Final = "_mode_select"

GET_PROFILE_SCHEMA: Final = vol.Schema(
    {
        vol.Optional("scope"): vol.In(["house", "floor", "area", "window"]),
        vol.Optional("id"): vol.All(str, vol.Length(min=1)),
    }
)


def _window(hass: HomeAssistant, ref: str) -> ConfigEntry:
    """Find a window by its key or by its Mode select entity."""
    from .hub import is_hub_entry

    key = ref
    if "." in ref:
        row = er.async_get(hass).async_get(ref)
        if row is None or row.platform != DOMAIN:
            raise ServiceValidationError(f"{ref} is not an Adaptive Cover entity")
        key = (
            row.unique_id.removesuffix(MODE_SELECT_SUFFIX)
            if row.unique_id.endswith(MODE_SELECT_SUFFIX)
            else row.config_entry_id or ""
        )
    entry = hass.config_entries.async_get_entry(key)
    if entry is None or entry.domain != DOMAIN or is_hub_entry(entry):
        raise ServiceValidationError(f"No Adaptive Cover window {ref!r}")
    return entry


def window_profile(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return one window's stored overrides, resolved settings and sources."""
    settings = effective_settings(hass, entry)
    overrides = window_overrides(entry)
    placement = window_placement(hass, entry)
    return {
        "scope": "window",
        "id": entry.entry_id,
        "title": entry.title,
        "area_id": placement.area_id,
        "floor_id": placement.floor_id,
        "overrides": {
            "values": dict(overrides.values),
            "legacy": dict(overrides.legacy),
        },
        "settings": settings.options,
        "provenance": settings.sources,
    }


def get_profile(
    hass: HomeAssistant, scope: str | None, scope_id: str | None
) -> dict[str, Any]:
    """Build the ``get_profile`` response (see the module docstring)."""
    if scope == "window":
        if not scope_id:
            raise ServiceValidationError("a window needs its id")
        return window_profile(hass, _window(hass, scope_id))
    hub = lifted_hub(hass)
    if hub is None:
        raise ServiceValidationError("the house has no layered settings yet")
    unit = hub.options.get(TEMPERATURE_UNIT)
    if scope is None:
        return {
            "house": {
                "values": profile_values(hub.options, Level.HOUSE, None),
                "temperature_unit": unit,
            },
            "floors": {
                key: dict(values)
                for key, values in (hub.options.get(FLOORS) or {}).items()
            },
            "areas": {
                key: dict(values)
                for key, values in (hub.options.get(AREAS) or {}).items()
            },
        }
    level = Level(scope)
    try:
        check_scope(hass, level, scope_id)
    except ProfileError as err:
        raise ServiceValidationError(str(err)) from err
    response: dict[str, Any] = {
        "scope": scope,
        "id": scope_id,
        "values": profile_values(hub.options, level, scope_id),
    }
    if level is Level.HOUSE:
        response["temperature_unit"] = unit
    return response


def async_register_get_profile(hass: HomeAssistant) -> None:
    """Register ``adaptive_cover.get_profile`` (read-only; any user)."""
    from homeassistant.core import SupportsResponse

    async def handle(call: ServiceCall) -> ServiceResponse:
        return cast(
            ServiceResponse,
            get_profile(hass, call.data.get("scope"), call.data.get("id")),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PROFILE,
        handle,
        schema=GET_PROFILE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
