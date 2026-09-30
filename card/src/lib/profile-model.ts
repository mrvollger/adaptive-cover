import type { HomeAssistant } from 'custom-card-helpers';

import { INTEGRATION_DOMAIN } from '../const';
import type { CoverPositionAttributes } from '../types';
import type { ServiceCall } from './house-actions';
import type { HouseModel, HouseWindow } from './house-model';
import {
  SETTINGS_BY_KEY,
  normalizeValue,
  settingsAt,
  storedValue,
  type ProfileLevel,
  type ProfileSetting,
} from './profile-settings';

/*
 * What the house, floor and room sheets show for each setting, and the
 * service calls that change it.
 *
 * Reading (best source first):
 *
 * 1. The house device's entities: the live house value of the settings
 *    they show (Climate, thresholds, override duration, times, ...).
 * 2. `adaptive_cover.get_profile` (response only, any user): with no scope
 *    every stored profile (the house's values, each floor's and room's);
 *    with `scope: window` a window's resolved settings, for the values of
 *    its own exceptions. A house that is not lifted yet answers with a
 *    validation error: the sheets then say the house settings are not
 *    available yet.
 * 3. Provenance-aware reading of the windows, for an integration without
 *    get_profile. Each window's Position sensor has `provenance` = {option:
 *    "area" | "floor" | "window" | "legacy"} for every value that does not
 *    come from the house (or the spec default). So a room stores its own
 *    value for an option when one of its windows gets it from "area"; a
 *    window without an entry gets it from the house. A few resolved values
 *    are attributes (`default`, `sunset_default`, `sunset_offset`).
 *
 * Writing: `adaptive_cover.set_profile` with scope area or floor and the id
 * (null removes the value: the room or floor uses the house's again). The
 * house sheet uses the house device's switch, number and time entities, and
 * `set_profile` for the house for every other house setting.
 */

/** Where a window's value comes from (the Position `provenance` attribute). */
export type ProvenanceSource = 'legacy' | 'window' | 'area' | 'floor';

export interface ProfileScope {
  level: ProfileLevel;
  /** Floor or area id; null for the house. */
  id: string | null;
  /** Display name of the room or floor ("" for the house). */
  name: string;
}

/** The layered settings the house stores (`get_profile` with no scope),
 *  plus the resolved settings of the windows read so far. */
export interface StoredProfiles {
  house: Record<string, unknown>;
  floors: Record<string, Record<string, unknown>>;
  areas: Record<string, Record<string, unknown>>;
  /** Window key → its resolved settings (`get_profile` scope window). */
  windows?: Record<string, Record<string, unknown>>;
}

/** What reading the stored profiles gave. */
export type ProfilesRead =
  | { status: 'ok'; stored: StoredProfiles }
  /** The house has no layered settings yet (get_profile says so). */
  | { status: 'not_lifted' }
  /** No get_profile (an older integration) or another failure: the sheets
   *  read the windows' provenance instead. */
  | { status: 'unavailable' };

/** This sheet's own writes since it opened: key → card value (null: removed). */
export type ProfileOverlay = Record<string, unknown>;

export interface SettingException {
  level: 'floor' | 'area' | 'window';
  /** Floor id, area id or window key. */
  id: string;
  name: string;
  /** Its value (card form), undefined when unknown. */
  value: unknown;
  /** A window value kept from before the house settings ("legacy"). */
  legacy?: boolean;
}

export interface SettingRow {
  setting: ProfileSetting;
  /** This scope stores its own value (always true for the house); null when
   *  the card cannot tell. */
  own: boolean | null;
  /** The scope's own value (card form), undefined when unknown. */
  value: unknown;
  /** What applies here without an own value: the floor's (for a room whose
   *  floor sets it) or the house's. Null for the house. */
  inherited: { level: 'house' | 'floor'; name: string | null; value: unknown } | null;
  /** The house value (card form), undefined when unknown. */
  houseValue: unknown;
  /** Narrower levels inside this scope with their own value. */
  exceptions: SettingException[];
}

export interface WindowExceptions {
  window: HouseWindow;
  settings: Array<{ key: string; legacy: boolean }>;
}

const SOURCES = new Set<string>(['legacy', 'window', 'area', 'floor']);

function attrs(hass: HomeAssistant, w: HouseWindow): CoverPositionAttributes | undefined {
  const id = w.entities.position;
  return id ? (hass.states[id]?.attributes as CoverPositionAttributes | undefined) : undefined;
}

