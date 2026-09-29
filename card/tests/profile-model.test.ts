/// <reference types="node" />
// What the house, floor and room sheets read (lib/profile-model.ts) from the
// live house on the v1.20 surface, and the calls they make.
import { describe, expect, it } from 'vitest';

import { discoverHouse } from '../src/lib/house-model';
import {
  fetchStoredProfiles,
  parseStoredProfiles,
  planHouseSetting,
  planSetProfile,
  settingRows,
  windowExceptions,
  windowProvenance,
  type ProfileScope,
  type SettingRow,
  type StoredProfiles,
} from '../src/lib/profile-model';
import {
  HUB_ENTRY,
  HUB_MODE_SELECT,
  HUB_SETTINGS,
  LIVE_LAYERS,
  houseFixture,
  layeredHouse,
  type HouseTestHass,
} from './fixtures/house-hass';

const UP = 'sensor.upstairs_indoor_temperature';
const OFFICE: ProfileScope = { level: 'area', id: 'office', name: 'Office' };
const MASTER: ProfileScope = { level: 'area', id: 'master_bedroom', name: 'Master' };
const UPSTAIRS: ProfileScope = { level: 'floor', id: 'upstairs', name: 'Upstairs' };
const HOUSE: ProfileScope = { level: 'house', id: null, name: '' };

const STORED: StoredProfiles = parseStoredProfiles({
  house: LIVE_LAYERS.house,
  floors: LIVE_LAYERS.floors,
  areas: LIVE_LAYERS.areas,
})!;

function setup(opts: { stored?: boolean } = {}) {
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
  it('has the everyday settings, valued by the house device', () => {
    const { rows } = setup();
    const r = rows(HOUSE, null);
    expect(Object.keys(r)).toEqual([
      'climate_on',
      'temp_low',
      'temp_high',
      'manual_override_duration',
      'eye_height',
      'occupied_distance',
    ]);
    expect(Object.values(r).map((x) => x.value)).toEqual([true, 72, 75, 120, 1.2, 2]);
    expect(r.temp_low.exceptions).toEqual([]);
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
    expect(planHouseSetting({ ...model, hubSettings: {} }, 'eye_height', 1.1)).toEqual([
      {
        domain: 'adaptive_cover',
        service: 'set_profile',
        data: { scope: 'house', eye_height: 1.1 },
      },
    ]);
  });
});

describe('fetchStoredProfiles', () => {
  it('reads the house entry’s diagnostics', async () => {
    const { hass } = setup();
    const stored = await fetchStoredProfiles(hass, HUB_MODE_SELECT);
    expect(hass.callWS).toHaveBeenCalledWith({
      type: 'config/entity_registry/get',
      entity_id: HUB_MODE_SELECT,
    });
    expect(hass.callApi).toHaveBeenCalledWith(
      'GET',
      `diagnostics/config_entry/${HUB_ENTRY.entry_id}`,
    );
    expect(stored).toEqual(STORED);
  });

  it('is null for a non-admin (no request) or when the read fails', async () => {
    const fx = houseFixture();
    const viewer = layeredHouse(fx, undefined, { admin: false });
    expect(await fetchStoredProfiles(viewer, HUB_MODE_SELECT)).toBeNull();
    expect(viewer.callApi).not.toHaveBeenCalled();
    const failing: HouseTestHass = layeredHouse(fx, undefined, { stored: false });
    expect(await fetchStoredProfiles(failing, HUB_MODE_SELECT)).toBeNull();
    expect(await fetchStoredProfiles(failing, undefined)).toBeNull();
  });

  it('is null before the house is lifted', () => {
    expect(parseStoredProfiles({ temperature_unit: '°F' })).toBeNull();
    expect(parseStoredProfiles(null)).toBeNull();
  });
});
