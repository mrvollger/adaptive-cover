/// <reference types="node" />
// The card's table of recurring settings (lib/profile-settings.ts) against
// the integration's option spec, plus the value helpers the sheets use.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  PROFILE_SETTINGS,
  SETTINGS_BY_KEY,
  durationMinutes,
  formatValue,
  minutesDuration,
  normalizeValue,
  settingLabel,
  settingsAt,
  storedValue,
  temperatureShape,
} from '../src/lib/profile-settings';
import { t } from '../src/lib/i18n';
import type { HomeAssistant } from 'custom-card-helpers';

const PKG = resolve(import.meta.dirname, '../../custom_components/adaptive_cover');
const read = (rel: string) => readFileSync(resolve(PKG, rel), 'utf8');

const LEVELS: Record<string, string> = {
  H: 'house',
  F: 'floor',
  A: 'area',
  W: 'window',
  'Level.HOUSE': 'house',
  'Level.FLOOR': 'floor',
  'Level.AREA': 'area',
  'Level.WINDOW': 'window',
};

interface SpecRow {
  key: string;
  levels: Set<string>;
}

/** Every recurring Opt of settings/spec.py OPTS and settings/shadow.py
 *  TOGGLE_OPTS: its key and the levels that may store it. */
function recurringSpec(): SpecRow[] {
  const consts = Object.fromEntries(
    [...read('const.py').matchAll(/^(CONF_\w+)\s*=\s*"([^"]+)"/gm)].map((m) => [m[1], m[2]]),
  );
  const text = read('settings/spec.py') + read('settings/shadow.py');
  const re =
    /Opt\(\s*(CONF_\w+),\s*Kind\.\w+,\s*Group\.\w+,\s*(?:REC|Scope\.RECURRING),\s*([\w.]+)(?:,\s*\(([^)]*)\))?/g;
  return [...text.matchAll(re)].map((m) => {
    const over = (m[3] ?? '')
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    const key = consts[m[1]];
    expect(key, m[1]).toBeTruthy();
    return { key, levels: new Set([m[2], ...over].map((l) => LEVELS[l])) };
  });
}

describe('the settings table follows the option spec', () => {
  const spec = recurringSpec();

  it('finds the recurring settings in spec.py and shadow.py', () => {
    expect(spec.length).toBeGreaterThan(35);
    expect(spec.find((r) => r.key === 'climate_on')?.levels).toEqual(new Set(['house', 'area']));
    expect(spec.find((r) => r.key === 'temp_low')?.levels).toEqual(
      new Set(['house', 'floor', 'area']),
    );
  });

  it('lists every recurring setting, at the spec levels', () => {
    for (const row of spec) {
      const mine = SETTINGS_BY_KEY.get(row.key);
      expect(mine, `${row.key} is missing from PROFILE_SETTINGS`).toBeTruthy();
      const levels = new Set([...row.levels].filter((l) => l !== 'window'));
      expect(new Set(mine!.levels), row.key).toEqual(levels);
      expect(mine!.window, `${row.key} window override`).toBe(row.levels.has('window'));
    }
  });

  it('has no setting the spec does not know as recurring', () => {
    const known = new Set(spec.map((r) => r.key));
    for (const s of PROFILE_SETTINGS) expect(known.has(s.key), s.key).toBe(true);
  });

  it('marks the settings the house device has an entity for (house_settings.py)', () => {
    const source = read('house_settings.py');
    const switches = /HOUSE_SWITCHES[^=]*=\s*\(([^)]*)\)/.exec(source)![1];
    const numbers = [...source.matchAll(/HouseNumberSpec\((CONF_\w+),/g)].map((m) => m[1]);
    const times = [
      .../HOUSE_TIMES[^=]*=\s*\{([^}]*)\}/.exec(source)![1].matchAll(/(CONF_\w+):/g),
    ].map((m) => m[1]);
    expect(times).toHaveLength(3);
    const consts = Object.fromEntries(
      [...read('const.py').matchAll(/^(CONF_\w+)\s*=\s*"([^"]+)"/gm)].map((m) => [m[1], m[2]]),
    );
    const hubSwitches = switches
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
      .map((c) => consts[c]);
    const hubNumbers = numbers.map((c) => consts[c]);
    expect(
      PROFILE_SETTINGS.filter((s) => s.hub === 'switch')
        .map((s) => s.key)
        .sort(),
    ).toEqual([...hubSwitches].sort());
    expect(
      PROFILE_SETTINGS.filter((s) => s.hub === 'number')
        .map((s) => s.key)
        .sort(),
    ).toEqual([...hubNumbers].sort());
    expect(
      PROFILE_SETTINGS.filter((s) => s.hub === 'time')
        .map((s) => s.key)
        .sort(),
    ).toEqual(times.map((c) => consts[c]).sort());
  });

  it('a list setting offers the spec’s weather conditions', () => {
    const block = /WEATHER_CONDITIONS: Final = \(([^)]*)\)/.exec(read('settings/spec.py'))![1];
    const conditions = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect(SETTINGS_BY_KEY.get('weather_state')!.options).toEqual(conditions);
    for (const c of conditions) expect(t(`settings.weather.${c}`), c).not.toMatch(/^settings\./);
  });

  it('every recurring key has a label', () => {
    for (const row of spec) {
      const key = `settings.label.${row.key}`;
      expect(t(key), row.key).not.toBe(key);
      expect(settingLabel(row.key)).toBe(t(key));
    }
  });
});

