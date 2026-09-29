"""The one cover a window drives, as stored in its options (ADR 0002).

A window drives exactly one cover. Since P3 the options store it twice:

- ``cover_entity_id`` (``CONF_COVER_ENTITY``): the cover, the key the forms
  and services use;
- ``group`` (``CONF_ENTITIES``): ``[cover]``, the list older versions read.
  Kept until P8 so a downgrade keeps working.

``group`` stays the key the runtime reads: an older version (after a
downgrade) writes only ``group``, so it is the one that is never stale.
Every writer goes through :func:`with_cover`, which writes both.

An entry from before P3 may hold several covers in ``group``; it keeps
working and gets a "split" repair issue.

Pure: no Home Assistant imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..const import CONF_COVER_ENTITY, CONF_ENTITIES


def window_covers(options: Mapping[str, Any]) -> list[str]:
    """Return every cover ``options`` drives (``group``, else the cover key)."""
    if CONF_ENTITIES in options:
        return list(options.get(CONF_ENTITIES) or [])
    cover = options.get(CONF_COVER_ENTITY)
    return [cover] if cover else []


def window_cover(options: Mapping[str, Any]) -> str | None:
    """Return the window's one cover; None with no cover or several."""
    covers = window_covers(options)
    return covers[0] if len(covers) == 1 else None


def with_cover(options: Mapping[str, Any], cover: str | None) -> dict[str, Any]:
    """Return ``options`` driving ``cover`` (None: no cover), both keys written."""
    return {
        **options,
        CONF_COVER_ENTITY: cover or None,
        CONF_ENTITIES: [cover] if cover else [],
    }


def normalize_cover(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``options`` with both cover keys agreeing.

    A single cover (or none) is written to both keys. Several covers (an
    entry from before P3) are left as they are: ``group`` keeps driving
    them until the entry is split.
    """
    covers = window_covers(options)
    if len(covers) > 1:
        return dict(options)
    return with_cover(options, covers[0] if covers else None)
