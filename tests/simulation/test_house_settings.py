"""A house setting reaches every window without a reload (P5 flip).

The plan's scenario: the owner changes the house's cooling threshold on
the hub device; every window re-reads its settings and acts on the new
threshold at once (its season flips), without a reload and before the
next sun tick.
"""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from custom_components.adaptive_cover.const import CONF_TEMP_HIGH, DOMAIN
from custom_components.adaptive_cover.entity_surface import HUB_UNIQUE_ID

from .harness import SimHouse

COVERS = ["cover.office", "cover.den"]


async def test_house_threshold_change_reaches_every_window(hass, freezer):
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-06-21",
        covers=COVERS,
        start_at="10:00",
        climate={
            "temp": 22.0,
            "presence": "home",
            "weather": "sunny",
            "temp_low": 21.0,
            "temp_high": 23.0,
        },
    )
    await house.advance_to("10:30")
    teardowns = {cover: house.window(cover).teardowns for cover in COVERS}
    for cover in COVERS:
        assert house.entity("sensor", "control_method", cover=cover).state == (
            "intermediate"
        )

    cooling = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{HUB_UNIQUE_ID}_{CONF_TEMP_HIGH}"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": cooling, "value": 21.5}, blocking=True
    )
    await hass.async_block_till_done()

    # 22 °C is above the new 21.5 °C cooling threshold: summer, right away.
    for cover in COVERS:
        assert house.entity("sensor", "control_method", cover=cover).state == "summer"
        assert house.window(cover).teardowns == teardowns[cover], "a reload"
        assert (await house.window(cover).settings())[CONF_TEMP_HIGH] == 21.5
    await house.teardown()
