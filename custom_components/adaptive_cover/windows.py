"""Where a window's config lives: a legacy entry or a house subentry (P7).

Until the owner consolidates the house (``consolidate.py``), each window is
its own config entry, as it always was (the *legacy* model). After it, each
window is a config subentry of type ``window`` of the house entry: the hub
entry, promoted (ADR 0001). A fresh install uses subentries from the start.

``WindowEntry`` gives both kinds the same read-only face, so the runtime,
the platforms and the layered settings do not care where a window lives:

- ``entry_id`` is the window key (``window_key``): a migrated window's old
  entry_id, a new window's subentry_id. It is the unique_id prefix of every
  entity of the window, the override-store key and the card binding key,
  so it never changes;
- ``title``, ``data`` and ``options`` are what a window entry holds;
- ``config_entry`` is the entry that owns the window (the window's own
  entry, or the house).

``async_update_window`` stores a change where the window lives.

**Subentry data (v2.0).** A window subentry stores the window entry's data
and options verbatim (ADR 0006)::

    {"window_key": "<key>", "data": {"name": ..., "sensor_type": ...},
     "options": {...every option, the sparse ``overrides`` included...}}

so a consolidated window reads exactly what it read as an entry. Its
unique_id is the cover's entity-registry id (ADR 0002): a second window
for the same cover aborts.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import UNDEFINED, UndefinedType

from .const import DOMAIN, HOUSE_ENTRY_VERSION

WINDOW_SUBENTRY: Final = "window"
"""The subentry type of a window."""

WINDOW_KEY: Final = "window_key"
DATA: Final = "data"
OPTIONS: Final = "options"

_EMPTY: Final[Mapping[str, Any]] = MappingProxyType({})


def _is_hub(entry: ConfigEntry) -> bool:
    return bool(entry.data.get("is_hub"))


def subentry_window_key(subentry: ConfigSubentry) -> str:
    """Return a window subentry's key (its subentry_id when it has none)."""
    return str(subentry.data.get(WINDOW_KEY) or subentry.subentry_id)


