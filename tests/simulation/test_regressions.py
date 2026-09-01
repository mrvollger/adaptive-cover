"""Simulation regressions for coordinator fixes (2026-09 bug hunt)."""

from custom_components.adaptive_cover.const import DOMAIN

from .harness import SimHouse

A = "cover.left"
B = "cover.right"


async def test_regression_group_remote_latches_both_covers(hass, freezer):
    """Two covers moved in the same instant must BOTH latch manual.

    A single shared state_change_data slot dropped one event when a
    room-group remote moved several covers at once.
    """
    house = await SimHouse.create(
        hass, freezer, date="2026-03-20", covers=[A, B]
    )
    await house.advance_to("11:10")

    await house.user_moves(A, 100, via="remote")
    await house.user_moves(B, 100, via="remote")
    await house.advance_to("11:20")

    coord = house.coordinator
    assert coord.manager.is_cover_manual(A), "left cover override dropped"
    assert coord.manager.is_cover_manual(B), "right cover override dropped"
    assert house.auto_moves(A, since="11:10") == []
    assert house.auto_moves(B, since="11:10") == []
    await house.teardown()


async def test_regression_override_clears_on_new_day(hass, freezer):
    """Day rollover is a safety net: even an absurdly long override
    duration cannot carry a stale override into the next solar day."""
    house = await SimHouse.create(
        hass,
        freezer,
        date="2026-03-20",
        options={"manual_override_duration": {"hours": 48}},
    )
    await house.advance_to("15:00")
    await house.user_moves("cover.shade", 100, via="remote")
    await house.advance_to("23:00")
    assert house.coordinator.manager.is_cover_manual("cover.shade")

    # Cross midnight into the next solar day: auto control resumes.
    await house.advance_to("10:00")  # next day
    assert not house.coordinator.manager.is_cover_manual("cover.shade")
    await house.teardown()


async def test_regression_overrides_survive_entry_reload(hass, freezer):
    """Options reloads rebuild the coordinator; overrides must survive."""
    house = await SimHouse.create(hass, freezer, date="2026-03-20")
    await house.advance_to("11:10")
    await house.user_moves("cover.shade", 100, via="remote")
    assert house.coordinator.manager.is_cover_manual("cover.shade")

    await hass.config_entries.async_reload(house.entry.entry_id)
    await hass.async_block_till_done()
    house.coordinator = hass.data[DOMAIN][house.entry.entry_id]
    # the hub re-registers real cover services on reload; win them back
    house._register_services()

    assert house.coordinator.manager.is_cover_manual("cover.shade"), (
        "entry reload wiped the manual override"
    )
    await house.advance_to("11:25")
    assert house.auto_moves("cover.shade", since="11:10") == []
    await house.teardown()
