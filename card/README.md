# Adaptive Cover Card

Lovelace cards for the [Adaptive Cover](https://github.com/mrvollger/adaptive-cover) Home Assistant integration (domain `adaptive_cover`, fork of [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover)). Drop a tile on your dashboard to see where every shade sits and why, and put up a compass that shows the sun crossing each window in real time.

> **Fork notice:** this card bundle is a fork of [jrhubott/adaptive-cover-pro-card](https://github.com/jrhubott/adaptive-cover-pro-card) (MIT, © Jason Rhubottom), adapted to the `adaptive_cover` integration's entity surface. The original MIT license is preserved in [LICENSE](LICENSE). Upstream targets the Adaptive Cover **Pro** integration and will not work with `adaptive_cover` (and vice versa).

## Cards in this bundle

| Card | Type | Summary |
|------|------|---------|
| Adaptive Cover | `custom:adaptive-cover-card` | The full card: pick one window, get every section (compass, sun-today chart, decision trace, per-cover bars, overrides, climate). |
| Tile | `custom:adaptive-cover-tile-card` | Compact per-shade row: icon, name, position, `↑ ■ ▼`, and a live intent badge. Tap opens a detail dialog. |
| Sky Compass | `custom:adaptive-cover-sky-compass-card` | The compass on its own. Accepts multiple windows and overlays each window's FOV and cover wedge on a shared sun dot. |
| Decision strip | `custom:adaptive-cover-decision-card` | Standalone decision trace: every engine step for one window with the winning step highlighted. |

## What the cards read

Everything comes from the integration's **Cover Position** sensor of the chosen window:

- the sensor **state** is the engine's target position (0–100 %),
- `intent` — what the engine is trying to achieve (`calculated`, `default`, `sunset`, `privacy`, `admit_no_glare`, `shaded_by_overhang`, `climate_*`) — drives the tile badge and winner label,
- `decision_trace` — prose lines rendered as the decision strip; the last line is the winning step,
- `forecast_today` — today's position change-points, rendered as the forecast strip in the tile dialog,
- `sun` — solar geometry (azimuth, elevation, gamma, window azimuth, FOV, elevation limits) for the sky compass and elevation chart,
- `window_key`, `cover_entity` / `cover_entities`, `cover_type` — which window this is, the cover(s) it controls and its blind type (see [How a card finds its window](#how-a-card-finds-its-window)),
- `last_moves` / `move_blocked_by` — per-cover move log and gate blocks. With an integration that does not publish `cover_entity`, these keys are also how the card finds the managed covers.

Plus the window's other entities (matched via registry `unique_id`): the Sun Infront and Manual Override binary sensors, the Toggle Control / Manual Override / Climate Mode switches, the Start Sun / End Sun / Control Method sensors, and the Reset Manual Override button.

### How a card finds its window

A card names its window with one key:

- `window:` — the window key. The Cover Position sensor shows it in its `window_key` attribute. Use this for new cards; the card editors write it.
- `cover:` — the cover entity. The card uses the window whose Cover Position sensor lists that cover in `cover_entity` / `cover_entities`.
- `entry_id:` — the old key. Existing cards keep working without a change: a window's key is the entry_id of the config entry that created it.

When a config sets more than one, `window` wins, then `entry_id`, then `cover`. On a tile, `cover` next to `window` or `entry_id` only picks the cover the `↑ ■ ▼` controls act on.

Discovery never uses the registry's `config_entry_id` to find a window, because it stops naming a window once windows become subentries of one house entry (it is read only to build the settings link). The card finds the Cover Position sensor by its attributes first, and falls back to the unique_id prefix: every entity's unique_id is `{window_key}_{suffix}` and never changes. The window's other entities come from the same prefix.

All cover actions use standard Home Assistant services (`cover.set_cover_position`, `cover.stop_cover`, `cover.set_cover_tilt_position`, `switch.turn_on/off`, `button.press`) — no custom services, and the cards make zero third-party network calls.

### Known limitations

- **With an integration that does not publish `cover_entity`**, the managed covers come from `last_moves` / `move_blocked_by`. Until it has recorded at least one move (or blocked gate) for a cover, the tile's `↑ ■ ▼` controls and the per-cover bars have nothing to act on, and a `cover:`-only card cannot find its window. Setting `window:` (or `entry_id:`) plus `cover:` works with any version.
- **With an integration that does not publish `cover_type`**, the compass/tile default to vertical-blind visuals. Tilt windows are inferred when the managed covers only report `current_tilt_position`; awning geometry renders as a vertical blind. Override the tile icon with `icon:` if desired.
- The manual-override badge shows no expiry countdown (the integration does not expose the override end time).

## Install

The bundle ships inside the integration (`custom_components/adaptive_cover/www/`). On setup the integration serves it and registers it as a Lovelace resource, so installing or updating Adaptive Cover through HACS and restarting Home Assistant is all that is needed. The cards then appear in the card picker under "Adaptive Cover".

## Configuration

Every option is exposed in the visual editor; the YAML below is the equivalent. Pick the window in the editor dropdown, or read its key from the `window_key` attribute of its Cover Position sensor (Developer tools → States). An existing `entry_id:` config needs no change.

**Tile card** (stack one per shade):
```yaml
type: custom:adaptive-cover-tile-card
window: YOUR_WINDOW_KEY            # or: cover: cover.patio_right_shade
# optional:
# name: Patio Right
# icon: mdi:blinds-horizontal
# cover: cover.patio_right_shade   # with `window`: the cover the controls act on
# layout: detailed                 # 'detailed' | 'one-line'
# show_position: true
# show_controls: true
# show_badge: true
# show_decision_summary: false
# tap_action: { action: more-info }
```

**Sky compass** (one or more entries):
```yaml
type: custom:adaptive-cover-sky-compass-card
windows:
  - KITCHEN_WINDOW_KEY
  - LIVING_ROOM_WINDOW_KEY
# or covers: [cover.kitchen_shade, …]; the old entry_ids: list still works.
# Overlays are drawn in the order windows, covers, entry_ids.
# optional:
# title: West-facing windows
# show_elevation_chart: true
# show_moon: false
# show_sun_path: true
# show_legend: true
# show_stats: true
```

**Full card:**
```yaml
type: custom:adaptive-cover-card
window: YOUR_WINDOW_KEY            # or: cover: cover.your_shade
# optional:
# show_sections: [sky, decision, covers, overrides]
# compact: false
```

**Decision strip:**
```yaml
type: custom:adaptive-cover-decision-card
window: YOUR_WINDOW_KEY            # or: cover: cover.your_shade
```

## For developers

```bash
npm ci
npm run build          # → ../custom_components/adaptive_cover/www/adaptive-cover-card.js (commit it)
npm run dev            # rollup -c -w, rebuilds dist/ (with sourcemaps) on save
npm test               # vitest
npm run typecheck      # tsc --noEmit
npm run lint           # eslint + prettier --check
npm run check-bundle   # fails if the committed www/ bundle differs from a fresh build
```

The integration serves the bundle from `custom_components/adaptive_cover/www/`, so any change under `src/` needs `npm run build` and the rebuilt bundle in the same commit; CI runs `check-bundle` to enforce that. The card's own strings are English-only, like the integration; they live in `src/lib/i18n/en.ts`.

The upstream dev harness (a browser playground that simulated the Pro integration's 11-handler pipeline) was removed in this fork; the vitest suite covers the components against the `adaptive_cover` schema.

## Credits

Forked from [jrhubott/adaptive-cover-pro-card](https://github.com/jrhubott/adaptive-cover-pro-card). Pairs with [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover), itself forked from [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover).
