/// <reference types="node" />
// What the house, floor and room sheets read (lib/profile-model.ts) from the
// live house on the v1.20 surface, and the calls they make.
import { describe, expect, it } from 'vitest';

import { discoverHouse } from '../src/lib/house-model';
import {
  parseProfiles,
  planHouseSetting,
  planSetProfile,
  profilesSupported,
  readProfiles,
  readWindowSettings,
  settingRows,
  windowExceptions,
  windowProvenance,
  windowsToRead,
  type ProfileScope,
  type SettingRow,
  type StoredProfiles,
} from '../src/lib/profile-model';
import { settingsAt } from '../src/lib/profile-settings';
import {
  HUB_SETTINGS,
  LIVE_LAYERS,
  houseFixture,
  layeredHouse,
  type LayeredOptions,
} from './fixtures/house-hass';

const UP = 'sensor.upstairs_indoor_temperature';
const OFFICE: ProfileScope = { level: 'area', id: 'office', name: 'Office' };
const MASTER: ProfileScope = { level: 'area', id: 'master_bedroom', name: 'Master' };
const UPSTAIRS: ProfileScope = { level: 'floor', id: 'upstairs', name: 'Upstairs' };
const HOUSE: ProfileScope = { level: 'house', id: null, name: '' };

const STORED: StoredProfiles = parseProfiles({
  house: { values: LIVE_LAYERS.house, temperature_unit: '°F' },
  floors: LIVE_LAYERS.floors,
  areas: LIVE_LAYERS.areas,
})!;

function setup(opts: LayeredOptions = {}) {
  const fx = houseFixture();
  const hass = layeredHouse(fx, undefined, opts);
  const model = discoverHouse(hass, null);
  const rows = (scope: ProfileScope, stored: StoredProfiles | null = null, overlay = {}) =>
    Object.fromEntries(
      settingRows(hass, model, scope, stored, overlay).map((r) => [r.setting.key, r]),
    ) as Record<string, SettingRow>;
  return { fx, hass, model, rows };
}

const brief = (r: SettingRow) => ({ own: r.own, value: r.value, inherited: r.inherited });

describe('discovery on the v1.20 surface', () => {
  it('finds the house setting entities on the house device only', () => {
    const { model } = setup();
    expect(model.hubSettings).toEqual(HUB_SETTINGS);
    // The window numbers of the 1.13 snapshot share some translation keys.
    expect(Object.values(model.hubSettings).every((id) => id!.includes('adaptive_cover_all'))).toBe(
      true,
    );
  });

  it('reads the provenance attribute like the integration writes it', () => {
    const { hass, model } = setup();
    const byName = (n: string) => model.windows.find((w) => w.deviceName === n)!;
    expect(windowProvenance(hass, byName('Office north'))).toEqual({
      default_percentage: 'area',
      sunset_offset: 'area',
      sunrise_offset: 'area',
      start_time: 'area',
      temp_entity: 'floor',
    });
    expect(windowProvenance(hass, byName('Master door'))).toEqual({
      default_percentage: 'window',
      sunset_position: 'window',
      sunrise_offset: 'area',
      temp_entity: 'floor',
    });
    expect(windowProvenance(houseFixture().hass, byName('Master door'))).toBeNull();
  });
});

describe('a room sheet', () => {
  it('with the stored profiles: every room value is known', () => {
    const { rows } = setup();
    const r = rows(OFFICE, STORED);
    expect(brief(r.start_time)).toEqual({
      own: true,
      value: '07:30:00',
      inherited: { level: 'house', name: null, value: '00:00:00' },
    });
    expect(r.sunrise_offset.value).toBe(45);
    expect(r.default_percentage).toMatchObject({ own: true, value: 100, houseValue: 99 });
    expect(r.temp_low).toMatchObject({ own: false, houseValue: 72 });
    expect(r.temp_entity).toMatchObject({
      own: false,
      inherited: { level: 'floor', name: 'Upstairs', value: UP },
    });
    // Climate and the override duration come from the house device.
    expect(r.climate_on).toMatchObject({ own: false, houseValue: true });
    expect(r.manual_override_duration).toMatchObject({ own: false, houseValue: 120 });
  });

  it('without them: provenance says what the room sets; attributes give some values', () => {
    const { rows } = setup();
    const r = rows(OFFICE, null);
    expect(r.start_time).toMatchObject({ own: true, value: undefined });
    expect(r.default_percentage).toMatchObject({ own: true, value: 100, houseValue: 99 });
    expect(r.sunset_offset).toMatchObject({ own: true, value: 0, houseValue: 20 });
    expect(r.temp_low).toMatchObject({ own: false, houseValue: 72 });
    expect(r.return_sunset).toMatchObject({ own: false, houseValue: undefined });
    expect(r.temp_entity).toMatchObject({
      own: false,
      inherited: { level: 'floor', name: 'Upstairs', value: undefined },
    });
  });

  it('names the windows with their own value for each setting', () => {
    const { rows } = setup();
    const r = rows(MASTER, null);
    expect(r.sunrise_offset.own).toBe(true);
    expect(r.sunset_offset).toMatchObject({ own: false, houseValue: 20 });
    expect(r.sunset_offset.exceptions).toEqual([
      expect.objectContaining({ level: 'window', name: 'Master trap', value: 15, legacy: true }),
    ]);
    expect(r.default_percentage.exceptions).toEqual([
      expect.objectContaining({ level: 'window', name: 'Master door', value: 100, legacy: false }),
    ]);
  });

  it('lists the windows with their own values', () => {
    const { hass, model } = setup();
    const out = windowExceptions(
      hass,
      model.windows.filter((w) => w.areaId === 'master_bedroom'),
    ).map((e) => [e.window.deviceName, e.settings.map((s) => `${s.key}${s.legacy ? '*' : ''}`)]);
    expect(out).toEqual([
      ['Master door', ['default_percentage', 'sunset_position']],
      ['Master south', ['privacy_offset*', 'privacy_position*']],
      ['Master trap', ['sunrise_offset*', 'sunset_offset*']],
    ]);
  });

  it('this sheet’s own writes win (a reset shows the wider value again)', () => {
    const { rows } = setup();
    const r = rows(OFFICE, STORED, { start_time: null, temp_low: 70 });
    expect(r.start_time).toMatchObject({ own: false, value: undefined });
    expect(r.temp_low).toMatchObject({ own: true, value: 70 });
  });
});

