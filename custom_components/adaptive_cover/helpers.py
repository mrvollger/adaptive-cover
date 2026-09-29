"""Helper functions."""

import datetime as dt
from typing import overload

from dateutil import parser
from homeassistant.core import HomeAssistant, split_entity_id


def get_safe_state(hass: HomeAssistant, entity_id: str):
    """Get a safe state value if not available."""
    state = hass.states.get(entity_id)
    if not state or state.state in ["unknown", "unavailable"]:
        return None
    return state.state


def get_safe_attr(hass: HomeAssistant, entity_id: str, attr: str):
    """Return an entity attribute, or None if entity/attr missing."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    return state.attributes.get(attr)


def get_domain(entity: str):
    """Get domain of entity."""
    if entity is not None:
        domain, object_id = split_entity_id(entity)
        return domain


@overload
def get_datetime_from_str(
    string: str, default_date: dt.date | None = None
) -> dt.datetime: ...


@overload
def get_datetime_from_str(
    string: str | None, default_date: dt.date | None = None
) -> dt.datetime | None: ...


def get_datetime_from_str(
    string: str | None, default_date: dt.date | None = None
) -> dt.datetime | None:
    """Convert datetime string to datetime (None stays None).

    A bare time string gets its date from default_date when given.
    Without it, dateutil falls back to the PROCESS-local today, which is
    wrong whenever the process timezone differs from HA's configured one
    (e.g. docker containers running UTC) — callers that care about "today"
    must pass the HA-local date explicitly.
    """
    if string is not None:
        if default_date is not None:
            default = dt.datetime.combine(default_date, dt.time())
            return parser.parse(string, ignoretz=True, default=default)
        return parser.parse(string, ignoretz=True)


def get_last_updated(entity_id: str, hass: HomeAssistant):
    """Get last updated attribute from entity."""
    if entity_id is not None:
        if hass.states.get(entity_id):
            return hass.states.get(entity_id).last_updated
