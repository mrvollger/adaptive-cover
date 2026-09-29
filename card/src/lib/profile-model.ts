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
import { getCachedRegistry } from './registry-store';

/*
 * What the house, floor and room sheets show for each setting, and the
 * service calls that change it.
 *
 * Reading (best source first):
 *
 * 1. The stored profiles: the house entry's `house`, `floors` and `areas`
 *    options. The integration has no read service for them yet; an admin
 *    card reads them from the house entry's diagnostics
 *    (`fetchStoredProfiles`). Exact for every setting.
 * 2. The house device's entities: the house value of the everyday
 *    settings (Climate, thresholds, override duration, ...).
 * 3. Provenance-aware reading of the windows. Each window's Position sensor
 *    has `provenance` = {option: "area" | "floor" | "window" | "legacy"} for
 *    every value that does not come from the house (or the spec default).
 *    So a room stores its own value for an option when one of its windows
 *    gets it from "area"; a window without an entry gets it from the house.
 *    A few resolved values are also attributes (`default`,
 *    `sunset_default`, `sunset_offset`), so for those the value is known too.
 *
 * Writing: `adaptive_cover.set_profile` with scope area or floor and the id
 * (null removes the value: the room or floor uses the house's again); the
 * house sheet uses the house device's switch and number entities.
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

/** The layered settings the house entry stores (hub options). */
export interface StoredProfiles {
  house: Record<string, unknown>;
  floors: Record<string, Record<string, unknown>>;
  areas: Record<string, Record<string, unknown>>;
}

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

/** The window's resolved value of `setting`, when its Position sensor shows it. */
function windowValue(hass: HomeAssistant, w: HouseWindow, setting: ProfileSetting): unknown {
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

/** The stored profiles in a house entry's options, or null (not lifted). */
export function parseStoredProfiles(options: unknown): StoredProfiles | null {
  if (!options || typeof options !== 'object') return null;
  const o = options as Record<string, unknown>;
  const obj = (v: unknown): Record<string, unknown> =>
    v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
  if (!o.house || typeof o.house !== 'object') return null;
  const nested = (v: unknown) =>
    Object.fromEntries(Object.entries(obj(v)).map(([k, p]) => [k, obj(p)]));
  return { house: obj(o.house), floors: nested(o.floors), areas: nested(o.areas) };
}

async function hubEntryId(hass: HomeAssistant, entityId: string): Promise<string | null> {
  const cached = getCachedRegistry()?.find((r) => r.entity_id === entityId)?.config_entry_id;
  if (cached) return cached;
  const row = await hass.callWS<{ config_entry_id?: string | null } | null>({
    type: 'config/entity_registry/get',
    entity_id: entityId,
  });
  return row?.config_entry_id ?? null;
}

/**
 * The house entry's stored profiles, read from its diagnostics (admins
 * only), or null when they cannot be read. A stopgap until the integration
 * offers a read path; the sheets work without it (provenance-aware reading).
 */
export async function fetchStoredProfiles(
  hass: HomeAssistant,
  hubEntityId: string | undefined,
): Promise<StoredProfiles | null> {
  if (!hubEntityId) return null;
  const user = (hass as { user?: { is_admin?: boolean } }).user;
  if (user && user.is_admin === false) return null;
  try {
    const entryId = await hubEntryId(hass, hubEntityId);
    if (!entryId) return null;
    const resp = await hass.callApi<{ data?: { config_options?: unknown } }>(
      'GET',
      `diagnostics/config_entry/${encodeURIComponent(entryId)}`,
    );
    return parseStoredProfiles(resp?.data?.config_options);
  } catch {
    return null;
  }
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
      const v = windowValue(this.hass, i.w, setting);
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
      const v = windowValue(this.hass, i.w, setting);
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
        value: windowValue(this.hass, i.w, setting),
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
 * store (the house sheet: the everyday settings that have a house entity).
 * `overlay` holds this sheet's own writes, which win over what the house
 * reports until the sheet closes.
 */
export function settingRows(
  hass: HomeAssistant,
  model: HouseModel,
  scope: ProfileScope,
  stored: StoredProfiles | null,
  overlay: ProfileOverlay = {},
): SettingRow[] {
  const r = new Reader(hass, model, stored);
  const settings = settingsAt(scope.level).filter(
    (s) => scope.level !== 'house' || !!model.hubSettings?.[s.key],
  );
  return settings.map((setting) => {
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

/** Change a house setting: its entity on the house device (switch or
 *  number; durations in minutes), else `set_profile` for the house. */
export function planHouseSetting(model: HouseModel, key: string, value: unknown): ServiceCall[] {
  const id = model.hubSettings?.[key];
  const setting = SETTINGS_BY_KEY.get(key);
  if (!id || !setting || value === null) {
    return [planSetProfile({ level: 'house', id: null, name: '' }, key, value)];
  }
  if (setting.kind === 'bool') {
    return [
      { domain: 'switch', service: value ? 'turn_on' : 'turn_off', data: { entity_id: [id] } },
    ];
  }
  return [{ domain: 'number', service: 'set_value', data: { entity_id: [id], value } }];
}
