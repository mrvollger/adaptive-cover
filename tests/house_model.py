"""Build a house entry (3.1) with window subentries for a test (v2.1, P8).

Since v2.1 the house entry is the integration's only running config entry
and every window is a ``window`` subentry storing only what it uses
(``settings/window_record.py``). A test describes its windows the way a
window entry held them (flat options: geometry, the cover, and recurring
values), and ``mock_house`` stores them the way a house holds them:

- the house options are the windows' recurring values lifted into house,
  floor and area profiles (``settings/lift.py``: what a house lifted from
  these windows stores), so each window acts on exactly its options;
- each window's subentry holds its geometry, its cover and the overrides
  the lift gave it.

``mock_window_entry`` is the one-window case. Its window key is the house
entry's own entry_id, so ``entry.entry_id`` addresses both the entry to
set up and the window (its unique_id prefix, ``WindowHandle.by_key``), as
a window entry's entry_id did.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.util.ulid import ulid_now
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_SENSOR_TYPE,
    DOMAIN,
    HOUSE_ENTRY_MINOR_VERSION,
    HOUSE_ENTRY_VERSION,
    SensorType,
)
from custom_components.adaptive_cover.hub import (
    CONF_IS_HUB,
    HUB_ENTRY_NAME,
    HUB_UNIQUE_ID,
)
from custom_components.adaptive_cover.runtime.shade_config import absent_options
from custom_components.adaptive_cover.settings.lift import LegacyWindow
from custom_components.adaptive_cover.settings.shadow import (
    hub_options,
    legacy_values,
    lift_house,
)
from custom_components.adaptive_cover.settings.window_record import (
    record_from_options,
)


@dataclass
class Window:
    """One window of a test house, described as a window entry held it."""

    name: str
    options: Mapping[str, Any]
    sensor_type: str = SensorType.BLIND
    window_key: str | None = None
    """A migrated window's key (None: its key is its subentry_id)."""
    subentry_id: str = field(default_factory=ulid_now)
    area_id: str | None = None
    """Where the lift places it (None: the house)."""
    toggles: Mapping[str, bool] = field(default_factory=dict)
    """Toggle values (``climate_on``, ``manual_detection``, ...)."""
    unique_id: str | None = None
    title: str | None = None
    """The subentry's title, when it is not the name (a renamed title)."""

    @property
    def key(self) -> str:
        """The window key."""
        return self.window_key or self.subentry_id


def house_layers(
    hass: HomeAssistant, windows: Sequence[Window]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the house options and each window's subentry data (by key)."""
    unit = hass.config.units.temperature_unit
    flats = {
        window.key: legacy_values(
            {**window.options, **absent_options(window.options)},
            window.toggles,
            temperature_unit=unit,
        )
        for window in windows
    }
    lifted = lift_house(
        [
            LegacyWindow(
                window_key=window.key, options=flats[window.key], area_id=window.area_id
            )
            for window in windows
        ],
        {area.id: area.floor_id for area in ar.async_get(hass).async_list_areas()},
        [floor.floor_id for floor in fr.async_get(hass).async_list_floors()],
        temperature_unit=unit,
    )
    data = {
        window.key: record_from_options(
            window.name,
            window.sensor_type,
            window.options,
            overrides=lifted.overrides[window.key],
            window_key=window.window_key,
        ).as_data()
        for window in windows
    }
    return hub_options(lifted), data


def mock_house(
    hass: HomeAssistant,
    windows: Sequence[Window],
    *,
    entry_id: str | None = None,
    options: Mapping[str, Any] | None = None,
    add: bool = True,
) -> MockConfigEntry:
    """Return a 3.1 house entry holding ``windows`` (added to hass, not set up).

    ``options`` replace parts of the lifted house options.
    """
    house_options, data = house_layers(hass, windows)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=HUB_ENTRY_NAME,
        unique_id=HUB_UNIQUE_ID,
        data={"name": HUB_ENTRY_NAME, CONF_IS_HUB: True},
        options={**house_options, **(options or {})},
        version=HOUSE_ENTRY_VERSION,
        minor_version=HOUSE_ENTRY_MINOR_VERSION,
        entry_id=entry_id,
        subentries_data=[
            {
                "data": data[window.key],
                "subentry_id": window.subentry_id,
                "subentry_type": "window",
                "title": window.title or window.name,
                "unique_id": window.unique_id,
            }
            for window in windows
        ],
    )
    if add:
        entry.add_to_hass(hass)
    return entry


def mock_window_entry(
    hass: HomeAssistant,
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    **window: Any,
) -> MockConfigEntry:
    """Return a house with one window whose key is the house's entry_id.

    ``data`` and ``options`` are what the window entry held (``name``,
    ``sensor_type``; flat options). ``entry.entry_id`` is then both the
    entry to set up and the window's key.
    """
    entry_id = ulid_now()
    return mock_house(
        hass,
        [
            Window(
                name=data["name"],
                options=options,
                sensor_type=data.get(CONF_SENSOR_TYPE, SensorType.BLIND),
                window_key=entry_id,
                **window,
            )
        ],
        entry_id=entry_id,
    )


def window_subentry(entry: MockConfigEntry, key: str | None = None):
    """Return the house's window subentry with this key (default: the only one)."""
    subentries = [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == "window"
        and (
            key is None
            or (subentry.data.get("window_key") or subentry.subentry_id) == key
        )
    ]
    assert len(subentries) == 1, subentries
    return subentries[0]
