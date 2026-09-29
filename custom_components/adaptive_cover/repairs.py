"""Repair flows: split a window entry that drives several covers (ADR 0002).

An entry from before P3 may drive several covers; setup raises a fixable
"split" issue for it (``window_cover.async_check_split_issue``). Fixing it
keeps one cover on the entry and gives each other cover a window of its
own with a copy of the settings (``window_cover.async_split_window``).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .window_cover import async_split_window, split_plan


class SplitWindowFlow(RepairsFlow):
    """Confirm, then split one multi-cover entry into one window per cover."""

    def __init__(self, entry_id: str) -> None:
        """Split the entry ``entry_id``."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start with the confirmation."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show what the split does; split on confirm."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_removed")
        if user_input is not None:
            await async_split_window(self.hass, entry)
            return self.async_create_entry(data={})
        plan = split_plan(self.hass, entry)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "window": entry.title,
                "kept": plan.kept,
                "new_windows": ", ".join(plan.new_windows) or "none",
                "dropped": ", ".join(plan.dropped) or "none",
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow of a "split" issue."""
    if not data or "entry_id" not in data:
        raise ValueError(f"Repair issue {issue_id} has no entry_id")
    return SplitWindowFlow(str(data["entry_id"]))
