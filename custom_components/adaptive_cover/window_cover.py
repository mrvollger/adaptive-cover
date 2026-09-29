"""One cover per window (ADR 0002): which window drives a cover.

A window drives exactly one cover, and a cover belongs to at most one
window. The setup wizard, the options form, the ``add_entry`` service and
the split repair ask :func:`cover_problem` before they store a cover.

A window's config entry takes its cover's entity-registry id as its
unique_id (:func:`cover_registry_id`), so Home Assistant also refuses a
second entry for a registered cover. Covers outside the entity registry
(no unique_id) have no registry id; the scan in :func:`window_using_cover`
covers them too.

An entry from before P3 may drive several covers. It keeps working and
gets a fixable "split" repair issue (:func:`async_check_split_issue`);
the fix (``repairs.py``) runs :func:`async_split_window`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import CONF_SENSOR_TYPE, DOMAIN
from .settings.normalize import window_covers, with_cover

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
) -> ConfigEntry | None:
    """Return the window that drives ``cover``, if any.

    Only enabled windows count (a disabled entry drives nothing); the hub
    is not a window (its leftover options list every cover).
    """
    from .hub import is_hub_entry

    for entry in hass.config_entries.async_entries(
        DOMAIN, include_ignore=False, include_disabled=False
    ):
        if entry.entry_id == exclude_entry_id or is_hub_entry(entry):
            continue
        if cover in window_covers(entry.options):
            return entry
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


# ------------------------------------------------------------ split repair

SPLIT_ISSUE = "split_window"


def split_issue_id(entry_id: str) -> str:
    """Return the repair issue id of one multi-cover entry."""
    return f"{SPLIT_ISSUE}_{entry_id}"


@callback
def async_check_split_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise (or clear) the fixable "split" issue of a multi-cover entry."""
    covers = window_covers(entry.options)
    issue_id = split_issue_id(entry.entry_id)
    if len(covers) <= 1:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=SPLIT_ISSUE,
        translation_placeholders={
            "window": entry.title,
            "covers": ", ".join(covers),
        },
        data={"entry_id": entry.entry_id},
    )


@dataclass(frozen=True)
class SplitPlan:
    """How :func:`async_split_window` splits one multi-cover entry."""

    kept: str
    """The cover the entry keeps."""
    new_windows: tuple[str, ...]
    """Covers that get a window of their own (a copy of the settings)."""
    dropped: tuple[str, ...]
    """Covers another window already drives: removed from this entry."""


def split_plan(hass: HomeAssistant, entry: ConfigEntry) -> SplitPlan:
    """Plan the split: keep the first free cover, one new window per other."""
    covers = window_covers(entry.options)
    free = [
        cover
        for cover in covers
        if window_using_cover(hass, cover, exclude_entry_id=entry.entry_id) is None
    ]
    kept = free[0] if free else covers[0]
    return SplitPlan(
        kept=kept,
        new_windows=tuple(cover for cover in free if cover != kept),
        dropped=tuple(c for c in covers if c not in free and c != kept),
    )


async def async_split_window(hass: HomeAssistant, entry: ConfigEntry) -> SplitPlan:
    """Split a multi-cover entry into one window per cover.

    The entry keeps one cover (its entities, history and overrides stay).
    Each other cover gets a new window with a copy of the entry's settings,
    named after the cover. Covers another window drives are removed.
    """
    plan = split_plan(hass, entry)
    settings = dict(entry.options)
    hass.config_entries.async_update_entry(
        entry, options=with_cover(settings, plan.kept)
    )
    for cover in plan.new_windows:
        state = hass.states.get(cover)
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                "name": state.name if state is not None else cover,
                CONF_SENSOR_TYPE: entry.data.get(CONF_SENSOR_TYPE),
                "options": with_cover(settings, cover),
            },
        )
    ir.async_delete_issue(hass, DOMAIN, split_issue_id(entry.entry_id))
    return plan
