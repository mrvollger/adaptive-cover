import type { HomeAssistant } from 'custom-card-helpers';

import { INTEGRATION_DOMAIN } from '../const';
import type { CoverPositionAttributes } from '../types';
import type { EntityRegistryEntry } from './entity-registry';

/*
 * Whole-house discovery for the house card and the dashboard strategy.
 *
 * Source of truth is the frontend's display registry (`hass.entities`), which
 * carries `platform`, `device_id`, `area_id`, `hidden` and `translation_key`
 * for every enabled entity. Every adaptive_cover row is classified by its
 * translation key (P1 entity surface). A window is one Position sensor; its
 * key is the sensor's `window_key` attribute. The window's other entities are
 * the rows on the same device.
 *
 * Fallback for an integration without translation keys or window attributes:
 * the full entity registry (websocket fetch). Its `unique_id` is
 * `{window_key}_{suffix}` for window rows and `adaptive_cover_hub_{suffix}`
 * for the house device, and never changes. The caller passes the registry in
 * only when `needsRegistry` says so.
 *
 * Discovery never filters on `config_entry_id`: once windows become subentries
 * of one house entry they all share it.
 *
 * Grouping: room = the Position sensor's own area, else the window device's
 * area, else the physical cover's area (entity, then its device). Floor = the
 * room's floor. Floors run top-down (highest level first); rooms and windows
 * sort by name. Windows without a room go in an "Unassigned" room.
 */

export type WindowMode = 'auto' | 'hold' | 'off';
export type GroupMode = WindowMode | 'mixed';

/** The per-window entities the house card reads or drives. */
export type WindowRole =
  | 'position'
  | 'mode'
  | 'returnButton'
  | 'manualOverride'
  | 'sunInFront'
  | 'controlMethod'
  | 'controlSwitch'
  | 'climateSwitch';

/** The house device's entities ("Adaptive Cover All"); the Climate switch is
 *  the house's `climate_on` setting (P5 flip). */
export type HubRole = 'cover' | 'modeSelect' | 'returnButton' | 'climateSwitch';

/** (domain, translation_key) of each window role. Mirrors
 *  custom_components/adaptive_cover/entity_surface.py WINDOW_SURFACE. */
const WINDOW_TRANSLATION_KEYS: Record<string, WindowRole> = {
  'sensor:target_position': 'position',
  'select:mode': 'mode',
  'button:return_to_auto': 'returnButton',
  'binary_sensor:manual_override': 'manualOverride',
  'binary_sensor:sun_motion': 'sunInFront',
  'sensor:control': 'controlMethod',
  'switch:control_toggle': 'controlSwitch',
  'switch:switch_mode': 'climateSwitch',
};

/** (domain, unique_id suffix) of each window role; the suffixes are frozen. */
const WINDOW_UNIQUE_ID_SUFFIXES: Record<string, WindowRole> = {
  'sensor:Cover Position': 'position',
  'select:mode_select': 'mode',
  'button:Reset Manual Override': 'returnButton',
  'binary_sensor:Manual Override': 'manualOverride',
  'binary_sensor:Sun Infront': 'sunInFront',
  'sensor:Control Method': 'controlMethod',
  'switch:Toggle Control': 'controlSwitch',
  'switch:Climate Mode': 'climateSwitch',
};

const ROLE_SUFFIX: Record<WindowRole, string> = Object.fromEntries(
  Object.entries(WINDOW_UNIQUE_ID_SUFFIXES).map(([k, role]) => [role, k.slice(k.indexOf(':') + 1)]),
) as Record<WindowRole, string>;

/** The house settings on the house device (P5 flip, `house_settings.py`):
 *  (domain, translation_key) → setting key. Their unique_id suffix is the
 *  same key. Window rows of older integrations had numbers with some of
 *  these translation keys, so a row counts only on the house device. */
const HUB_SETTING_KEYS: Record<string, string> = {
  'switch:climate_on': 'climate_on',
  'switch:manual_detection': 'manual_detection',
  'switch:use_outside_temp': 'use_outside_temp',
  'switch:use_lux': 'use_lux',
  'switch:use_irradiance': 'use_irradiance',
  'number:temp_low': 'temp_low',
  'number:temp_high': 'temp_high',
  'number:manual_override_duration': 'manual_override_duration',
  'number:eye_height': 'eye_height',
  'number:occupied_distance': 'occupied_distance',
  'number:privacy_offset': 'privacy_offset',
  'time:end_time': 'end_time',
  'time:quiet_start': 'quiet_start',
  'time:quiet_end': 'quiet_end',
};