describe('a floor sheet', () => {
  it('shows the floor’s sensor and the house thresholds', () => {
    const { rows } = setup();
    expect(Object.keys(rows(UPSTAIRS, STORED))).toEqual(['temp_low', 'temp_high', 'temp_entity']);
    expect(rows(UPSTAIRS, STORED).temp_entity).toMatchObject({ own: true, value: UP });
    expect(rows(UPSTAIRS, null).temp_entity).toMatchObject({ own: true, value: undefined });
    expect(rows(UPSTAIRS, null).temp_low).toMatchObject({
      own: false,
      inherited: { level: 'house', value: 72 },
    });
  });
});

describe('the house sheet', () => {
  it('has every house setting, valued by the house device, else the stored house', () => {
    const { rows } = setup();
    const r = rows(HOUSE, STORED);
    expect(Object.keys(r)).toEqual(settingsAt('house').map((s) => s.key));
    // House device entities (live), including the times.
    expect(r.climate_on.value).toBe(true);
    expect(r.temp_low.value).toBe(72);
    expect(r.manual_override_duration.value).toBe(120);
    expect(r.privacy_offset.value).toBe(30);
    expect(r.end_time.value).toBe('00:00:00');
    // No quiet hours: the time is unknown and the house stores none.
    expect(r.quiet_start.value).toBeNull();
    // Only in the stored house profile (set_profile for the house).
    expect(r.delta_position.value).toBe(1);
    expect(r.weather_state.value).toEqual([
      'sunny',
      'partlycloudy',
      'clear',
      'windy',
      'windy-variant',
    ]);
    expect(r.weather_entity.value).toBe('weather.forecast_home_2');
    expect(r.max_moves_hour.value).toBeNull();
    expect(r.temp_low.exceptions).toEqual([]);
  });

  it('without the stored house, only the device entities and attributes are known', () => {
    const { rows } = setup();
    const r = rows(HOUSE, null);
    expect(r.temp_low.value).toBe(72);
    expect(r.default_percentage.value).toBe(99);
    expect(r.delta_position.value).toBeUndefined();
  });

  it('shows the floors and rooms that set their own value', () => {
    const { rows } = setup();
    const stored: StoredProfiles = {
      ...STORED,
      floors: { ...STORED.floors, main: { temp_entity: 'x', temp_low: 71 } },
      areas: { ...STORED.areas, office: { ...STORED.areas.office, temp_low: 70 } },
    };
    expect(rows(HOUSE, stored).temp_low.exceptions).toEqual([
      { level: 'floor', id: 'main', name: 'Main', value: 71 },
      { level: 'area', id: 'office', name: 'Office', value: 70 },
    ]);
  });
});

