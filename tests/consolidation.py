"""Drive the "Consolidate" repair (P7) the way the owner does.

The repair issue ``consolidate_house`` is fixable: its fix flow shows a dry
run (``preview``), then asks for a backup (``confirm``) and moves every
window entry into a subentry of the house. These helpers run that flow
through the integration's repairs platform, as Home Assistant's Repairs
page does (see also tests/test_migration_1_3.py for the split repair).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.adaptive_cover.const import DOMAIN
from custom_components.adaptive_cover.repairs import (
    BACKUP_CONFIRMED,
    async_create_fix_flow,
)

ISSUE_ID = "consolidate_house"


def consolidate_issue(hass: HomeAssistant) -> ir.IssueEntry | None:
    """The "Consolidate" repair issue, when the house has window entries."""
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)


async def open_consolidation(hass: HomeAssistant) -> tuple[Any, dict[str, Any]]:
    """Open the fix flow; return it and its first result (the dry run)."""
    issue = consolidate_issue(hass)
    assert issue is not None, "no consolidate_house repair issue"
    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    flow.issue_id = issue.issue_id
    flow.flow_id = "consolidate-test"
    return flow, await flow.async_step_init()


async def consolidate_via_repair(
    hass: HomeAssistant, *, backup: bool = True
) -> dict[str, Any]:
    """Fix the "Consolidate" repair: dry run, backup, move. Return the last result."""
    flow, result = await open_consolidation(hass)
    assert result["type"] is FlowResultType.FORM, result
    assert result["step_id"] == "preview", result
    result = await flow.async_step_preview({})
    assert result["type"] is FlowResultType.FORM, result
    assert result["step_id"] == "confirm", result
    result = await flow.async_step_confirm({BACKUP_CONFIRMED: backup})
    await hass.async_block_till_done()
    return result
