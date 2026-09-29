"""P5 shadow release (v1.18.0): the layered settings run beside the legacy ones.

The hub starts at config 1.3, so migration 1.4 lifts the window into the
hub's house profile and writes its ``overrides``. From then on:

- the lift itself changes nothing the window does (no reload, no move);
- a legacy option changed through the options form still drives the
  window, and the difference from the layered settings raises one
  ``settings_differ`` repair issue for the window, listing the key; the
  issue goes away when the values agree again;
- a dropped switch (manual-override detection) flipped after the lift
  differs from what the lift recorded, and raises the same issue.

Observed only through the timeline, entity states and the issue registry.
"""

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover.const import (
    CONF_MANUAL_DETECTION,
    CONF_SUNSET_POS,
    DOMAIN,
)

from .harness import SimHouse

SHADE = "cover.shade"
# 2026-06-21 in SLC: sunrise ~05:58 local, so 04:00-05:00 is night and the
# window wants its sunset position.
DATE = "2026-06-21"


def _pre_p5_hub(hass) -> MockConfigEntry:
    """The hub as v1.17.0 left it (config 1.3): migration 1.4 lifts the house."""
    hub = MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive Cover All",
        data={"is_hub": True, "name": "Adaptive Cover All"},
        version=1,
        minor_version=3,
    )
    hub.add_to_hass(hass)
    return hub


def _differ_issues(hass) -> dict[str, dict[str, str]]:
    """The settings_differ issues: issue_id -> translation placeholders."""
    return {
        issue_id: dict(issue.translation_placeholders or {})
        for (domain, issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "settings_differ"
    }


async def _house(hass, freezer) -> SimHouse:
    hub = _pre_p5_hub(hass)
    house = await SimHouse.create(
        hass, freezer, date=DATE, options={CONF_SUNSET_POS: 0}
    )
    assert hub.minor_version == 4
    assert "house" in hub.options
    return house


async def test_lift_changes_nothing_the_window_does(hass, freezer):
    house = await _house(hass, freezer)
    window = house.window()

    # The lift wrote the window's overrides after its setup had started:
    # that update is not a reload, and nothing differs.
    assert window.teardowns == 0
    assert _differ_issues(hass) == {}
    assert window.attributes["provenance"] == {}
    await house.advance_to("05:00")
    assert window.target == 0
    await house.teardown()


async def test_legacy_option_change_raises_a_repair_issue(hass, freezer):
    house = await _house(hass, freezer)
    window = house.window()
    await house.advance_to("04:30")
    assert window.target == 0

    await house.set_options(**{CONF_SUNSET_POS: 25})

    # The runtime still acts on the legacy option ...
    assert window.target == 25
    await house.advance_to("05:00")
    assert house.position(SHADE) == 25
    # ... and the layered settings (lifted with 0) now differ: one issue.
    issue_id = f"settings_differ_{house.entry.entry_id}"
    assert _differ_issues(hass) == {
        issue_id: {"window": house.entry.title, "keys": CONF_SUNSET_POS}
    }

    await house.set_options(**{CONF_SUNSET_POS: 0})
    assert _differ_issues(hass) == {}
    await house.teardown()


async def test_dropped_switch_flip_raises_a_repair_issue(hass, freezer):
    house = await _house(hass, freezer)
    issue_id = f"settings_differ_{house.entry.entry_id}"

    await house.toggle("manual_override", False)
    assert _differ_issues(hass) == {
        issue_id: {"window": house.entry.title, "keys": CONF_MANUAL_DETECTION}
    }

    await house.toggle("manual_override", True)
    assert _differ_issues(hass) == {}
    await house.teardown()