describe('settingsAt', () => {
  it('a floor sheet has the thresholds and the indoor sensor', () => {
    expect(settingsAt('floor').map((s) => s.key)).toEqual(['temp_low', 'temp_high', 'temp_entity']);
  });

  it('a room sheet has every room setting, grouped by section', () => {
    const keys = settingsAt('area').map((s) => s.key);
    expect(keys).toHaveLength(23);
    expect(keys.slice(0, 3)).toEqual([
      'manual_override_duration',
      'manual_override_reset',
      'manual_detection',
    ]);
    expect(keys).not.toContain('use_lux');
    expect(keys).toContain('temp_entity');
  });

  it('the house sheet has every house setting, rare sections last', () => {
    const house = settingsAt('house');
    expect(house).toHaveLength(PROFILE_SETTINGS.length - 1);
    expect(house.map((s) => s.key)).not.toContain('temp_entity');
    expect(house.slice(-8).map((s) => s.section)).toEqual(Array(8).fill('sensors'));
    // One Climate switch (house 3.2) leads Climate; climate_mode is gone.
    const climate = house.filter((s) => s.section === 'climate').map((s) => s.key);
    expect(climate[0]).toBe('climate_on');
    expect(SETTINGS_BY_KEY.has('climate_mode')).toBe(false);
    expect(SETTINGS_BY_KEY.has('ignore_climate')).toBe(false);
  });
});

describe('values', () => {
  const s = (key: string) => SETTINGS_BY_KEY.get(key)!;
  const hass = {
    config: { unit_system: { temperature: '°F' } },
    states: { 'sensor.upstairs_indoor_temperature': { attributes: { friendly_name: 'Upstairs' } } },
  } as unknown as HomeAssistant;

  it('durations are minutes in the card and {hours, minutes, seconds} when stored', () => {
    expect(durationMinutes({ hours: 2, minutes: 0, seconds: 0 })).toBe(120);
    expect(durationMinutes({ hours: 1, minutes: 30 })).toBe(90);
    expect(minutesDuration(90)).toEqual({ hours: 1, minutes: 30, seconds: 0 });
    expect(storedValue(s('manual_override_duration'), 135)).toEqual({
      hours: 2,
      minutes: 15,
      seconds: 0,
    });
    expect(normalizeValue(s('manual_override_duration'), '120.0')).toBe(120);
  });

  it('times are HH:MM:SS; booleans read switch states', () => {
    expect(normalizeValue(s('start_time'), '7:30')).toBe('07:30:00');
    expect(storedValue(s('start_time'), '07:30')).toBe('07:30:00');
    expect(normalizeValue(s('climate_on'), 'on')).toBe(true);
    expect(normalizeValue(s('climate_on'), 'unknown')).toBeNull();
    expect(normalizeValue(s('temp_low'), '72.0')).toBe(72);
  });

  it('formats values for people', () => {
    expect(formatValue(hass, s('temp_low'), 72)).toBe('72 °F');
    expect(formatValue(hass, s('manual_override_duration'), 120)).toBe('2 h');
    expect(formatValue(hass, s('manual_override_duration'), 90)).toBe('1 h 30 min');
    expect(formatValue(hass, s('sunrise_offset'), 45)).toBe('45 min after sunrise');
    expect(formatValue(hass, s('sunset_offset'), -30)).toBe('30 min before sunset');
    expect(formatValue(hass, s('sunset_offset'), 0)).toBe('At sunset');
    expect(formatValue(hass, s('default_percentage'), 97)).toBe('97%');
    expect(formatValue(hass, s('eye_height'), 1.2)).toBe('1.2 m');
    expect(formatValue(hass, s('start_time'), '07:30:00')).toBe('07:30');
    expect(formatValue(hass, s('start_time'), '00:00:00')).toBe('Midnight');
    expect(formatValue(hass, s('climate_on'), false)).toBe('Off');
    expect(formatValue(hass, s('temp_entity'), 'sensor.upstairs_indoor_temperature')).toBe(
      'Upstairs',
    );
    expect(formatValue(hass, s('privacy_position'), null)).toBe('Not set');
    expect(formatValue(hass, s('quiet_start'), null)).toBe('None');
    expect(formatValue(hass, s('weather_state'), ['sunny', 'partlycloudy'])).toBe(
      'Sunny, Partly cloudy',
    );
    expect(formatValue(hass, s('lux_threshold'), 1000)).toBe('1000 lx');
  });

  it('threshold ranges follow HA’s unit', () => {
    expect(temperatureShape('temp_low', '°F')).toEqual({ min: 40, max: 90, step: 0.5 });
    expect(temperatureShape('temp_high', '°C')).toEqual({ min: 10, max: 40, step: 0.5 });
    expect(temperatureShape('temp_hysteresis', '°F')).toEqual({ min: 0, max: 5, step: 0.1 });
    expect(temperatureShape('temp_hysteresis', '°C')).toEqual({ min: 0, max: 3, step: 0.5 });
  });
});
