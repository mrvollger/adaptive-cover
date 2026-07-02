"""Serve and auto-register the bundled Lovelace card.

The card bundle (card/ source, built to www/adaptive-cover-card.js) ships
inside the integration so the frontend and the sensor data contract always
version together. On setup we expose the file over HTTP and add it to the
storage-mode Lovelace resources with a version query for cache busting -
install/update via HACS + restart is all a user ever does.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import _LOGGER

CARD_FILENAME = "adaptive-cover-card.js"
CARD_URL_BASE = "/adaptive_cover_files"
CARD_URL = f"{CARD_URL_BASE}/{CARD_FILENAME}"


def _card_path() -> Path:
    return Path(__file__).parent / "www" / CARD_FILENAME


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Serve the bundled card and ensure a Lovelace resource points at it."""
    path = _card_path()
    if not path.is_file():
        _LOGGER.debug("Card bundle missing at %s; skipping registration", path)
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), cache_headers=False)]
    )

    versioned_url = f"{CARD_URL}?v={version}"
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        _LOGGER.debug("Lovelace resources unavailable; card served at %s", CARD_URL)
        return
    if not resources.loaded:
        await resources.async_load()

    existing = [
        item
        for item in resources.async_items()
        if str(item.get("url", "")).startswith(CARD_URL)
    ]
    if not existing:
        if hasattr(resources, "async_create_item"):
            await resources.async_create_item(
                {"res_type": "module", "url": versioned_url}
            )
            _LOGGER.info("Registered Lovelace resource %s", versioned_url)
        else:  # YAML-mode lovelace: user manages resources manually
            _LOGGER.warning(
                "Lovelace is in YAML mode; add resource %s manually", versioned_url
            )
        return

    for item in existing:
        if item.get("url") != versioned_url and hasattr(resources, "async_update_item"):
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": versioned_url}
            )
            _LOGGER.info("Updated Lovelace resource to %s", versioned_url)