/** (domain, translation_key) of the house device's roles. HUB_SURFACE. */
const HUB_TRANSLATION_KEYS: Record<string, HubRole> = {
  'select:house_mode': 'modeSelect',
  'button:return_all_to_auto': 'returnButton',
  'switch:climate_on': 'climateSwitch',
};

export const HUB_UNIQUE_ID_PREFIX = 'adaptive_cover_hub_';
const HUB_UNIQUE_ID_SUFFIXES: Record<string, HubRole> = {
  'cover:cover': 'cover',
  'select:house_mode': 'modeSelect',
  'button:reset_all': 'returnButton',
  'switch:climate_on': 'climateSwitch',
};

/** One row of the frontend display registry (`hass.entities`). */
export interface DisplayEntity {
  entity_id: string;
  platform?: string;
  device_id?: string | null;
  area_id?: string | null;
  translation_key?: string | null;
  hidden?: boolean;
  /** Not part of the display registry; checked defensively. */
  disabled_by?: string | null;
}

export interface DisplayDevice {
  id: string;
  name?: string | null;
  name_by_user?: string | null;
  area_id?: string | null;
}

export interface DisplayArea {
  area_id: string;
  name: string;
  floor_id?: string | null;
}

export interface DisplayFloor {
  floor_id: string;
  name: string;
  level?: number | null;
  icon?: string | null;
}

/** `hass` with the frontend registries the card reads. */
export type HouseHass = HomeAssistant & {
  entities?: Record<string, DisplayEntity>;
  devices?: Record<string, DisplayDevice>;
  areas?: Record<string, DisplayArea>;
  floors?: Record<string, DisplayFloor>;
};

/** Registry row with the extra fields the fallback reads. */
type RegistryRow = EntityRegistryEntry & {
  hidden_by?: string | null;
  area_id?: string | null;
};

export interface HouseWindow {
  /** The window key: the Position sensor's `window_key`, else the unique_id prefix. */
  key: string;
  /** Display name: the device name with the room name taken off the front. */
  name: string;
  /** The window device's full name. */
  deviceName: string;
  deviceId: string | null;
  areaId: string | null;
  floorId: string | null;
  coverType: string;
  /** Physical covers the window drives, primary first. */
  covers: string[];
  entities: Partial<Record<WindowRole, string>>;
  /** Only known with the full registry; used for the settings link. */
  configEntryId: string | null;
  configSubentryId: string | null;
}

export interface HouseRoom {
  /** Area id, or null for the "Unassigned" room. */
  id: string | null;
  name: string;
  windows: HouseWindow[];
}

export interface HouseFloor {
  /** Floor id, or null for rooms without a floor. */
  id: string | null;
  name: string;
  level: number | null;
  rooms: HouseRoom[];
}

export type HouseHub = Partial<Record<HubRole, string>>;

/** The house device's setting entities, by setting key (`climate_on`,
 *  `temp_low`, ...). */
export type HouseHubSettings = Partial<Record<string, string>>;

export interface HouseModel {
  floors: HouseFloor[];
  /** Every window in display order (floor, room, name). */
  windows: HouseWindow[];
  hub: HouseHub;
  /** The house settings entities on the house device (P5 flip). */
  hubSettings: HouseHubSettings;
  /** The house device (its page holds the house settings), when known. */
  hubDeviceId: string | null;
  /** True when some adaptive_cover rows need the full registry to classify
   *  (no translation key) and none was passed in. */
  needsRegistry: boolean;
}

export interface HouseFilter {
  floors?: string[];
  areas?: string[];
}

export const UNASSIGNED_ROOM_NAME = 'Unassigned';
export const NO_FLOOR_NAME = 'Other';

