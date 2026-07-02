"""Shared entity helpers for the Adaptive Cover integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN


def adaptive_cover_device_info(config_entry: ConfigEntry) -> DeviceInfo:
    """Return the shared device info for all entities of a config entry.

    One service device per config entry, named after the user's entry name,
    so entities render as "<entry name> <role>".
    """
    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=config_entry.data["name"],
        entry_type=DeviceEntryType.SERVICE,
    )
