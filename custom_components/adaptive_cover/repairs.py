"""Repair flows: split a multi-cover window (ADR 0002); consolidate the house (P7).

An entry from before P3 may drive several covers; setup raises a fixable
"split" issue for it (``window_cover.async_check_split_issue``). Fixing it
keeps one cover on the entry and gives each other cover a window of its
own with a copy of the settings (``window_cover.async_split_window``).

A house with window entries gets the fixable "consolidate" issue
(``consolidate.async_check_consolidate_issue``). Fixing it moves every
window entry into a subentry of the house (``ConsolidateFlow``).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import BooleanSelector

from .window_cover import async_split_window, split_plan

BACKUP_CONFIRMED = "backup_confirmed"


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


class ConsolidateFlow(RepairsFlow):
    """Move every window entry into the house (P7): a dry run, then the move.

    1. ``preview``: what moves (windows and their entities; every entity_id
       stays), what stays (disabled window entries), and a check that
       every window acts on the same settings afterwards. A problem ends
       the flow here, with nothing moved.
    2. ``confirm``: the owner confirms a backup from the last 24 hours (the
       rollback after the move is restoring it); then every window moves
       (``consolidate.async_consolidate``). A run that stops part way can
       be started again: it resumes.
    """

    def _house(self) -> ConfigEntry | None:
        from .windows import house_entry

        house = house_entry(self.hass)
        if house is None or house.state is not ConfigEntryState.LOADED:
            return None
        return house

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start with the dry run."""
        return await self.async_step_preview()

    async def async_step_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show what moves; nothing is written."""
        from .consolidate import consolidation_plan

        if (house := self._house()) is None:
            return self.async_abort(reason="house_not_loaded")
        if user_input is not None:
            return await self.async_step_confirm()
        plan = consolidation_plan(self.hass, house)
        if not plan.moves:
            return self.async_abort(reason="nothing_to_move")
        if not plan.ok:
            problems = [*plan.problems, *plan.mismatches]
            return self.async_abort(
                reason="blocked",
                description_placeholders={
                    "problems": "\n".join(f"- {line}" for line in problems)
                },
            )
        windows = "\n".join(
            f"- {move.title}: {len(move.entity_ids)} entities"
            + (" (resumed)" if move.resumed else "")
            for move in plan.moves
        )
        return self.async_show_form(
            step_id="preview",
            data_schema=vol.Schema({}),
            description_placeholders={
                "count": str(len(plan.moves)),
                "windows": windows,
                "entities": f"{plan.entity_count}/{plan.entity_count}",
                "left_alone": ", ".join(plan.left_alone) or "none",
            },
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm the backup, then move every window."""
        from .consolidate import ConsolidationError, async_consolidate

        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(BACKUP_CONFIRMED):
                errors["base"] = "backup_required"
            else:
                if (house := self._house()) is None:
                    return self.async_abort(reason="house_not_loaded")
                try:
                    report = await async_consolidate(self.hass, house)
                except ConsolidationError as err:
                    return self.async_abort(
                        reason="failed", description_placeholders={"error": str(err)}
                    )
                return self.async_create_entry(data={"moved": list(report.moved)})
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {vol.Required(BACKUP_CONFIRMED, default=False): BooleanSelector()}
            ),
            errors=errors or None,
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow of a "split" or of the "consolidate" issue."""
    from .consolidate import ISSUE_ID as CONSOLIDATE_ISSUE_ID

    if issue_id == CONSOLIDATE_ISSUE_ID:
        return ConsolidateFlow()
    if not data or "entry_id" not in data:
        raise ValueError(f"Repair issue {issue_id} has no entry_id")
    return SplitWindowFlow(str(data["entry_id"]))