/** A window's `provenance` attribute, or null before the house is lifted. */
export function windowProvenance(
  hass: HomeAssistant,
  w: HouseWindow,
): Record<string, ProvenanceSource> | null {
  const raw = (attrs(hass, w) as { provenance?: unknown } | undefined)?.provenance;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const out: Record<string, ProvenanceSource> = {};
  for (const [key, source] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof source === 'string' && SOURCES.has(source)) {
      out[key] = source as ProvenanceSource;
    }
  }
  return out;
}

/** The window's resolved value of `setting`: from `get_profile` when read,
 *  else when its Position sensor shows it. */
function windowValue(
  hass: HomeAssistant,
  w: HouseWindow,
  setting: ProfileSetting,
  stored?: StoredProfiles | null,
): unknown {
  const resolved = stored?.windows?.[w.key];
  if (resolved && has(resolved, setting.key)) {
    const v = normalizeValue(setting, resolved[setting.key]);
    return v === null ? undefined : v;
  }
  if (!setting.attr) return undefined;
  const a = attrs(hass, w) as Record<string, unknown> | undefined;
  if (!a || !(setting.attr in a)) return undefined;
  const v = normalizeValue(setting, a[setting.attr]);
  return v === null ? undefined : v;
}

/** The house device's value of `setting`, undefined when it has no entity. */
function hubValue(hass: HomeAssistant, model: HouseModel, setting: ProfileSetting): unknown {
  const id = model.hubSettings?.[setting.key];
  const st = id ? hass.states[id] : undefined;
  if (!st || st.state === 'unavailable' || st.state === 'unknown') return undefined;
  const v = normalizeValue(setting, st.state);
  return v === null ? undefined : v;
}

/** Call `adaptive_cover.get_profile` and return its response. */
async function getProfile(hass: HomeAssistant, data: Record<string, unknown>): Promise<unknown> {
  const result = await hass.callWS<{ response?: unknown }>({
    type: 'call_service',
    domain: INTEGRATION_DOMAIN,
    service: 'get_profile',
    service_data: data,
    return_response: true,
  });
  return result?.response;
}

const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

/** The stored profiles in a `get_profile` response (no scope), or null. */
export function parseProfiles(response: unknown): StoredProfiles | null {
  const r = obj(response);
  const house = obj(r.house);
  if (!r.house || !house.values) return null;
  const nested = (v: unknown) =>
    Object.fromEntries(Object.entries(obj(v)).map(([k, p]) => [k, obj(p)]));
  return { house: obj(house.values), floors: nested(r.floors), areas: nested(r.areas) };
}

/** Read every stored profile (see `ProfilesRead`). */
export async function readProfiles(hass: HomeAssistant): Promise<ProfilesRead> {
  try {
    const stored = parseProfiles(await getProfile(hass, {}));
    return stored ? { status: 'ok', stored } : { status: 'unavailable' };
  } catch (err) {
    // Without a scope the only validation error is a house not lifted yet.
    const code = (err as { code?: unknown } | null)?.code;
    return code === 'service_validation_error'
      ? { status: 'not_lifted' }
      : { status: 'unavailable' };
  }
}

/** The resolved settings of `keys` (window keys), by window; a window that
 *  cannot be read is left out. */
export async function readWindowSettings(
  hass: HomeAssistant,
  keys: string[],
): Promise<Record<string, Record<string, unknown>>> {
  const out: Record<string, Record<string, unknown>> = {};
  await Promise.all(
    keys.map(async (key) => {
      try {
        const settings = obj(obj(await getProfile(hass, { scope: 'window', id: key })).settings);
        if (Object.keys(settings).length > 0) out[key] = settings;
      } catch {
        /* keep what provenance and the attributes give */
      }
    }),
  );
  return out;
}

/** Windows of `windows` with their own value (window or legacy) for one of
 *  `keys`: the ones whose resolved settings the sheet reads. */
export function windowsToRead(
  hass: HomeAssistant,
  windows: HouseWindow[],
  keys: Iterable<string>,
): string[] {
  const wanted = new Set(keys);
  return windows
    .filter((w) =>
      Object.entries(windowProvenance(hass, w) ?? {}).some(
        ([k, source]) => wanted.has(k) && (source === 'window' || source === 'legacy'),
      ),
    )
    .map((w) => w.key);
}

/**
 * Whether the integration stores house, floor and room settings
 * (`set_profile`, 1.20+). HA lists the services in `hass.services`; without
 * that list, the house device's setting entities tell.
 */
