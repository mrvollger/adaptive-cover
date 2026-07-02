import type { HomeAssistant } from 'custom-card-helpers';

import type {
  CoverPositionAttributes,
  DecisionTraceAttributes,
  DiscoveredEntities,
  ForecastEvent,
  ForecastSample,
  PositionForecastAttributes,
  SunPositionAttributes,
} from '../types';

/**
 * Adapters from the Adaptive Cover integration's single rich sensor —
 * `sensor.*_cover_position` (state = target %, attributes = intent /
 * decision_trace / forecast_today / sun / last_moves / move_blocked_by) —
 * to the card-internal view models.
 *
 * The upstream (Pro) card read a dozen dedicated diagnostic sensors; this
 * integration consolidates everything onto the Cover Position sensor, so all
 * reads funnel through here.
 */

/** Raw attributes of the Cover Position sensor, or undefined when absent. */
export function readCoverAttrs(
  hass: HomeAssistant,
  d: DiscoveredEntities,
): CoverPositionAttributes | undefined {
  const id = d.entities.target_position_sensor;
  if (!id) return undefined;
  const st = hass.states[id];
  if (!st) return undefined;
  return st.attributes as unknown as CoverPositionAttributes;
}

/** The winning engine intent, falling back to 'default'. */
export function readIntent(hass: HomeAssistant, d: DiscoveredEntities): string {
  const attrs = readCoverAttrs(hass, d);
  return attrs?.intent ?? 'default';
}

/**
 * Synthesize the card's decision context from `decision_trace` (string list)
 * + `intent`. Each trace line becomes one step; the last line is the winning
 * step (`matched: true`).
 */
export function readTraceAttrs(
  hass: HomeAssistant,
  d: DiscoveredEntities,
): DecisionTraceAttributes | undefined {
  const attrs = readCoverAttrs(hass, d);
  if (!attrs) return undefined;
  const lines = Array.isArray(attrs.decision_trace) ? attrs.decision_trace : [];
  const trace = lines.map((line, i) => ({
    handler: line,
    matched: i === lines.length - 1,
    reason: line,
    position: null,
  }));
  return {
    trace,
    reason: lines.length > 0 ? lines[lines.length - 1] : '',
    winner: attrs.intent ?? 'default',
    sun_azimuth: attrs.sun?.azimuth,
    sun_elevation: attrs.sun?.elevation,
    gamma: attrs.sun?.gamma,
    in_field_of_view: attrs.sun?.in_fov,
    default_position: attrs.default,
    sunset_position: attrs.sunset_default,
  };
}

/** The `sun` geometry block for the sky compass / elevation chart, or null. */
export function readSunAttrs(
  hass: HomeAssistant,
  d: DiscoveredEntities,
): SunPositionAttributes | null {
  const attrs = readCoverAttrs(hass, d);
  const sun = attrs?.sun;
  if (!sun || typeof sun.azimuth !== 'number' || typeof sun.elevation !== 'number') return null;
  return sun;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Map `forecast_today` change-points into the forecast strip's view model.
 *
 * The integration emits change-points only, so the samples are expanded into
 * a step curve (each change-point is preceded by a sample holding the prior
 * position) and extended to the end of the day. Events mark each intent
 * transition.
 */
export function readForecast(
  hass: HomeAssistant,
  d: DiscoveredEntities,
): PositionForecastAttributes | null {
  const attrs = readCoverAttrs(hass, d);
  const raw = attrs?.forecast_today;
  if (!Array.isArray(raw) || raw.length === 0) return null;

  const samples: ForecastSample[] = [];
  const events: ForecastEvent[] = [];
  let prev: { time: string; position: number; intent: string } | null = null;
  for (const entry of raw) {
    if (!entry || typeof entry.time !== 'string') continue;
    if (prev !== null) {
      // Hold the previous position until the instant of the change → step curve.
      samples.push({ t: entry.time, position: prev.position, handler: prev.intent });
      if (entry.intent !== prev.intent) {
        events.push({ t: entry.time, kind: entry.intent, label: entry.intent });
      }
    }
    samples.push({ t: entry.time, position: entry.position, handler: entry.intent });
    prev = entry;
  }
  if (prev !== null) {
    // Extend the final position to the end of the local day.
    const lastTs = Date.parse(prev.time);
    if (!Number.isNaN(lastTs)) {
      const dayEnd = new Date(lastTs);
      dayEnd.setHours(23, 59, 59, 0);
      if (dayEnd.getTime() - lastTs < DAY_MS) {
        samples.push({
          t: dayEnd.toISOString(),
          position: prev.position,
          handler: prev.intent,
        });
      }
    }
  }
  return { forecast: samples, events };
}

/**
 * Cover entity_ids managed by this entry, discovered from the union of the
 * `last_moves` and `move_blocked_by` attribute keys. Sorted for stability.
 * Empty when the integration has not yet recorded a move for any cover —
 * the card then falls back to entry-level rendering only.
 */
export function managedCoversFrom(attrs: CoverPositionAttributes | undefined): string[] {
  if (!attrs) return [];
  const ids = new Set<string>();
  for (const key of Object.keys(attrs.last_moves ?? {})) ids.add(key);
  for (const key of Object.keys(attrs.move_blocked_by ?? {})) ids.add(key);
  return [...ids].sort();
}

/** Live reported position of one cover: `current_tilt_position` for tilt
 *  covers, else `current_position`. */
export function liveCoverPosition(
  hass: HomeAssistant,
  coverType: string,
  entityId: string,
): number | null {
  const attrs = hass.states[entityId]?.attributes as
    | { current_position?: number; current_tilt_position?: number }
    | undefined;
  const v = coverType === 'cover_tilt' ? attrs?.current_tilt_position : attrs?.current_position;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
