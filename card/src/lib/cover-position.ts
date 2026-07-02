import type { HomeAssistant } from 'custom-card-helpers';

import type { DiscoveredEntities } from '../types';
import { aggregateActualPosition } from './geometry';
import { liveCoverPosition } from './trace-adapter';

/**
 * Shared cover-position readers for the COVERS bar and the sky compass.
 *
 * With the Adaptive Cover integration the Cover Position sensor STATE is
 * always the engine's target position (a manual override does not rewrite
 * it), and per-cover actuals are read live from each managed cover entity's
 * `current_position` / `current_tilt_position` attribute. A manual override
 * therefore shows up naturally as actual ≠ target.
 */

/** Engine target position — the Cover Position sensor state. Null when
 *  missing/NaN. */
export function coverHeldPosition(hass: HomeAssistant, d: DiscoveredEntities): number | null {
  const id = d.entities.target_position_sensor;
  if (!id) return null;
  const val = parseFloat(hass.states[id]?.state ?? '');
  return Number.isNaN(val) ? null : val;
}

/** Alias for the engine target (kept for callers that distinguish
 *  solar-target vs held; this integration exposes only the one target). */
export function coverSolarTarget(hass: HomeAssistant, d: DiscoveredEntities): number | null {
  return coverHeldPosition(hass, d);
}

/** Per-cover live positions keyed by entity_id, read from the managed cover
 *  entities themselves. */
export function coverActualPositions(
  hass: HomeAssistant,
  d: DiscoveredEntities,
): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const id of d.managed_covers) {
    out[id] = liveCoverPosition(hass, d.cover_type, id);
  }
  return out;
}

/** Mean of the live per-cover positions. Null when there are no managed
 *  covers or none reports a position. */
export function coverActualPosition(hass: HomeAssistant, d: DiscoveredEntities): number | null {
  if (d.managed_covers.length === 0) return null;
  return aggregateActualPosition(coverActualPositions(hass, d));
}

/** True when the discovered manual-override binary sensor is `on`. */
export function manualOverrideActive(hass: HomeAssistant, d: DiscoveredEntities): boolean {
  const id = d.entities.manual_override_binary;
  if (!id) return false;
  return hass.states[id]?.state === 'on';
}

/** True when a manual override is active AND the live aggregate diverges from
 *  the engine target (so the bar/compass should split target vs actual). */
export function isOverrideDivergence(hass: HomeAssistant, d: DiscoveredEntities): boolean {
  if (!manualOverrideActive(hass, d)) return false;
  const target = coverHeldPosition(hass, d);
  const actual = coverActualPosition(hass, d);
  if (target === null || actual === null) return false;
  return Math.round(actual) !== Math.round(target);
}

/** The value to label and mark as "Target": always the engine target here. */
export function displayTarget(hass: HomeAssistant, d: DiscoveredEntities): number | null {
  return coverHeldPosition(hass, d);
}
