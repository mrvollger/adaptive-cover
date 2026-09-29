"""The layered settings drive the window (P5 flip; shadow release before).

The hub starts at config 1.3, so migration 1.4 lifts the window into the
hub's house profile and writes its ``overrides``. From then on:

- the lift itself changes nothing the window does (no reload, no move);
- a recurring setting changed through the settings service becomes the
  window's own value (a sparse override, no reload) and drives the
  window at once; changed back, the override goes away;
- a dropped switch (manual-override detection) flipped after the lift
  writes through to the window's own value: detection stops and starts;
- the retired ``settings_differ`` repair issue never appears.

Observed only through the timeline, entity states, the diagnostics
settings and the issue registry.
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
    """The retired settings_differ issues: issue_id -> translation placeholders."""
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
    assert hub.minor_version == 5
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


async def test_recurring_change_is_a_window_override(hass, freezer):
    house = await _house(hass, freezer)
    window = house.window()
    await house.advance_to("04:30")
    assert window.target == 0

    await house.set_options(**{CONF_SUNSET_POS: 25})

    # The window's own value, stored sparsely, acted on without a reload.
    assert house.entry.options["overrides"]["values"] == {CONF_SUNSET_POS: 25}
    assert window.attributes["provenance"] == {CONF_SUNSET_POS: "window"}
    assert window.teardowns == 0
    assert window.target == 25
    await house.advance_to("05:00")
    assert house.position(SHADE) == 25
    assert _differ_issues(hass) == {}

    # Back to the house's value: the override goes away.
    await house.set_options(**{CONF_SUNSET_POS: 0})
    assert house.entry.options["overrides"]["values"] == {}
    assert window.attributes["provenance"] == {}
    assert window.target == 0
    await house.teardown()


async def test_dropped_switch_writes_through(hass, freezer):
    house = await _house(hass, freezer)
    window = house.window()
    await house.advance_to("10:00")

    await house.toggle("manual_override", False)
    # Detection may not be set per window in the spec: a legacy value.
    assert house.entry.options["overrides"]["legacy"] == {CONF_MANUAL_DETECTION: False}
    assert window.attributes["provenance"] == {CONF_MANUAL_DETECTION: "legacy"}
    assert house.entity("switch", "manual_override").state == "off"
    await house.user_moves(SHADE, 100, via="remote")
    await house.advance_to("10:30")
    assert not window.manual_override, "detection is off for this window"

    await house.toggle("manual_override", True)
    assert house.entry.options["overrides"]["legacy"] == {}
    assert house.entity("switch", "manual_override").state == "on"
    assert _differ_issues(hass) == {}
    await house.teardown()
