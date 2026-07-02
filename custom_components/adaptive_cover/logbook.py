"""Describe adaptive_cover_moved events in the Home Assistant logbook.

Gives every cover movement a human-readable provenance line:
"moved to 37% (all_covers: whole-house gesture)".
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN

EVENT_ADAPTIVE_COVER_MOVED = "adaptive_cover_moved"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict]], None],
) -> None:
    """Register the describe callback for our move events."""

    @callback
    def async_describe_moved(event: Event) -> dict:
        data = event.data
        message = f"moved to {data.get('position')}% ({data.get('source')}"
        if data.get("reason"):
            message += f": {data.get('reason')}"
        message += ")"
        return {
            "name": "Adaptive Cover",
            "message": message,
            "entity_id": data.get("entity_id"),
        }

    async_describe_event(DOMAIN, EVENT_ADAPTIVE_COVER_MOVED, async_describe_moved)
