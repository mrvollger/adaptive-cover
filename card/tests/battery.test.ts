import { describe, expect, it } from 'vitest';

import { batteryReading, findBatterySensor } from '../src/lib/battery';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';
import type { HomeAssistant } from 'custom-card-helpers';

const REG: EntityRegistryEntry[] = [
  {
    entity_id: 'cover.family_door_shades',
    unique_id: 'zha-cover',
    config_entry_id: 'zha',
    platform: 'zha',
    device_id: 'dev1',
  },
  {
    entity_id: 'sensor.family_room_door_shades_battery',
    unique_id: 'zha-batt',
    config_entry_id: 'zha',
    platform: 'zha',
    device_id: 'dev1',
  },
  {
    entity_id: 'sensor.family_room_door_shades_window_covering_type',
    unique_id: 'zha-wct',
    config_entry_id: 'zha',
    platform: 'zha',
    device_id: 'dev1',
  },
  {
    entity_id: 'cover.no_battery',
    unique_id: 'zha-cover2',
    config_entry_id: 'zha',
    platform: 'zha',
    device_id: 'dev2',
  },
];

describe('findBatterySensor', () => {
  it('finds the battery sensor on the cover device', () => {
    expect(findBatterySensor(REG, 'cover.family_door_shades')).toBe(
      'sensor.family_room_door_shades_battery',
    );
  });
  it('returns null when the device has no battery sensor', () => {
    expect(findBatterySensor(REG, 'cover.no_battery')).toBeNull();
  });
  it('returns null for unknown covers or missing registry', () => {
    expect(findBatterySensor(REG, 'cover.nope')).toBeNull();
    expect(findBatterySensor(null, 'cover.family_door_shades')).toBeNull();
    expect(findBatterySensor(REG, undefined)).toBeNull();
  });
});

describe('batteryReading', () => {
  const hass = {
    states: {
      'sensor.b': { state: '24.0', attributes: {} },
      'sensor.bad': { state: 'unavailable', attributes: {} },
    },
  } as unknown as HomeAssistant;
  it('parses numeric levels as available', () => {
    expect(batteryReading(hass, 'sensor.b')).toEqual({ level: 24, available: true });
  });
  it('marks unavailable/missing sensors stale rather than absent', () => {
    // A dead battery reports as unavailable - it must be distinguishable
    // from "this shade has no battery sensor" (regression: 5% shade died
    // offline and disappeared from view, 2026-07-02).
    expect(batteryReading(hass, 'sensor.bad')).toEqual({ level: null, available: false });
    expect(batteryReading(hass, 'sensor.missing')).toEqual({ level: null, available: false });
  });
  it('returns null only when there is no sensor at all', () => {
    expect(batteryReading(hass, null)).toBeNull();
  });
});
