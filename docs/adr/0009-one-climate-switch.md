# ADR 0009: One Climate switch: climate capability is derived, a window opts out, house 3.2

- **Status:** Proposed (the owner approved the change; accepted at merge)
- **Date:** 2026-09-30
- **Delivered in:** after v2.1.0 (house config entry 3.2)
- **Amends:** [ADR 0003](0003-settings-precedence.md) (the settings table: `climate_mode` leaves it, `ignore_climate` joins the one-time window settings) and [ADR 0007](0007-house-only-in-v2-1.md) (the house version after it). The rest of both stands.
- **Source:** [`docs/refactor_plan.md`](../refactor_plan.md), "One-time vs recurring settings" (the "Ignore climate" exception row)

## Context

Two settings said "climate on": `climate_on` (the house's Climate switch, a room can turn it off; the card's Climate control) and `climate_mode` (a recurring setting at the house and the rooms, from the 1.x setup wizard's "Climate mode" toggle). Climate control ran only with both on. `climate_mode` really answered "can this window run climate control at all": the wizard made it the switch that showed the climate page with its temperature sensor. The owner had two switches that looked the same, and the card showed both.

## Decision

- **`climate_on` is the only climate on/off setting** (recurring: house, room override). No form, service (`change_settings`, `add_entry`, `set_profile`), profile (`get_profile`) or card sheet offers `climate_mode`.
- **Climate capability is derived, never stored** (`runtime/shade_config.climate_capable`): a window can run climate control when a temperature source resolves for it (its indoor temperature sensor from the window, room, floor or house; the outside temperature sensor; the weather entity, whose temperature the outside reading falls back to) and it does not opt out.
- **`ignore_climate`** is a one-time window setting (default False; the window form's Advanced section, the window record's geometry, `change_settings`): the window follows the sun alone.
- **Runtime rule:** climate control runs when `climate_on and not ignore_climate and a temperature source exists`.
- **Migration 3.1 -> 3.2** (`upgrade.py`, also right after 2.1 -> 3.1): a window whose `climate_mode` resolved to False (its 3.1 precedence: its own value, its room, its floor, the house, the default False) gets `ignore_climate: True`; `climate_mode` leaves the window overrides and the house, floor and room profiles (a profile left empty goes).

## Consequences

- The live house (all 15 windows had `climate_mode` on, each with a temperature sensor) takes the migration with nothing behavioral written: no window gets `ignore_climate`, every resolved setting is the same except that `climate_mode` is gone and `ignore_climate` reads False, and the house replay matches its goldens byte for byte through 2.1 -> 3.1 -> 3.2.
- A window that had `climate_mode` on but no temperature source at all (no indoor sensor, outside sensor or weather entity) stops running climate control. Such a window had no season, only presence, lux and irradiance inputs.
- A new window (the form or `add_entry`) runs climate control when the house has it on and the window has a temperature source; `add_entry` without `copy_from` used to start with `climate_mode` off.
- Rolling back to v2.1.0 (HACS downgrade) loads the 3.2 house as a newer minor, but v2.1.0 reads the missing `climate_mode` as its default (off): every window runs without climate control until the Home Assistant backup is restored.
- Mutations M160 (`ignore_climate` ignored) and M161 (the migration drops a window's opt-out) guard the rule and the migration.

## Alternatives considered

- **Keep `climate_mode` as a hidden capability flag.** Rejected: it is stored state that only restates whether the window has a temperature sensor, and a second switch the owner has to understand.
- **Map a room's `climate_mode` off to the room's `climate_on` off.** Rejected: `climate_on` is the day-to-day switch the card toggles; turning it back on would silently re-enable windows that were set up without climate control. The opt-out stays on each window.
- **A major version (4.1).** Rejected: the change is small and the owner chose 3.2; the rollback is the backup either way.