def window_subentry_data(
    window_key: str | None, data: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a window subentry's data: the entry data and options, verbatim.

    ``window_key`` is a migrated window's old entry_id; None for a new
    window, whose key is its subentry_id.
    """
    stored: dict[str, Any] = {DATA: dict(data), OPTIONS: dict(options)}
    if window_key is not None:
        stored[WINDOW_KEY] = window_key
    return stored


class WindowEntry:
    """One window, read the same way wherever it is stored.

    A view, not a copy: every read goes to the live entry or subentry, so a
    stored change is seen at once. ``virtual`` builds a window that is not
    stored (yet): the consolidation preview resolves one.
    """

    __slots__ = ("_entry", "_subentry_id", "_virtual", "via_device_id")

    def __init__(
        self,
        entry: ConfigEntry,
        subentry_id: str | None = None,
        *,
        via_device_id: str | None = None,
    ) -> None:
        """Wrap a legacy window entry, or one window subentry of ``entry``."""
        self._entry = entry
        self._subentry_id = subentry_id
        self._virtual: tuple[str, Mapping[str, Any]] | None = None
        self.via_device_id = via_device_id
        """The house device, for a subentry window's device (via_device_id)."""

    @classmethod
    def virtual(
        cls,
        house: ConfigEntry,
        window_key: str,
        title: str,
        data: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> WindowEntry:
        """Return a subentry window of ``house`` that is not stored."""
        window = cls(house, f"virtual-{window_key}")
        window._virtual = (
            title,
            MappingProxyType(window_subentry_data(window_key, data, options)),
        )
        return window

    # ------------------------------------------------------------ identity

    @property
    def is_subentry(self) -> bool:
        """Whether the window is a subentry of the house entry."""
        return self._subentry_id is not None

    @property
    def config_entry(self) -> ConfigEntry:
        """The config entry that owns the window (itself, or the house)."""
        return self._entry

    @property
    def subentry_id(self) -> str | None:
        """The window's subentry_id (None for a legacy entry)."""
        return self._subentry_id

    @property
    def subentry(self) -> ConfigSubentry | None:
        """The window's subentry (None for a legacy or a virtual window)."""
        if self._subentry_id is None or self._virtual is not None:
            return None
        return self._entry.subentries.get(self._subentry_id)

    def _stored(self) -> Mapping[str, Any]:
        if self._virtual is not None:
            return self._virtual[1]
        subentry = self.subentry
        return subentry.data if subentry is not None else _EMPTY

    @property
    def window_key(self) -> str:
        """The window key (see the module docstring)."""
        if self._subentry_id is None:
            return self._entry.entry_id
        return str(self._stored().get(WINDOW_KEY) or self._subentry_id)

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
        """The window's name as the integration page shows it."""
        if self._subentry_id is None:
            return self._entry.title
        if self._virtual is not None:
            return self._virtual[0]
        subentry = self.subentry
        return subentry.title if subentry is not None else ""

    @property
    def data(self) -> Mapping[str, Any]:
        """What a window entry's data holds (name, sensor_type)."""
        if self._subentry_id is None:
            return self._entry.data
        return MappingProxyType(dict(self._stored().get(DATA) or {}))

    @property
    def options(self) -> Mapping[str, Any]:
        """What a window entry's options hold (every option, overrides too)."""
        if self._subentry_id is None:
            return self._entry.options
        return MappingProxyType(dict(self._stored().get(OPTIONS) or {}))

    @property
    def unique_id(self) -> str | None:
        """The cover's entity-registry id (ADR 0002)."""
        if self._subentry_id is None:
            return self._entry.unique_id
        subentry = self.subentry
        return subentry.unique_id if subentry is not None else None

    @property
    def state(self) -> ConfigEntryState:
        """The owning entry's state."""
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
        """Hash by the owning entry and the subentry."""
        return hash((self._entry.entry_id, self._subentry_id))

    def __repr__(self) -> str:
        """Debug form."""
        where = f"subentry {self._subentry_id}" if self.is_subentry else "entry"
        return f"<WindowEntry {self.title!r} key={self.window_key} {where}>"


WindowLike = ConfigEntry | WindowEntry
"""A legacy window entry, or any window (the layered-settings functions take both)."""


def as_window(window: WindowLike) -> WindowEntry:
    """Return ``window`` as a WindowEntry (a legacy entry is wrapped)."""
    return window if isinstance(window, WindowEntry) else WindowEntry(window)


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
    """Return the window config entries (the legacy model), hub excluded."""
    return [
        entry
        for entry in hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=include_disabled
        )
        if not _is_hub(entry)
    ]


def is_pending(hass: HomeAssistant, subentry: ConfigSubentry) -> bool:
    """Whether a window subentry still has its legacy entry (mid-consolidation).

    Its legacy entry runs the window until consolidation removes it; the
    house must not run the subentry as well.
    """
    return (
        hass.config_entries.async_get_entry(subentry_window_key(subentry)) is not None
    )


def window_subentries(house: ConfigEntry) -> list[ConfigSubentry]:
    """Return the house's window subentries."""
    return house.get_subentries_of_type(WINDOW_SUBENTRY)


def subentry_windows(
    hass: HomeAssistant, house: ConfigEntry | None = None, *, pending: bool = False
) -> list[WindowEntry]:
    """Return the house's subentry windows (``pending``: mid-consolidation ones too)."""
    house = house or house_entry(hass)
    if house is None:
        return []
    return [
        WindowEntry(house, subentry.subentry_id)
        for subentry in window_subentries(house)
        if pending or not is_pending(hass, subentry)
    ]


def all_windows(
    hass: HomeAssistant, *, include_disabled: bool = False
) -> list[WindowEntry]:
    """Return every window: the enabled legacy entries, then the subentries.

    A window being consolidated is listed once (as its legacy entry).
    """
    return [
        *(
            WindowEntry(entry)
            for entry in legacy_window_entries(hass, include_disabled=include_disabled)
        ),
        *subentry_windows(hass),
    ]


def find_window(hass: HomeAssistant, window_key: str) -> WindowEntry | None:
    """Return the window with this key (a legacy entry wins mid-consolidation)."""
    entry = hass.config_entries.async_get_entry(window_key)
    if entry is not None and entry.domain == DOMAIN:
        return None if _is_hub(entry) else WindowEntry(entry)
    return next(
        (
            window
            for window in subentry_windows(hass)
            if window.window_key == window_key
        ),
        None,
    )


def uses_subentries(hass: HomeAssistant) -> bool:
    """Whether new windows are subentries of the house: a 2.x house.

    A house is 2.x once consolidated, or from the start on a fresh
    install. A 1.x house (the hub of window entries) keeps adding window
    entries until the owner consolidates it, so a downgrade before the
    click keeps working.
    """
    house = house_entry(hass)
    return house is not None and house.version >= HOUSE_ENTRY_VERSION


# ------------------------------------------------------------ registry


def window_device(hass: HomeAssistant, window: WindowLike) -> dr.DeviceEntry | None:
    """Return the window's device (identifier ``(DOMAIN, window_key)``).

    A subentry window whose device is still on its legacy entry (a window
    the consolidation preview resolves) finds it there.
    """
    window = as_window(window)
    dev_reg = dr.async_get(hass)
    identifier = (DOMAIN, window.window_key)
    device = dev_reg.async_get_device_by_identifier(
        identifier, config_entry_id=window.config_entry.entry_id
    )
    if device is None and window.is_subentry:
        device = dev_reg.async_get_device_by_identifier(
            identifier, config_entry_id=window.window_key
        )
    return device


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
    window: WindowLike,
    *,
    data: Mapping[str, Any] | UndefinedType = UNDEFINED,
    options: Mapping[str, Any] | UndefinedType = UNDEFINED,
    title: str | UndefinedType = UNDEFINED,
    unique_id: str | None | UndefinedType = UNDEFINED,
) -> bool:
    """Store a window's data, options, title or unique_id where it lives.

    Returns whether anything changed. A legacy entry's update listener, or
    the house's (``house.HouseRuntime.async_sync``), acts on the change.
    """
    if isinstance(window, ConfigEntry):
        window = WindowEntry(window)
    if not window.is_subentry:
        return hass.config_entries.async_update_entry(
            window.config_entry,
            data=data,
            options=options,
            title=title,
            unique_id=unique_id,
        )
    subentry = window.subentry
    if subentry is None:
        raise ValueError(f"{window!r} is not stored")
    stored = dict(subentry.data)
    if data is not UNDEFINED:
        stored[DATA] = dict(data)
    if options is not UNDEFINED:
        stored[OPTIONS] = dict(options)
    return hass.config_entries.async_update_subentry(
        window.config_entry,
        subentry,
        data=stored,
        title=title,
        unique_id=unique_id,
    )
