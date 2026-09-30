"""Where a window's config lives: a ``window`` subentry of the house entry.

Since v2.1 (P8) the house entry (the hub, 2.x) is the integration's only
running config entry, and each window is one of its config subentries of
type ``window`` (ADR 0001). Window config entries (the 1.x model) no
longer run: a house that still has them must be consolidated on v2.0.x
first (``upgrade.py``).

``WindowEntry`` is one window's read-only face:

- ``window_key`` (and ``entry_id``, its old name) is the key of the
  window: a migrated window's old entry_id, a new window's subentry_id.
  It is the unique_id prefix of every entity of the window, the
  override-store key and the card binding key, so it never changes;
- ``name``, ``cover``, ``cover_type``, ``geometry`` and ``overrides`` are
  what the subentry stores (``settings/window_record.py``), and
  ``options`` the flat one-time options the runtime reads (computed);
- ``config_entry`` is the house entry.

``async_update_window`` stores a changed window record.

A window subentry's unique_id is its cover's entity-registry id (ADR
0002): a second window for the same cover aborts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import UNDEFINED, UndefinedType

from .const import DOMAIN
from .settings.resolve import WindowOverrides
from .settings.window_record import WINDOW_KEY, WindowRecord

WINDOW_SUBENTRY: Final = "window"
"""The subentry type of a window."""


def _is_hub(entry: ConfigEntry) -> bool:
    return bool(entry.data.get("is_hub"))


def subentry_window_key(subentry: ConfigSubentry) -> str:
    """Return a window subentry's key (its subentry_id when it has none)."""
    return str(subentry.data.get(WINDOW_KEY) or subentry.subentry_id)


class WindowEntry:
    """One window subentry of the house, read where it is stored.

    A view, not a copy: every read goes to the live subentry, so a stored
    change is seen at once.
    """

    __slots__ = ("_entry", "_subentry_id", "via_device_id")

    def __init__(
        self,
        house: ConfigEntry,
        subentry_id: str,
        *,
        via_device_id: str | None = None,
    ) -> None:
        """Wrap one window subentry of the house entry."""
        self._entry = house
        self._subentry_id = subentry_id
        self.via_device_id = via_device_id
        """The house device, for the window device's ``via_device_id``."""

    # ------------------------------------------------------------ identity

    @property
    def config_entry(self) -> ConfigEntry:
        """The house entry (it owns the window)."""
        return self._entry

    @property
    def subentry_id(self) -> str:
        """The window's subentry_id."""
        return self._subentry_id

    @property
    def subentry(self) -> ConfigSubentry | None:
        """The window's subentry (None once it is removed)."""
        return self._entry.subentries.get(self._subentry_id)

    @property
    def record(self) -> WindowRecord:
        """What the subentry stores (``settings/window_record.py``).

        Raises
        ------
        RecordError
            The subentry is not in the 3.1 shape.
        KeyError
            The subentry was removed.

        """
        subentry = self.subentry
        if subentry is None:
            raise KeyError(self._subentry_id)
        return WindowRecord.from_data(subentry.data)

    @property
    def window_key(self) -> str:
        """The window key (see the module docstring)."""
        subentry = self.subentry
        if subentry is None:
            return self._subentry_id
        return subentry_window_key(subentry)

    @property
    def entry_id(self) -> str:
        """The window key: what a window entry's entry_id always was."""
        return self.window_key

    @property
    def domain(self) -> str:
        """The integration domain."""
        return self._entry.domain

    @property
    def title(self) -> str:
        """The window's title on the integration page."""
        subentry = self.subentry
        return subentry.title if subentry is not None else ""

    @property
    def name(self) -> str:
        """The window's name (its device's), else its title."""
        return self.record.name or self.title

    @property
    def cover(self) -> str | None:
        """The one cover the window drives (ADR 0002)."""
        return self.record.cover

    @property
    def covers(self) -> list[str]:
        """The window's cover as a list (empty without one)."""
        cover = self.cover
        return [cover] if cover else []

    @property
    def cover_type(self) -> str:
        """``cover_blind``, ``cover_awning`` or ``cover_tilt``."""
        return self.record.cover_type

    @property
    def geometry(self) -> Mapping[str, Any]:
        """The window's one-time settings."""
        return self.record.geometry

    @property
    def overrides(self) -> WindowOverrides:
        """The window's own recurring values (sparse)."""
        return self.record.overrides

    @property
    def options(self) -> dict[str, Any]:
        """The flat one-time options the runtime reads (computed)."""
        return self.record.options

    @property
    def unique_id(self) -> str | None:
        """The cover's entity-registry id (ADR 0002)."""
        subentry = self.subentry
        return subentry.unique_id if subentry is not None else None

    @property
    def state(self) -> ConfigEntryState:
        """The house entry's state."""
        return self._entry.state

    def __eq__(self, other: object) -> bool:
        """Two views of the same window are equal."""
        if not isinstance(other, WindowEntry):
            return NotImplemented
        return (self._entry.entry_id, self._subentry_id) == (
            other._entry.entry_id,
            other._subentry_id,
        )

    def __hash__(self) -> int:
        """Hash by the house entry and the subentry."""
        return hash((self._entry.entry_id, self._subentry_id))

    def __repr__(self) -> str:
        """Debug form."""
        return f"<WindowEntry {self.title!r} key={self.window_key}>"