function nonEmpty(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

function domainOf(entityId: string): string {
  return entityId.slice(0, entityId.indexOf('.'));
}

// adaptive_cover rows of `hass.entities`, per display-registry object. HA
// hands out a new `hass` on every state change but keeps `hass.entities`
// until the registry changes, so the full scan runs once per registry change.
const platformRowsCache = new WeakMap<object, DisplayEntity[]>();

function platformRows(hass: HouseHass, registry: RegistryRow[] | null): DisplayEntity[] {
  const entities = hass.entities;
  if (entities) {
    const cached = platformRowsCache.get(entities);
    if (cached) return cached;
    const rows = Object.values(entities).filter((e) => e?.platform === INTEGRATION_DOMAIN);
    platformRowsCache.set(entities, rows);
    return rows;
  }
  // No display registry (very old frontend): use the full registry rows.
  return (registry ?? [])
    .filter((r) => r.platform === INTEGRATION_DOMAIN)
    .map((r) => ({
      entity_id: r.entity_id,
      platform: r.platform,
      device_id: r.device_id,
      area_id: r.area_id ?? null,
      translation_key: r.translation_key ?? null,
      hidden: !!r.hidden_by,
      disabled_by: r.disabled_by ?? null,
    }));
}

const registryIndexCache = new WeakMap<RegistryRow[], Map<string, RegistryRow>>();

function registryIndex(registry: RegistryRow[] | null): Map<string, RegistryRow> | null {
  if (!registry) return null;
  let idx = registryIndexCache.get(registry);
  if (!idx) {
    idx = new Map(registry.map((r) => [r.entity_id, r]));
    registryIndexCache.set(registry, idx);
  }
  return idx;
}

interface Classified {
  row: DisplayEntity;
  window?: WindowRole;
  hub?: HubRole;
  /** A house setting candidate (kept only when it is on the house device). */
  hubSetting?: string;
  /** The unique_id prefix, when the registry row is known. */
  uidKey?: string;
  reg?: RegistryRow;
}

/** Window key from a unique_id, given the role's frozen suffix. */
function uidPrefix(uniqueId: string | undefined, role: WindowRole): string | undefined {
  if (!nonEmpty(uniqueId)) return undefined;
  const tail = `_${ROLE_SUFFIX[role]}`;
  return uniqueId.length > tail.length && uniqueId.endsWith(tail)
    ? uniqueId.slice(0, -tail.length)
    : undefined;
}

function classify(row: DisplayEntity, reg: RegistryRow | undefined): Classified | null {
  const domain = domainOf(row.entity_id);
  const uid = reg?.unique_id;
  // The only cover entity the integration creates is the house cover.
  if (domain === 'cover') return { row, hub: 'cover', reg };
  const tk = row.translation_key ?? reg?.translation_key;
  if (nonEmpty(tk)) {
    const hubSetting = HUB_SETTING_KEYS[`${domain}:${tk}`];
    const hub = HUB_TRANSLATION_KEYS[`${domain}:${tk}`];
    if (hub) return { row, hub, hubSetting, reg };
    const role = WINDOW_TRANSLATION_KEYS[`${domain}:${tk}`];
    if (role) return { row, window: role, uidKey: uidPrefix(uid, role), reg };
    return hubSetting ? { row, hubSetting, reg } : null;
  }
  if (!nonEmpty(uid)) return null;
  if (uid.startsWith(HUB_UNIQUE_ID_PREFIX)) {
    const suffix = `${domain}:${uid.slice(HUB_UNIQUE_ID_PREFIX.length)}`;
    const hub = HUB_UNIQUE_ID_SUFFIXES[suffix];
    const hubSetting = HUB_SETTING_KEYS[suffix];
    return hub || hubSetting ? { row, hub, hubSetting, reg } : null;
  }
  for (const [key, role] of Object.entries(WINDOW_UNIQUE_ID_SUFFIXES)) {
    if (!key.startsWith(`${domain}:`)) continue;
    const prefix = uidPrefix(uid, role);
    if (prefix) return { row, window: role, uidKey: prefix, reg };
  }
  return null;
}

function positionAttrs(hass: HomeAssistant, entityId: string): CoverPositionAttributes | undefined {
  return hass.states[entityId]?.attributes as CoverPositionAttributes | undefined;
}

/** Covers a Position sensor names (`cover_entity` first, then `cover_entities`),
 *  else the covers it has moved or gated (older integrations). */
function windowCovers(attrs: CoverPositionAttributes | undefined): string[] {
  const out: string[] = [];
  if (nonEmpty(attrs?.cover_entity)) out.push(attrs!.cover_entity!);
  if (Array.isArray(attrs?.cover_entities)) out.push(...attrs!.cover_entities!.filter(nonEmpty));
  if (out.length === 0) {
    out.push(...Object.keys(attrs?.last_moves ?? {}), ...Object.keys(attrs?.move_blocked_by ?? {}));
    out.sort();
  }
  return [...new Set(out)];
}

const KNOWN_COVER_TYPES = new Set(['cover_blind', 'cover_awning', 'cover_tilt']);

/** The area of a physical cover: its own area, else its device's. */
function coverArea(hass: HouseHass, coverId: string): string | null {
  const row = hass.entities?.[coverId];
  if (!row) return null;
  if (nonEmpty(row.area_id)) return row.area_id;
  const dev = row.device_id ? hass.devices?.[row.device_id] : undefined;
  return nonEmpty(dev?.area_id) ? dev!.area_id! : null;
}

/** True when `areaId` names a real area (or areas are not loaded at all). */
function knownArea(hass: HouseHass, areaId: string | null | undefined): areaId is string {
  if (!nonEmpty(areaId)) return false;
  return !hass.areas || !!hass.areas[areaId];
}

/**
 * The window name inside its room: "Master east" in room "Master" → "East".
 * Kept whole when it does not start with the room name.
 */
export function stripRoomName(name: string, room: string | null | undefined): string {
  if (!room) return name;
  const lower = name.toLowerCase();
  const prefix = room.toLowerCase();
  if (!lower.startsWith(prefix) || name.length <= room.length) return name;
  const rest = name.slice(room.length);
  if (!/^[\s\-–—:·]/.test(rest)) return name;
  const trimmed = rest.replace(/^[\s\-–—:·]+/, '');
  if (!trimmed) return name;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

const byName = (a: { name: string }, b: { name: string }): number =>
  a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });

