# Adaptive Cover — Architecture & Codebase Guide

## What It Does

A Home Assistant custom integration that automatically positions window blinds, awnings, and venetian blinds based on solar geometry. It calculates where the sun is relative to each window and sets cover positions to block direct sunlight. Optionally adds climate-aware logic (temperature, presence, weather) to balance glare reduction with passive heating/cooling.

## Supported Cover Types

| Type | Key Parameters | Position Meaning |
|------|---------------|-----------------|
| **Vertical blind** | window height, distance to shade area | % of window covered from top |
| **Horizontal awning** | awning length, awning angle | % of awning extended |
| **Venetian tilt** | slat depth, slat spacing | slat tilt angle as % |

## Directory Layout

```
custom_components/adaptive_cover/
├── __init__.py              # Entry point: platform setup, event listeners
├── coordinator.py           # Core: data update loop, cover service calls, manual override tracking
├── calculation.py           # Solar geometry & position math (the algorithm)
├── config_flow.py           # Multi-step UI configuration (setup + options)
├── const.py                 # All config keys, defaults, enums
├── sensor.py                # Sensor entities (position %, solar times, control mode)
├── switch.py                # Toggle switches (control, climate mode, lux, etc.)
├── binary_sensor.py         # Binary sensors (sun in front, manual override active)
├── button.py                # Reset manual override button
├── sun.py                   # Astral-based solar position provider
├── helpers.py               # Utility functions (safe state access, datetime parsing)
├── config_context_adapter.py # Logger adapter that tags logs with config name
├── diagnostics.py           # HA diagnostics export
├── manifest.json            # Integration metadata & dependencies
├── strings.json             # English UI strings
├── icons.json               # MDI icon mappings
├── translations/            # NL, DE, SK, ES, FR translations
├── blueprints/              # HA automation blueprints
└── simulation/              # Simulation utilities
```

## Core Architecture

### Data Flow

```
sun.sun state change ──┐
temp entity change ────┤
presence change ───────┤──▶ AdaptiveDataUpdateCoordinator._async_update_data()
weather change ────────┤         │
cover state change ────┘         ▼
                          Instantiate cover class (Vertical/Horizontal/Tilt)
                                 │
                          ┌──────┴──────┐
                          ▼             ▼
                     BasicMode    ClimateMode
                     (NormalCoverState)  (ClimateCoverState)
                          │             │
                          └──────┬──────┘
                                 ▼
                          Raw position (0-100%)
                                 │
                          Apply transforms:
                            - interpolation (custom ranges)
                            - inverse (if enabled)
                            - min/max clamp
                                 │
                          Gate checks:
                            - timing window (start/end time)
                            - position delta threshold
                            - time delta throttle
                            - manual override check
                                 │
                          ▼
                    cover.set_cover_position service call
```

### Key Classes

**`AdaptiveDataUpdateCoordinator`** (coordinator.py) — The hub. Inherits HA's `DataUpdateCoordinator`. Listens to state changes, runs the calculation pipeline, calls cover services, tracks manual overrides. Contains `AdaptiveCoverManager` for per-cover override state.

**`AdaptiveGeneralCover`** (calculation.py) — Abstract base for all cover types. Holds window geometry (azimuth, FOV, height) and sun state. Subclasses:
- `AdaptiveVerticalCover` — triangle geometry: `height = (distance / cos(gamma)) * tan(elevation)`
- `AdaptiveHorizontalCover` — extends vertical with awning length/angle
- `AdaptiveTiltCover` — venetian slat angle from research paper (MDPI 1996-1073/13/7/1731)

**`NormalCoverState`** / **`ClimateCoverState`** (calculation.py) — Strategy classes that evaluate whether to use calculated position, default position, or sunset position based on sun validity and climate conditions.

**`SunData`** (sun.py) — Wraps astral library. Generates daily solar position data at 5-minute intervals. Provides sunrise/sunset, azimuth/elevation lists.

### Config Flow (config_flow.py)

Multi-step wizard:
1. **User** → pick blind type + name
2. **Vertical/Horizontal/Tilt** → window geometry parameters
3. **Interpolation** (optional) → custom position mapping
4. **Blind spot** (optional) → shadow exclusion zones
5. **Automation** → timing, delta thresholds, manual override duration
6. **Climate** (optional) → temp/presence/weather/lux/irradiance entities
7. **Weather** (optional) → which weather conditions trigger control

Both initial setup (`ConfigFlow`) and edit (`OptionsFlowHandler`) share the same step logic via `_SchemaCommonFlowHandler`.

## Solar Algorithm Details

### Gamma (Relative Sun Angle)
```python
gamma = (window_azimuth - solar_azimuth + 180) % 360 - 180
```
Sun is "in front" when `-fov_right < gamma < fov_left` and elevation > 0.

