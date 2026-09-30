"""One cover per window (ADR 0002): which window drives a cover.

A window drives exactly one cover, and a cover belongs to at most one
window. The window form, the ``add_entry`` service and Reconfigure ask
:func:`cover_problem` before they store a cover.

A window subentry takes its cover's entity-registry id as its unique_id
(:func:`cover_registry_id`), so Home Assistant also refuses a second
window for a registered cover. Covers outside the entity registry (no
unique_id) have no registry id; the scan in :func:`window_using_cover`
covers them too.
"""

from __future__ import annotations

from collections.abc import Sequence

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .windows import WindowEntry, all_windows

# Error keys (strings.json config.error / options.error).
ERROR_ONE_COVER = "one_cover_per_window"
ERROR_COVER_IN_USE = "cover_in_use"


def cover_registry_id(hass: HomeAssistant, cover: str | None) -> str | None:
    """Return the cover's entity-registry id (None when not registered)."""
    if not cover:
        return None
    entry = er.async_get(hass).async_get(cover)
    return entry.id if entry is not None else None


def window_using_cover(
    hass: HomeAssistant, cover: str, *, exclude_entry_id: str | None = None
) -> WindowEntry | None:
    """Return the window that drives ``cover``, if any.

    ``exclude_entry_id`` is a window key (the window being edited).
    """
    for window in all_windows(hass):
        if window.window_key == exclude_entry_id:
            continue
        if cover in window.covers:
            return window
    return None


def cover_problem(
    hass: HomeAssistant,
    covers: Sequence[str],
    *,
    exclude_entry_id: str | None = None,
) -> str | None:
    """Return why ``covers`` cannot be one window's covers (an error key).

    None when they can: no cover, or one cover no other window drives.
    ``exclude_entry_id`` is the window being edited.
    """
    problem = None
    if len(covers) > 1:
        problem = ERROR_ONE_COVER
    elif covers and window_using_cover(
        hass, covers[0], exclude_entry_id=exclude_entry_id
    ):
        problem = ERROR_COVER_IN_USE
    return problem