describe('service calls', () => {
  it('set_profile for a room, a floor and a reset', () => {
    expect(planSetProfile(OFFICE, 'start_time', '07:45')).toEqual({
      domain: 'adaptive_cover',
      service: 'set_profile',
      data: { scope: 'area', id: 'office', start_time: '07:45:00' },
    });
    expect(planSetProfile(UPSTAIRS, 'temp_low', 70.5)).toEqual({
      domain: 'adaptive_cover',
      service: 'set_profile',
      data: { scope: 'floor', id: 'upstairs', temp_low: 70.5 },
    });
    expect(planSetProfile(OFFICE, 'manual_override_duration', 240).data).toEqual({
      scope: 'area',
      id: 'office',
      manual_override_duration: { hours: 4, minutes: 0, seconds: 0 },
    });
    expect(planSetProfile(OFFICE, 'sunrise_offset', null).data).toEqual({
      scope: 'area',
      id: 'office',
      sunrise_offset: null,
    });
  });

  it('the house: its switch or number, else set_profile for the house', () => {
    const { model } = setup();
    expect(planHouseSetting(model, 'climate_on', false)).toEqual([
      { domain: 'switch', service: 'turn_off', data: { entity_id: [HUB_SETTINGS.climate_on] } },
    ]);
    expect(planHouseSetting(model, 'manual_override_duration', 90)).toEqual([
      {
        domain: 'number',
        service: 'set_value',
        data: { entity_id: [HUB_SETTINGS.manual_override_duration], value: 90 },
      },
    ]);
    expect(planHouseSetting(model, 'end_time', '21:30')).toEqual([
      {
        domain: 'time',
        service: 'set_value',
        data: { entity_id: [HUB_SETTINGS.end_time], time: '21:30:00' },
      },
    ]);
    // No entity, or clearing a value: set_profile for the house.
    expect(planHouseSetting(model, 'delta_position', 2)).toEqual([
      {
        domain: 'adaptive_cover',
        service: 'set_profile',
        data: { scope: 'house', delta_position: 2 },
      },
    ]);
    expect(planHouseSetting(model, 'quiet_start', null)).toEqual([
      {
        domain: 'adaptive_cover',
        service: 'set_profile',
        data: { scope: 'house', quiet_start: null },
      },
    ]);
    expect(planHouseSetting({ ...model, hubSettings: {} }, 'eye_height', 1.1)).toEqual([
      {
        domain: 'adaptive_cover',
        service: 'set_profile',
        data: { scope: 'house', eye_height: 1.1 },
      },
    ]);
  });
});

describe('reading with get_profile', () => {
  const call = (data: Record<string, unknown>) => ({
    type: 'call_service',
    domain: 'adaptive_cover',
    service: 'get_profile',
    service_data: data,
    return_response: true,
  });

  it('reads every stored profile with one response-only call', async () => {
    const { hass } = setup();
    expect(await readProfiles(hass)).toEqual({ status: 'ok', stored: STORED });
    expect(hass.callWS).toHaveBeenCalledWith(call({}));
  });

  it('a house not lifted yet is not_lifted; no service falls back to provenance', async () => {
    expect(await readProfiles(setup({ profiles: 'not_lifted' }).hass)).toEqual({
      status: 'not_lifted',
    });
    expect(await readProfiles(setup({ profiles: 'missing' }).hass)).toEqual({
      status: 'unavailable',
    });
  });

  it('reads the windows that have their own values for the sheet’s settings', async () => {
    const { hass, model } = setup();
    const master = model.windows.filter((w) => w.areaId === 'master_bedroom');
    const keys = windowsToRead(hass, master, ['sunset_offset', 'privacy_offset']);
    const names = (ks: string[]) =>
      ks.map((k) => model.windows.find((w) => w.key === k)!.deviceName).sort();
    expect(names(keys)).toEqual(['Master south', 'Master trap']);
    const windows = await readWindowSettings(hass, keys);
    expect(hass.callWS).toHaveBeenCalledWith(call({ scope: 'window', id: keys[0] }));
    const trap = model.windows.find((w) => w.deviceName === 'Master trap')!;
    expect(windows[trap.key]).toMatchObject({ sunset_offset: 15, sunrise_offset: 0 });
    // Their values show on the exception chips.
    const r = settingRows(hass, model, MASTER, { ...STORED, windows }, {});
    const privacy = r.find((x) => x.setting.key === 'privacy_offset')!;
    expect(privacy.exceptions).toEqual([
      expect.objectContaining({ name: 'Master south', value: 30, legacy: true }),
    ]);
    expect(await readWindowSettings(setup({ profiles: 'missing' }).hass, keys)).toEqual({});
  });

  it('knows whether the integration stores profiles', () => {
    const { hass, model } = setup();
    expect(profilesSupported(hass, model)).toBe(true);
    const services = (set: boolean) =>
      ({
        ...hass,
        services: { adaptive_cover: set ? { set_profile: {}, hold: {} } : { hold: {} } },
      }) as unknown as typeof hass;
    expect(profilesSupported(services(true), model)).toBe(true);
    expect(profilesSupported(services(false), model)).toBe(false);
    const old = houseFixture();
    expect(profilesSupported(old.hass, discoverHouse(old.hass, null))).toBe(false);
  });

  it('is null for a response without the house', () => {
    expect(parseProfiles({ scope: 'house' })).toBeNull();
    expect(parseProfiles(null)).toBeNull();
  });
});