/**
 * Discover every window and the house device, grouped floor → room.
 *
 * `registry` is the full entity registry, or null. It is only read for rows
 * the display registry cannot classify (see `needsRegistry`).
 */
export function discoverHouse(
  hass: HomeAssistant,
  registry: EntityRegistryEntry[] | null,
  filter: HouseFilter = {},
): HouseModel {
  const h = hass as HouseHass;
  const regRows = registry as RegistryRow[] | null;
  const regIdx = registryIndex(regRows);
  let needsRegistry = false;

  const classified: Classified[] = [];
  for (const row of platformRows(h, regRows)) {
    const reg = regIdx?.get(row.entity_id);
    if (row.disabled_by || reg?.disabled_by) continue;
    const hit = classify(row, reg);
    // Hidden rows are left out, except the Climate mode switch: a hidden
    // alias since the P5 flip that the house Climate control still drives
    // until the house has a climate switch of its own.
    if ((row.hidden || reg?.hidden_by) && hit?.window !== 'climateSwitch') continue;
    if (hit) classified.push(hit);
    else if (!nonEmpty(row.translation_key) && !reg && domainOf(row.entity_id) !== 'number') {
      needsRegistry = true;
    }
  }

  // Hub roles.
  const hub: HouseHub = {};
  let hubDeviceId: string | null = null;
  for (const c of classified) {
    if (c.hub && !hub[c.hub]) hub[c.hub] = c.row.entity_id;
    if (c.hub && !hubDeviceId && nonEmpty(c.row.device_id)) hubDeviceId = c.row.device_id;
  }
  // House settings: rows on the house device, or with the house unique_id.
  const hubSettings: HouseHubSettings = {};
  for (const c of classified) {
    if (!c.hubSetting || hubSettings[c.hubSetting]) continue;
    const onHub =
      (hubDeviceId !== null && c.row.device_id === hubDeviceId) ||
      !!c.reg?.unique_id?.startsWith(HUB_UNIQUE_ID_PREFIX);
    if (onHub) hubSettings[c.hubSetting] = c.row.entity_id;
  }

  // One window per Position sensor.
  interface Draft {
    key: string;
    uidKey?: string;
    position: Classified;
    entities: Partial<Record<WindowRole, string>>;
  }
  const drafts: Draft[] = [];
  const byUidKey = new Map<string, Draft>();
  const byDevice = new Map<string, Draft>();
  const seenKeys = new Set<string>();
  for (const c of classified) {
    if (c.window !== 'position') continue;
    const attrKey = positionAttrs(hass, c.row.entity_id)?.window_key;
    const key = nonEmpty(attrKey) ? attrKey : (c.uidKey ?? c.row.device_id ?? c.row.entity_id);
    if (seenKeys.has(key)) continue;
    seenKeys.add(key);
    const d: Draft = {
      key,
      uidKey: c.uidKey,
      position: c,
      entities: { position: c.row.entity_id },
    };
    drafts.push(d);
    if (c.uidKey) byUidKey.set(c.uidKey, d);
    if (nonEmpty(attrKey)) byUidKey.set(attrKey, byUidKey.get(attrKey) ?? d);
    if (c.row.device_id && !byDevice.has(c.row.device_id)) byDevice.set(c.row.device_id, d);
  }
  // Attach the other roles: same unique_id prefix first, else same device.
  for (const c of classified) {
    if (!c.window || c.window === 'position') continue;
    const d =
      (c.uidKey ? byUidKey.get(c.uidKey) : undefined) ??
      (c.row.device_id ? byDevice.get(c.row.device_id) : undefined);
    if (d && !d.entities[c.window]) d.entities[c.window] = c.row.entity_id;
  }

  const floorsWanted = new Set(filter.floors ?? []);
  const areasWanted = new Set(filter.areas ?? []);
  const filtering = floorsWanted.size > 0 || areasWanted.size > 0;

  const windows: HouseWindow[] = [];
  for (const d of drafts) {
    const posId = d.position.row.entity_id;
    const attrs = positionAttrs(hass, posId);
    const covers = windowCovers(attrs);
    const deviceId = d.position.row.device_id ?? null;
    const device = deviceId ? h.devices?.[deviceId] : undefined;
    const friendly = hass.states[posId]?.attributes?.friendly_name;
    const deviceName =
      device?.name_by_user || device?.name || (nonEmpty(friendly) ? friendly : d.key);

    const candidates = [
      d.position.row.area_id,
      device?.area_id,
      ...covers.map((c) => coverArea(h, c)),
    ];
    const areaId = candidates.find((a) => knownArea(h, a)) ?? null;
    const area = areaId ? h.areas?.[areaId] : undefined;
    const floorId =
      nonEmpty(area?.floor_id) && h.floors?.[area!.floor_id!] ? area!.floor_id! : null;

    if (
      filtering &&
      !(floorId && floorsWanted.has(floorId)) &&
      !(areaId && areasWanted.has(areaId))
    ) {
      continue;
    }

    const rawType = attrs?.cover_type;
    windows.push({
      key: d.key,
      name: stripRoomName(deviceName, area?.name),
      deviceName,
      deviceId,
      areaId,
      floorId,
      coverType: nonEmpty(rawType) && KNOWN_COVER_TYPES.has(rawType) ? rawType : 'cover_blind',
      covers,
      entities: d.entities,
      configEntryId: d.position.reg?.config_entry_id ?? null,
      configSubentryId: d.position.reg?.config_subentry_id ?? null,
    });
  }

  // Group: floor → room → windows.
  const floorMap = new Map<string | null, HouseFloor>();
  const roomMap = new Map<string, HouseRoom>();
  for (const w of windows) {
    let floor = floorMap.get(w.floorId);
    if (!floor) {
      const f = w.floorId ? h.floors?.[w.floorId] : undefined;
      floor = {
        id: w.floorId,
        name: f?.name ?? NO_FLOOR_NAME,
        level: typeof f?.level === 'number' ? f.level : null,
        rooms: [],
      };
      floorMap.set(w.floorId, floor);
    }
    const roomKey = `${w.floorId ?? ''}|${w.areaId ?? ''}`;
    let room = roomMap.get(roomKey);
    if (!room) {
      room = {
        id: w.areaId,
        name: w.areaId ? (h.areas?.[w.areaId]?.name ?? w.areaId) : UNASSIGNED_ROOM_NAME,
        windows: [],
      };
      roomMap.set(roomKey, room);
      floor.rooms.push(room);
    }
    room.windows.push(w);
  }

  const floors = [...floorMap.values()];
  // Top floor first; floors without a level after those with one; the
  // no-floor group last.
  floors.sort((a, b) => {
    if ((a.id === null) !== (b.id === null)) return a.id === null ? 1 : -1;
    if ((a.level === null) !== (b.level === null)) return a.level === null ? 1 : -1;
    if (a.level !== null && b.level !== null && a.level !== b.level) return b.level - a.level;
    return byName(a, b);
  });
  for (const floor of floors) {
    floor.rooms.sort((a, b) => {
      if ((a.id === null) !== (b.id === null)) return a.id === null ? 1 : -1;
      return byName(a, b);
    });
    for (const room of floor.rooms) room.windows.sort(byName);
  }
  // A house without any floors shows its rooms without a floor heading.
  if (floors.length === 1 && floors[0].id === null) floors[0].name = '';

  const ordered = floors.flatMap((f) => f.rooms.flatMap((r) => r.windows));
  return {
    floors,
    windows: ordered,
    hub,
    hubSettings,
    hubDeviceId,
    needsRegistry: needsRegistry && !registry,
  };
}

/** Every entity id the house card reads for `model` (for change detection). */
export function watchedEntityIds(model: HouseModel): string[] {
  const ids = new Set<string>();
  for (const w of model.windows) {
    for (const id of Object.values(w.entities)) if (id) ids.add(id);
    for (const c of w.covers) ids.add(c);
  }
  for (const id of Object.values(model.hub)) if (id) ids.add(id);
  for (const id of Object.values(model.hubSettings ?? {})) if (id) ids.add(id);
  ids.add('sun.sun');
  return [...ids];
}
