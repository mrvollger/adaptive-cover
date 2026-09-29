# Live-house snapshot (sanitized)

A read-only capture of the owner's real Home Assistant house, taken on
**2026-09-28** (evening, America/Denver). It is the P0 "live-snapshot
fixture" from `docs/refactor_plan.md`: later phases rehearse migrations
against it, and `tests/replay/` replays every live window from it.

## Provenance

- Source: Home Assistant OS, core **2026.9.4**, `adaptive_cover` **1.13.5**,
  time zone America/Denver, unit system US customary (°F).
- Captured with the home-assistant MCP **read-only** tools only
  (`ha_get_integration` incl. the integration's diagnostics dump,
  `ha_get_device`, `ha_get_entity`, `ha_get_state`, `ha_list_floors_areas`,
  `ha_config_get_dashboard`, `ha_search`). Nothing in the house was changed.
- Values are copied verbatim, then sanitized (see below). JSON is written
  with sorted keys so a refresh diffs cleanly.

## Files

| File | What it holds |
|---|---|
| `config_entries.json` | All 19 `adaptive_cover` config entries: 15 live windows (`role: window`), the hub "Adaptive Cover All" (`role: hub`), and the 3 disabled legacy "SE" multi-cover entries (`role: disabled_legacy`). `entry_id`, title, source, state, `data`, `options`. |
| `floors_areas.json` | The 3 floors and 21 areas (ids, names, floor links). |
| `device_registry.json` | The 16 `adaptive_cover` device rows (15 windows + hub): name, name_by_user, area, config entries, identifiers, entity_ids. |
| `entity_registry.json` | All 318 `adaptive_cover` registry rows (21 per window + 3 hub): entity_id, unique_id, device, config entry, area, disabled/hidden, categories, labels. None is disabled, hidden or orphaned. |
| `physical_covers.json` | The 15 physical covers and the hub's aggregate cover: platform, registry area, device area, state at capture time. |
| `entity_states.json` | 301 live states of the `adaptive_cover` switches, selects, numbers, binary sensors and sensors, captured 2026-09-28T21:11 -06:00. |
| `dashboard_shades.json` | The Lovelace dashboard `dashboard-shades` (full config + `config_hash` `fe8b68210008ffb2`, the hash named in the plan). |
| `dashboard_dashboard_home.json`, `dashboard_dashboard_areas.json` | Strategy dashboards (`home`, `areas`): no explicit references, but they list adaptive entities by area. |
| `consumers.json` | Automations, scripts, scenes and helpers that reference `adaptive_cover` entities (none), plus the ones that move the physical covers (`automation.meeting`, `scene.meeting`, 5 cover groups) and the queries used. |

### Completeness notes

- **Window and hub options are complete.** They come from the integration's
  diagnostics dump (`config_options`), so options that were never set are
  present as explicit `null`, exactly as stored in `.storage`.
- **Disabled legacy entries** cannot be diagnosed (HA does not load a
  disabled entry), so their `options` come from the entry listing
  (`null`-valued keys absent) and their `data` is not captured (`null`).
- **`restore_state` is not readable over MCP.** `entity_states.json` is the
  stand-in: the live switch states are what the replay seeds into the
  restore cache.
- **The manual-override store** lives in memory (`hass.data`); only what
  the Manual Override binary sensors expose in their attributes is captured.
- `entity_category` is not exposed by the MCP registry read, so it is `null`
  in `entity_registry.json`; the code sets it (numbers and the Mode select
  are `config`).
- HA had restarted at about 20:58, so no manual override was active at
  capture time (every `manual_controlled` list is empty) and every "Last
  State Change" sensor reads "No changes recorded".
- Every switch is at its integration default (Toggle Control, Manual
  Override and Climate Mode on; Outside Temperature off).
- Oddities kept verbatim (they are real-house state, not capture errors):
  - Entry "Leanne's door" has `data.name` "Leanne's west" (the title was
    renamed later; `data.name` was not).
  - The Heating/Cooling threshold numbers show 72/75 with unit °C and
    ranges 5–30 / 10–40, while the options hold °F values.
  - Every "Next State Change" sensor names the sunrise of 2026-09-30,
    although the capture was taken on the evening of 2026-09-28.
  - Entity_id prefixes are inconsistent on the older entries (for example
    `office_north_shades_*` next to `office_north_shade_*`, `sw_*` next to
    `leanne_s_*`, `number.master_master_trap_shade_*`).
  - Only 3 of the 15 window devices have an area; every physical cover
    gets its area from its ZHA device (the entity area is empty).

## Sanitization

- No tokens, keys, passwords, URLs with credentials, e-mail addresses or IP
  addresses.
- No latitude/longitude: tests use the SLC coordinates already in
  `tests/characterization/golden_lib.py`.
- No hardware identifiers (Zigbee IEEE / MAC `connections` are dropped).
- Names: only room and window names (some rooms are named after the person
  who uses them, e.g. "Leanne's", and the area "Mitchell's"); no `person.*`
  details.
- `tests/replay/test_house_snapshot.py` enforces this on every run.

## Refreshing

Re-capture with the same read-only tools, keep the file shapes, run
`python -m pytest tests/replay -q`, and regenerate the replay goldens only
if the house configuration really changed (`UPDATE_GOLDENS=1`). Commit the
snapshot diff and the golden diff together.
