"""The live house snapshot as the settings lift reads it (plain JSON, no hass).

A window's area is its physical cover's effective area (the window device
copies it); its floor is that area's floor. The house runs in °F.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from custom_components.adaptive_cover.settings.lift import LegacyWindow

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "house_snapshot"
TEMPERATURE_UNIT = "°F"


def _load(name: str) -> dict:
    return json.loads((SNAPSHOT_DIR / name).read_text())


@dataclass(frozen=True)
class House:
    """The 15 live windows plus the HA areas and floors."""

    windows: tuple[LegacyWindow, ...]
    titles: dict[str, str]  # window_key -> entry title
    areas: dict[str, str | None]  # area_id -> floor_id
    floors: tuple[str, ...]

    def key(self, title: str) -> str:
        """Return the window_key of the window with this title."""
        (key,) = [k for k, t in self.titles.items() if t == title]
        return key


@cache
def load_house() -> House:
    """Load the live windows (hub and disabled legacy entries excluded)."""
    covers = {c["entity_id"]: c for c in _load("physical_covers.json")["covers"]}
    registry = _load("floors_areas.json")
    windows = []
    titles = {}
    for entry in _load("config_entries.json")["entries"]:
        if entry["role"] != "window":
            continue
        options = {**(entry["data"] or {}), **entry["options"]}
        (cover,) = options["group"]  # every live window has one cover
        windows.append(
            LegacyWindow(
                window_key=entry["entry_id"],
                options=options,
                area_id=covers[cover]["effective_area_id"],
            )
        )
        titles[entry["entry_id"]] = entry["title"]
    return House(
        windows=tuple(windows),
        titles=titles,
        areas={a["area_id"]: a["floor_id"] for a in registry["areas"]},
        floors=tuple(f["floor_id"] for f in registry["floors"]),
    )