export function profilesSupported(hass: HomeAssistant, model: HouseModel): boolean {
  const services = (hass as { services?: Record<string, Record<string, unknown>> }).services;
  if (services) return !!services[INTEGRATION_DOMAIN]?.set_profile;
  return Object.values(model.hubSettings ?? {}).some((id) => !!id);
}

function has(obj: Record<string, unknown> | undefined, key: string): boolean {
  return !!obj && Object.prototype.hasOwnProperty.call(obj, key);
}

interface WindowInfo {
  w: HouseWindow;
  prov: Record<string, ProvenanceSource> | null;
}

class Reader {
  readonly infos: WindowInfo[];
  constructor(
    readonly hass: HomeAssistant,
    readonly model: HouseModel,
    readonly stored: StoredProfiles | null,
  ) {
    this.infos = model.windows.map((w) => ({ w, prov: windowProvenance(hass, w) }));
  }

  windowsIn(level: ProfileLevel, id: string | null): WindowInfo[] {
    if (level === 'house') return this.infos;
    return this.infos.filter((i) => (level === 'area' ? i.w.areaId : i.w.floorId) === id);
  }

  bucket(level: 'floor' | 'area', id: string): Record<string, unknown> | undefined {
    if (!this.stored) return undefined;
    return (level === 'floor' ? this.stored.floors : this.stored.areas)[id] ?? {};
  }

  /** A value some window of `infos` resolves from `source`, when shown. */
  valueFrom(infos: WindowInfo[], setting: ProfileSetting, source: ProvenanceSource): unknown {
    for (const i of infos) {
      if (i.prov?.[setting.key] !== source) continue;
      const v = windowValue(this.hass, i.w, setting, this.stored);
      if (v !== undefined) return v;
    }
    return undefined;
  }

  houseValue(setting: ProfileSetting): unknown {
    if (!setting.levels.includes('house')) return undefined;
    const hub = hubValue(this.hass, this.model, setting);
    if (hub !== undefined) return hub;
    if (this.stored && has(this.stored.house, setting.key)) {
      return normalizeValue(setting, this.stored.house[setting.key]);
    }
    // A window without a provenance entry resolves the house value.
    for (const i of this.infos) {
      if (!i.prov || setting.key in i.prov) continue;
      const v = windowValue(this.hass, i.w, setting, this.stored);
      if (v !== undefined) return v;
    }
    return undefined;
  }

  /** Whether a floor or room stores `setting`, and its value. */
  own(
    level: 'floor' | 'area',
    id: string,
    setting: ProfileSetting,
  ): { own: boolean | null; value: unknown } {
    const bucket = this.bucket(level, id);
    if (bucket) {
      return has(bucket, setting.key)
        ? { own: true, value: normalizeValue(setting, bucket[setting.key]) }
        : { own: false, value: undefined };
    }
    const infos = this.windowsIn(level, id).filter((i) => i.prov !== null);
    if (infos.some((i) => i.prov![setting.key] === level)) {
      return { own: true, value: this.valueFrom(infos, setting, level) };
    }
    // A window that inherits from a wider level shows the level does not set it.
    const wider = (s: ProvenanceSource | undefined) =>
      s === undefined || (level === 'area' && s === 'floor');
    if (infos.some((i) => wider(i.prov![setting.key]))) return { own: false, value: undefined };
    return { own: null, value: undefined };
  }

  exceptions(scope: ProfileScope, setting: ProfileSetting): SettingException[] {
    const out: SettingException[] = [];
    const inScope = this.windowsIn(scope.level, scope.id);
    if (scope.level === 'house' && setting.levels.includes('floor')) {
      for (const floor of this.model.floors) {
        if (floor.id === null) continue;
        const o = this.own('floor', floor.id, setting);
        if (o.own) out.push({ level: 'floor', id: floor.id, name: floor.name, value: o.value });
      }
    }
    if (scope.level !== 'area' && setting.levels.includes('area')) {
      for (const floor of this.model.floors) {
        if (scope.level === 'floor' && floor.id !== scope.id) continue;
        for (const room of floor.rooms) {
          if (room.id === null) continue;
          const o = this.own('area', room.id, setting);
          if (o.own) out.push({ level: 'area', id: room.id, name: room.name, value: o.value });
        }
      }
    }
    for (const i of inScope) {
      const source = i.prov?.[setting.key];
      if (source !== 'window' && source !== 'legacy') continue;
      out.push({
        level: 'window',
        id: i.w.key,
        name: i.w.deviceName,
        value: windowValue(this.hass, i.w, setting, this.stored),
        legacy: source === 'legacy',
      });
    }
    return out;
  }
}

