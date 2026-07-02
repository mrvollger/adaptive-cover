# Adaptive Cover Card

Lovelace cards for the [Adaptive Cover](https://github.com/mrvollger/adaptive-cover) Home Assistant integration (domain `adaptive_cover`, fork of [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover)). Drop a tile on your dashboard to see where every shade sits and why, and put up a compass that shows the sun crossing each window in real time.

> **Fork notice:** this card bundle is a fork of [jrhubott/adaptive-cover-pro-card](https://github.com/jrhubott/adaptive-cover-pro-card) (MIT, © Jason Rhubottom), adapted to the `adaptive_cover` integration's entity surface. The original MIT license is preserved in [LICENSE](LICENSE). Upstream targets the Adaptive Cover **Pro** integration and will not work with `adaptive_cover` (and vice versa).

## Cards in this bundle

| Card | Type | Summary |
|------|------|---------|
| Adaptive Cover | `custom:adaptive-cover-card` | The full card: pick one integration entry, get every section (compass, sun-today chart, decision trace, per-cover bars, overrides, climate). |
| Tile | `custom:adaptive-cover-tile-card` | Compact per-shade row: icon, name, position, `↑ ■ ▼`, and a live intent badge. Tap opens a detail dialog. |
| Sky Compass | `custom:adaptive-cover-sky-compass-card` | The compass on its own. Accepts multiple entries and overlays each window's FOV and cover wedge on a shared sun dot. |
| Decision strip | `custom:adaptive-cover-decision-card` | Standalone decision trace: every engine step for one entry with the winning step highlighted. |

## What the cards read

Everything comes from the integration's **Cover Position** sensor for the chosen config entry:

- the sensor **state** is the engine's target position (0–100 %),
- `intent` — what the engine is trying to achieve (`calculated`, `default`, `sunset`, `privacy`, `admit_no_glare`, `shaded_by_overhang`, `climate_*`) — drives the tile badge and winner label,
- `decision_trace` — prose lines rendered as the decision strip; the last line is the winning step,
- `forecast_today` — today's position change-points, rendered as the forecast strip in the tile dialog,
- `sun` — solar geometry (azimuth, elevation, gamma, window azimuth, FOV, elevation limits) for the sky compass and elevation chart,
- `last_moves` / `move_blocked_by` — per-cover move log and gate blocks, also used to **discover the managed covers**.

Plus the entry's other entities (matched via registry `unique_id`): the Sun Infront and Manual Override binary sensors, the Toggle Control / Manual Override / Climate Mode switches, the Start Sun / End Sun / Control Method sensors, and the Reset Manual Override button.

All cover actions use standard Home Assistant services (`cover.set_cover_position`, `cover.stop_cover`, `cover.set_cover_tilt_position`, `switch.turn_on/off`, `button.press`) — no custom services, and the cards make zero third-party network calls.

### Known limitations

- **Managed covers are discovered from `last_moves` / `move_blocked_by`.** Until the integration has recorded at least one move (or blocked gate) for a cover, the tile's `↑ ■ ▼` controls and the per-cover bars have nothing to act on and the card shows the entry-level position only. Setting `cover: cover.your_cover` in the tile config bypasses discovery.
- **Blind type is not exposed by the integration**, so the compass/tile default to vertical-blind visuals. Tilt entries are inferred when the managed covers only report `current_tilt_position`. Awning geometry renders as a vertical blind; override the tile icon with `icon:` if desired.
- The manual-override badge shows no expiry countdown (the integration does not expose the override end time).

## Install

**HACS:**

1. Add `https://github.com/mrvollger/adaptive-cover-card` as a custom repository (category: **Dashboard**).
2. Install **Adaptive Cover Card** and refresh.
3. The cards appear in the card picker under "Adaptive Cover".

**Manual:**

1. Build or download `adaptive-cover-card.js`.
2. Copy it to `config/www/adaptive-cover-card.js`.
3. Add a dashboard resource:
   ```yaml
   url: /local/adaptive-cover-card.js
   type: module
   ```

## Configuration

Every option is exposed in the visual editor; the YAML below is the equivalent. Find your `entry_id` at `/config/integrations/integration/adaptive_cover`: click the entry and read it out of the URL bar (`config_entry=...`), or just use the editor dropdown.

**Tile card** (stack one per shade):
```yaml
type: custom:adaptive-cover-tile-card
entry_id: YOUR_CONFIG_ENTRY_ID
# optional:
# name: Patio Right
# icon: mdi:blinds-horizontal
# cover: cover.patio_right_shade   # explicit cover when discovery is empty
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
entry_ids:
  - KITCHEN_ENTRY_ID
  - LIVING_ROOM_ENTRY_ID
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
entry_id: YOUR_CONFIG_ENTRY_ID
# optional:
# show_sections: [sky, decision, covers, overrides]
# compact: false
```

**Decision strip:**
```yaml
type: custom:adaptive-cover-decision-card
entry_id: YOUR_CONFIG_ENTRY_ID
```

## For developers

```bash
npm install
npm run build      # → dist/adaptive-cover-card.js
npm run dev        # rollup -c -w, rebuilds dist/ on save
npm test           # vitest
npm run typecheck
npm run lint
```

The upstream dev harness (a browser playground that simulated the Pro integration's 11-handler pipeline) was removed in this fork; the vitest suite covers the components against the `adaptive_cover` schema.

## Credits

Forked from [jrhubott/adaptive-cover-pro-card](https://github.com/jrhubott/adaptive-cover-pro-card). Pairs with [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover), itself forked from [basbruss/adaptive-cover](https://github.com/basbruss/adaptive-cover).