### Vertical Blind Position
```python
blind_height = clip(
    (distance / cos(gamma_rad)) * tan(elevation_rad),
    0, window_height
)
position = blind_height / window_height * 100
```
Lower sun → more penetration → cover moves down.

### Horizontal Awning Position
Extends vertical calculation using sine rule to find required awning extension.

### Venetian Tilt
```python
beta = arctan(tan(elevation) / cos(gamma))
slat_angle = 2 * arctan(
    (tan(beta) + sqrt(tan(beta)² - (spacing/depth)² + 1)) / (1 + spacing/depth)
)
percentage = slat_angle / 90 * 100  # or /180 for bidirectional
```

## Climate Mode Logic

Two dimensions: **presence** (home/away) and **season** (winter/summer/intermediate).

| Presence | Season | Action |
|----------|--------|--------|
| Home | Summer, sun valid | Use calculated position (block glare) |
| Home | Winter, sun valid | Open fully (passive heating) |
| Home | Any, sun not valid | Default position |
| Away | Summer | Close fully (block heat gain) |
| Away | Winter | Open fully (passive heating) |

Season is determined by comparing current temperature against configurable low/high thresholds.

## Entity Inventory (per config entry)

| Platform | Entity | Purpose |
|----------|--------|---------|
| sensor | Cover position | Calculated position (0-100%) |
| sensor | Start sun time | When sun enters FOV |
| sensor | End sun time | When sun leaves FOV |
| sensor | Control method | "winter" / "summer" / "intermediate" |
| binary_sensor | Sun in front | Is sun within window FOV? |
| binary_sensor | Manual override | Any cover under manual control? |
| switch | Toggle control | Enable/disable auto positioning |
| switch | Toggle manual override | Enable/disable override detection |
| switch | Toggle climate mode | Basic vs climate mode |
| switch | Toggle outside temp | Use outside temp sensor (climate only) |
| switch | Toggle lux | Use lux sensor (climate only) |
| switch | Toggle irradiance | Use irradiance sensor (climate only) |
| button | Reset manual override | Clear all manual override states |

## Manual Override Detection

1. Cover state change event fires
2. Coordinator compares cover's actual position to last calculated position
3. If difference exceeds `CONF_DELTA_POSITION` threshold → mark as manually overridden
4. Override persists for `CONF_MANUAL_OVERRIDE_DURATION` minutes (or until reset button)
5. `CONF_MANUAL_OVERRIDE_RESET` controls whether auto-control resumes after duration

## Dependencies

- **astral** — solar position calculations
- **pandas** — time series (5-min interval generation)
- **numpy** — trigonometry, interpolation, clipping
- **voluptuous** — config schema validation

## Patterns Worth Knowing

- **Coordinator pattern**: single `DataUpdateCoordinator` per config entry, all entities subscribe
- **RestoreEntity**: switches persist state across HA restarts
- **Executor offload**: solar calculations run in `hass.async_add_executor_job` to avoid blocking
- **Contextual logging**: `ConfigContextAdapter` prepends config name to all log messages
- **Service call throttling**: position delta + time delta + timing window gates before calling covers
- **Config merging**: options flow updates `config_entry.options`; coordinator merges `data + options`

## Fork & Release Workflow

This is a fork of [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover) hosted at [mrvollger/adaptive-cover](https://github.com/mrvollger/adaptive-cover).

### Development

1. Make changes locally and run tests: `python -m pytest tests/ -vv`
2. Commit and push to `main`

### Releasing to HACS

HACS requires a GitHub Release to see updates. After pushing:

```bash
gh release create v1.x.x --repo mrvollger/adaptive-cover \
  --title "v1.x.x - Short description" \
  --notes "Changelog details here."
```

HACS will then show the update available. The user clicks **Update** in HACS → restarts HA.

### HACS Configuration

- `hacs.json` has `"zip_release": false` — HACS downloads the repo directly (no zip artifact needed)
- The repo must have at least one GitHub Release for HACS to install it
- Users add `https://github.com/mrvollger/adaptive-cover` as a **Custom Repository** (category: Integration) in HACS

### Deploying Without HACS

Alternatively, SSH into the HA instance and copy files directly:

```bash
cd /tmp
git clone https://github.com/mrvollger/adaptive-cover.git
cp -r adaptive-cover/custom_components/adaptive_cover /config/custom_components/
rm -rf /tmp/adaptive-cover
# Then restart HA
```

### Important Notes

- HA config (integration settings) is stored in `.storage/core.config_entries`, not in the integration code — replacing the code preserves configuration
- If the upstream repo was previously installed via HACS, remove it first before adding this fork
- Delete any `adaptive_cover.bak` directories in `custom_components/` — HA will try to load them as integrations