/** The name and id of the floor a room is on (from its windows). */
function roomFloor(model: HouseModel, areaId: string): { id: string; name: string } | null {
  for (const floor of model.floors) {
    if (floor.id !== null && floor.rooms.some((r) => r.id === areaId)) {
      return { id: floor.id, name: floor.name };
    }
  }
  return null;
}

/**
 * The rows of a settings sheet for `scope`: one per setting the scope may
 * store. `overlay` holds this sheet's own writes, which win over what the
 * house reports until the sheet closes.
 */
export function settingRows(
  hass: HomeAssistant,
  model: HouseModel,
  scope: ProfileScope,
  stored: StoredProfiles | null,
  overlay: ProfileOverlay = {},
): SettingRow[] {
  const r = new Reader(hass, model, stored);
  return settingsAt(scope.level).map((setting) => {
    const key = setting.key;
    const houseValue = r.houseValue(setting);
    const exceptions = r.exceptions(scope, setting);
    if (scope.level === 'house') {
      const value = has(overlay, key) ? overlay[key] : houseValue;
      return { setting, own: true, value, inherited: null, houseValue: value, exceptions };
    }
    const id = scope.id!;
    let { own, value } = r.own(scope.level, id, setting);
    if (has(overlay, key)) {
      own = overlay[key] !== null;
      value = own ? overlay[key] : undefined;
    }
    let inherited: SettingRow['inherited'] = { level: 'house', name: null, value: houseValue };
    if (scope.level === 'area' && setting.levels.includes('floor')) {
      const floor = roomFloor(model, id);
      const fromFloor = floor ? r.own('floor', floor.id, setting) : null;
      if (floor && (fromFloor?.own || !setting.levels.includes('house'))) {
        inherited = { level: 'floor', name: floor.name, value: fromFloor?.value };
      }
    }
    return { setting, own, value, inherited, houseValue, exceptions };
  });
}

/** Windows in `windows` with their own value for some setting (provenance
 *  "window", or "legacy": kept from before the house settings). */
export function windowExceptions(hass: HomeAssistant, windows: HouseWindow[]): WindowExceptions[] {
  const out: WindowExceptions[] = [];
  for (const w of windows) {
    const prov = windowProvenance(hass, w);
    if (!prov) continue;
    const settings = Object.entries(prov)
      .filter(([, s]) => s === 'window' || s === 'legacy')
      .map(([key, s]) => ({ key, legacy: s === 'legacy' }))
      .sort((a, b) => a.key.localeCompare(b.key));
    if (settings.length > 0) out.push({ window: w, settings });
  }
  return out;
}

// ---------------------------------------------------------- service calls

/**
 * `adaptive_cover.set_profile` for one setting of a room, floor or the
 * house. `value` is the card form (durations in minutes, times "HH:MM");
 * null removes a room's or floor's value.
 */
export function planSetProfile(scope: ProfileScope, key: string, value: unknown): ServiceCall {
  const setting = SETTINGS_BY_KEY.get(key);
  const data: Record<string, unknown> = { scope: scope.level };
  if (scope.level !== 'house') data.id = scope.id;
  data[key] = setting ? storedValue(setting, value) : value;
  return { domain: INTEGRATION_DOMAIN, service: 'set_profile', data };
}

/** Change a house setting: its entity on the house device (switch, number
 *  or time; durations in minutes), else `set_profile` for the house (also
 *  to clear a value, which no entity can). */
export function planHouseSetting(model: HouseModel, key: string, value: unknown): ServiceCall[] {
  const id = model.hubSettings?.[key];
  const setting = SETTINGS_BY_KEY.get(key);
  if (!id || !setting?.hub || value === null) {
    return [planSetProfile({ level: 'house', id: null, name: '' }, key, value)];
  }
  if (setting.hub === 'switch') {
    return [
      { domain: 'switch', service: value ? 'turn_on' : 'turn_off', data: { entity_id: [id] } },
    ];
  }
  if (setting.hub === 'time') {
    const time = storedValue(setting, value);
    return [{ domain: 'time', service: 'set_value', data: { entity_id: [id], time } }];
  }
  return [{ domain: 'number', service: 'set_value', data: { entity_id: [id], value } }];
}