# ------------------------------------------------------------ lookups


def house_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the house entry (the hub), if there is one."""
    return next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _is_hub(entry)
        ),
        None,
    )


def legacy_window_entries(
    hass: HomeAssistant, *, include_disabled: bool = False
) -> list[ConfigEntry]:
    """Return the window config entries left from 1.x (they do not run)."""
    return [
        entry
        for entry in hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=include_disabled
        )
        if not _is_hub(entry)
    ]


def window_subentries(house: ConfigEntry) -> list[ConfigSubentry]:
    """Return the house's window subentries."""
    return house.get_subentries_of_type(WINDOW_SUBENTRY)


def subentry_windows(
    hass: HomeAssistant, house: ConfigEntry | None = None
) -> list[WindowEntry]:
    """Return the house's windows."""
    house = house or house_entry(hass)
    if house is None:
        return []
    return [
        WindowEntry(house, subentry.subentry_id)
        for subentry in window_subentries(house)
    ]


def all_windows(hass: HomeAssistant) -> list[WindowEntry]:
    """Return every window (the house's window subentries)."""
    return subentry_windows(hass)


def find_window(hass: HomeAssistant, window_key: str) -> WindowEntry | None:
    """Return the window with this key, if there is one."""
    return next(
        (window for window in all_windows(hass) if window.window_key == window_key),
        None,
    )


# ------------------------------------------------------------ registry


def window_device(hass: HomeAssistant, window: WindowEntry) -> dr.DeviceEntry | None:
    """Return the window's device (identifier ``(DOMAIN, window_key)``)."""
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, window.window_key), config_entry_id=window.config_entry.entry_id
    )


def window_rows(hass: HomeAssistant, window_key: str) -> list[er.RegistryEntry]:
    """Return the entity-registry rows of one window (by unique_id prefix)."""
    prefix = f"{window_key}_"
    return [
        row
        for row in er.async_get(hass).entities.values()
        if row.platform == DOMAIN and row.unique_id.startswith(prefix)
    ]


# ------------------------------------------------------------ writes


@callback
def async_update_window(
    hass: HomeAssistant,
    window: WindowEntry,
    record: WindowRecord,
    *,
    title: str | UndefinedType = UNDEFINED,
    unique_id: str | None | UndefinedType = UNDEFINED,
) -> bool:
    """Store a window's record (and its title or unique_id); return whether it changed.

    The house's update listener (``house.HouseRuntime.async_sync``) acts
    on the change.
    """
    subentry = window.subentry
    if subentry is None:
        raise ValueError(f"{window!r} is not stored")
    return hass.config_entries.async_update_subentry(
        window.config_entry,
        subentry,
        data=record.as_data(),
        title=title,
        unique_id=unique_id,
    )
