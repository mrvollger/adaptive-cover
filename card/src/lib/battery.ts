import type { HomeAssistant } from 'custom-card-helpers';

import type { EntityRegistryEntry } from './entity-registry';

/** At or below this % the indicator turns amber (the household alert
 *  threshold - several shades live here for weeks, so it must not be red). */
export const BATTERY_WARN_PCT = 25;

/** At or below this % the indicator turns red: these motors start refusing
 *  commands around 20% and die near 5%, so this means "charge today". */
export const BATTERY_LOW_PCT = 12;

/** Above this % the number is noise - show the icon only. */
export const BATTERY_SHOW_NUMBER_PCT = 40;

/**
 * Locate the battery sensor that lives on the same device as a cover.
 *
 * The registry slim payload carries no device_class, so this matches by
 * device_id + sensor domain + a "battery" token in the entity_id — which is
 * how ZHA names them (sensor.<device>_battery).
 */
export function findBatterySensor(
  registry: EntityRegistryEntry[] | null,
  coverEntityId: string | undefined,
): string | null {
  if (!registry || !coverEntityId) return null;
  const cover = registry.find((e) => e.entity_id === coverEntityId);
  if (!cover?.device_id) return null;
  const battery = registry.find(
    (e) =>
      e.device_id === cover.device_id &&
      e.entity_id.startsWith('sensor.') &&
      /(^|_)battery(_|$)/.test(e.entity_id.split('.')[1]),
  );
  return battery?.entity_id ?? null;
}

export interface BatteryReading {
  /** Percentage, or null when the sensor exists but reports no number. */
  level: number | null;
  /** False when the sensor is unavailable/unknown - a dead battery looks
   *  exactly like this (the 5% shade went offline unnoticed), so callers
   *  must render a stale marker, never hide it. */
  available: boolean;
}

/** Read the battery sensor; null only when there is NO sensor at all. */
export function batteryReading(
  hass: HomeAssistant,
  sensorId: string | null,
): BatteryReading | null {
  if (!sensorId) return null;
  const st = hass.states[sensorId];
  if (!st || st.state === 'unavailable' || st.state === 'unknown') {
    return { level: null, available: false };
  }
  const v = parseFloat(st.state);
  return Number.isNaN(v) ? { level: null, available: false } : { level: v, available: true };
}
