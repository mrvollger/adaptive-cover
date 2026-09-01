# Simulation harness — test the house without the house

`harness.py` runs the **real integration** (config entry, coordinator,
listeners, entities) against a fully simulated house:

- **Fake shades** that behave like the real Smartwings/Zigbee covers: an
  `opening`/`closing` intermediate state the moment a command arrives, a
  landing position report only after a travel delay (default 120 s), with a
  fresh (device) context — so the coordinator's echo/travel/manual-detection
  logic is exercised exactly as in production.
- **A real sun**: astral-computed azimuth/elevation for a fixed date and
  location (SLC by default), written to `sun.sun` each tick.
- **A stepped frozen clock** (`freezer` + `async_fire_time_changed`), so
  point-in-time listeners (end-of-day close, arrival polls) fire in
  simulated time. The process timezone is deliberately NOT aligned with the
  configured HA timezone — the suite proves schedule math is tz-correct.

## Writing a scenario

```python
async def test_my_scenario(hass, freezer):
    house = await SimHouse.create(
        hass, freezer,
        date="2026-03-20",
        covers=["cover.shade"],
        options={CONF_END_TIME: "20:00:00", CONF_RETURN_SUNSET: True},
    )
    await house.advance_to("14:00")
    await house.user_moves("cover.shade", 100, via="remote")   # or "dashboard"
    await house.advance_to("16:00")
    assert house.auto_moves("cover.shade", since="14:00") == []
    await house.teardown()
```

- `house.timeline` — every service call and cover state write, timestamped,
  attributed to `integration` / `human` / `device`.
- `house.auto_moves(entity, since=, until=)` — integration-commanded moves.
- `house.user_moves(entity, pos, via=)` — a human act. `"remote"` models the
  physical remote (foreign state changes, no user context); `"dashboard"`
  models an HA service call with a user context.
- `house.advance_to("HH:MM")` — step to a local time (crosses midnight if
  already past); `house.tick()` — one step.

To replay a real incident from HA history, script the observed cover events
with `user_moves` / direct `hass.states.async_set` at the recorded times.

`test_symptoms.py` pins the two 2026-09 field symptoms (manual overrides
reverted; end-of-day close missed); `test_regressions.py` pins the
coordinator fixes that came out of that bug hunt.
