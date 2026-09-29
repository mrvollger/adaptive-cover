import type { HomeAssistant } from 'custom-card-helpers';
import { INTEGRATION_DOMAIN, UNIQUE_ID_ROLES, type EntityRole } from '../const';
import type { EntityRegistryEntry } from './entity-registry';
import type { CoverPositionAttributes, DiscoveredEntities, WindowBindingConfig } from '../types';
import { windowRefFromConfig, windowRefId, type WindowRef } from './window-binding';

/*
 * Window discovery.
 *
 * A card names its window by `window:` (window key), `cover:` (cover entity) or
 * a legacy `entry_id:`. Discovery turns that into the window's entities
 * WITHOUT filtering on the registry's `config_entry_id`: once windows are
 * subentries of one house entry, every window shares that id (it is copied
 * into the result only to build the settings link). The steps:
 *
 * 1. Find the window's Position sensor. Attributes first: the sensor whose
 *    `window_key` attribute equals the key, or whose `cover_entity` /
 *    `cover_entities` attributes list the cover.
 * 2. Fall back to the unique_id prefix. Every entity's unique_id is
 *    `{window_key}_{suffix}` and never changes, so a `window:` / `entry_id:`
 *    key still resolves when the Position sensor has no state (or an older
 *    integration does not publish `window_key`). A migrated window's key is
 *    its old entry_id, which is why legacy `entry_id:` configs keep working.
 *    For `cover:` with an older integration, the last fallback is the keys of
 *    the `last_moves` / `move_blocked_by` attributes.
 * 3. Collect the window's other entities by the same unique_id prefix.
 *
 * The full entity registry is an async websocket fetch (`hass.entities` is a
 * display-only subset that omits `unique_id`). The caller passes in the
 * pre-fetched registry so discovery stays pure and sync.
 */

type DomainSuffixes = Array<{ suffix: string; role: EntityRole }>;

/** UNIQUE_ID_ROLES regrouped by entity domain, longest suffix first. */
const SUFFIXES_BY_DOMAIN: Record<string, DomainSuffixes> = (() => {
  const out: Record<string, DomainSuffixes> = {};
  for (const [key, role] of Object.entries(UNIQUE_ID_ROLES)) {
    const sep = key.indexOf(':');
    const domain = key.slice(0, sep);
    (out[domain] ??= []).push({ suffix: key.slice(sep + 1), role });
  }
  for (const list of Object.values(out)) list.sort((a, b) => b.suffix.length - a.suffix.length);
  return out;
})();

const KNOWN_COVER_TYPES = new Set(['cover_blind', 'cover_awning', 'cover_tilt']);

/** The registry rows of one window, grouped by unique_id prefix. */
interface WindowRows {
  /** The unique_id prefix shared by the window's entities. */
  key: string;
  entities: Partial<Record<EntityRole, string>>;
  /** Registry row of the Position sensor, when the window has one. */
  position?: EntityRegistryEntry;
  /** The Position sensor's device, else the first device seen for the window. */
  deviceId?: string;
}

interface RegistryIndex {
  /** Windows by unique_id prefix, in registry order. */
  byKey: Map<string, WindowRows>;
  /** Windows that have a Position sensor, in registry order. */
  withPosition: WindowRows[];
}

// One index per registry array. The registry store hands every card the same
// array, so a dashboard of N cards builds the index once per registry change.
const indexCache = new WeakMap<EntityRegistryEntry[], RegistryIndex>();

/** The window key and role of an adaptive_cover registry row, or null. */
function classify(row: EntityRegistryEntry): { key: string; role: EntityRole } | null {
  if (row.platform !== INTEGRATION_DOMAIN || typeof row.unique_id !== 'string') return null;
  const domain = row.entity_id.split('.')[0];
  for (const { suffix, role } of SUFFIXES_BY_DOMAIN[domain] ?? []) {
    const tail = `_${suffix}`;
    if (row.unique_id.length > tail.length && row.unique_id.endsWith(tail)) {
      return { key: row.unique_id.slice(0, -tail.length), role };
    }
  }
  return null;
}

function indexRegistry(registry: EntityRegistryEntry[]): RegistryIndex {
  const cached = indexCache.get(registry);
  if (cached) return cached;
  const byKey = new Map<string, WindowRows>();
  for (const row of registry) {
    const hit = classify(row);
    if (!hit) continue;
    let win = byKey.get(hit.key);
    if (!win) {
      win = { key: hit.key, entities: {} };
      byKey.set(hit.key, win);
    }
    if (!win.entities[hit.role]) win.entities[hit.role] = row.entity_id;
    if (hit.role === 'target_position_sensor' && !win.position) {
      win.position = row;
      if (row.device_id) win.deviceId = row.device_id;
    }
    if (!win.deviceId && row.device_id) win.deviceId = row.device_id;
  }
  const index: RegistryIndex = {
    byKey,
    withPosition: [...byKey.values()].filter((w) => w.position),
  };
  indexCache.set(registry, index);
  return index;
}

function positionAttrs(hass: HomeAssistant, win: WindowRows): CoverPositionAttributes | undefined {
  const id = win.position?.entity_id;
  return id ? (hass.states[id]?.attributes as CoverPositionAttributes | undefined) : undefined;
}

function nonEmpty(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

/** Covers the Position sensor's `cover_entity` / `cover_entities` attributes
 *  name, primary first. Empty when the integration publishes neither. */
function attributeCovers(attrs: CoverPositionAttributes | undefined): string[] {
  const primary = nonEmpty(attrs?.cover_entity) ? attrs!.cover_entity! : null;
  const list = Array.isArray(attrs?.cover_entities) ? attrs!.cover_entities!.filter(nonEmpty) : [];
  const out = primary ? [primary, ...list] : list;
  return [...new Set(out)];
}

/** Covers the integration has moved or gated, from the `last_moves` /
 *  `move_blocked_by` keys. Used only when the cover attributes are absent. */
function historyCovers(attrs: CoverPositionAttributes | undefined): string[] {
  const ids = new Set<string>([
    ...Object.keys(attrs?.last_moves ?? {}),
    ...Object.keys(attrs?.move_blocked_by ?? {}),
  ]);
  return [...ids].sort();
}

/** A resolved window: its registry rows and its canonical key. */
interface ResolvedWindow {
  rows: WindowRows;
  windowKey: string;
}

function resolved(hass: HomeAssistant, rows: WindowRows): ResolvedWindow {
  const attrKey = positionAttrs(hass, rows)?.window_key;
  return { rows, windowKey: nonEmpty(attrKey) ? attrKey : rows.key };
}

/** Resolve a ref to its window: attributes first, then the unique_id prefix. */
function resolveWindow(
  hass: HomeAssistant,
  ref: WindowRef,
  index: RegistryIndex,
): ResolvedWindow | null {
  if (ref.kind === 'cover') {
    const target = ref.entity_id;
    // (a) Attributes: the primary cover first, then any listed cover.
    for (const rows of index.withPosition) {
      if (positionAttrs(hass, rows)?.cover_entity === target) return resolved(hass, rows);
    }
    for (const rows of index.withPosition) {
      if (attributeCovers(positionAttrs(hass, rows)).includes(target)) {
        return resolved(hass, rows);
      }
    }
    // (b) An integration that does not publish the cover attributes: the
    // covers it has moved or gated. Skip sensors that do publish them.
    for (const rows of index.withPosition) {
      const attrs = positionAttrs(hass, rows);
      if (attributeCovers(attrs).length > 0) continue;
      if (historyCovers(attrs).includes(target)) return resolved(hass, rows);
    }
    return null;
  }

  // `window:` and legacy `entry_id:` both carry the window key.
  // (a) Attributes: the Position sensor that reports this window_key.
  for (const rows of index.withPosition) {
    if (positionAttrs(hass, rows)?.window_key === ref.key) return { rows, windowKey: ref.key };
  }
  // (b) The unique_id prefix.
  const rows = index.byKey.get(ref.key);
  return rows ? { rows, windowKey: ref.key } : null;
}

interface DeviceDisplay {
  id: string;
  name?: string | null;
  name_by_user?: string | null;
  config_entries?: string[];
}

type HassWithDevices = HomeAssistant & {
  devices?: Record<string, DeviceDisplay>;
};

/** Display title: the window device's name, else the key. */
function windowTitle(hass: HomeAssistant, win: ResolvedWindow): string {
  const devices = (hass as HassWithDevices).devices;
  if (devices) {
    const dev = win.rows.deviceId ? devices[win.rows.deviceId] : undefined;
    if (dev) return dev.name_by_user || dev.name || win.windowKey;
    // Registry rows without a device: today's layout names the device after
    // the config entry, whose id is the window key.
    if (!win.rows.deviceId) {
      for (const d of Object.values(devices)) {
        if (d.config_entries?.includes(win.windowKey)) {
          return d.name_by_user || d.name || win.windowKey;
        }
      }
    }
  }
  return win.windowKey;
}

/** Combine the registry-derived window with the `hass`-derived fields (title,
 *  managed covers, cover type) into a full {@link DiscoveredEntities}. */
function assembleDiscovered(hass: HomeAssistant, win: ResolvedWindow): DiscoveredEntities {
  const attrs = positionAttrs(hass, win.rows);

  const fromAttrs = attributeCovers(attrs);
  const managedCovers = fromAttrs.length > 0 ? fromAttrs : historyCovers(attrs);

  // The Position sensor's `cover_type` attribute is authoritative. For an
  // integration that does not publish it, default to the vertical-blind
  // visuals, and mark the window tilt when every managed cover is tilt-only.
  let coverType: DiscoveredEntities['cover_type'] = 'cover_blind';
  if (nonEmpty(attrs?.cover_type) && KNOWN_COVER_TYPES.has(attrs!.cover_type!)) {
    coverType = attrs!.cover_type!;
  } else if (managedCovers.length > 0) {
    const isTilt = managedCovers.every((id) => {
      const a = hass.states[id]?.attributes as
        | { current_position?: number; current_tilt_position?: number }
        | undefined;
      return a?.current_tilt_position !== undefined && a?.current_position === undefined;
    });
    if (isTilt) coverType = 'cover_tilt';
  }

  return {
    window_key: win.windowKey,
    entry_id: win.windowKey,
    entry_title: windowTitle(hass, win),
    cover_type: coverType,
    entities: { ...win.rows.entities },
    managed_covers: managedCovers,
    device_id: win.rows.deviceId,
    config_entry_id: win.rows.position?.config_entry_id ?? null,
    config_subentry_id: win.rows.position?.config_subentry_id ?? null,
  };
}

/** A single-window card config, or an already-parsed ref. */
export type WindowTarget = (WindowBindingConfig & { type?: string }) | WindowRef | null | undefined;

function toRef(target: WindowTarget): WindowRef | null {
  if (!target) return null;
  if ('kind' in target && typeof target.kind === 'string') return target as WindowRef;
  return windowRefFromConfig(target as WindowBindingConfig);
}

/**
 * Discover one window's entities. Accepts a card config (`window:`, `cover:` or
 * legacy `entry_id:`) or a {@link WindowRef}. Null when nothing matches.
 */
export function discoverEntities(
  hass: HomeAssistant,
  target: WindowTarget,
  registry: EntityRegistryEntry[],
): DiscoveredEntities | null {
  const ref = toRef(target);
  if (!ref) return null;
  const win = resolveWindow(hass, ref, indexRegistry(registry));
  return win ? assembleDiscovered(hass, win) : null;
}

/**
 * The registry rows of the window a ref resolves to (every adaptive_cover row
 * whose unique_id starts with the window's prefix). Cards persist this slice
 * to warm-start the next page load. Empty when the ref does not resolve.
 */
export function windowRegistrySlice(
  hass: HomeAssistant,
  target: WindowTarget,
  registry: EntityRegistryEntry[],
): EntityRegistryEntry[] {
  const ref = toRef(target);
  if (!ref) return [];
  const win = resolveWindow(hass, ref, indexRegistry(registry));
  if (!win) return [];
  const prefix = `${win.rows.key}_`;
  return registry.filter(
    (e) => e.platform === INTEGRATION_DOMAIN && e.unique_id?.startsWith(prefix),
  );
}

/** One pickable window, for the card editors and the card picker stubs. */
export interface WindowOption {
  window_key: string;
  title: string;
  /** The window's primary cover, when the integration publishes it. */
  cover?: string;
}

/**
 * Every window in the registry: each adaptive_cover Position sensor that is not
 * disabled. The title is the window device's name, else `fallbackTitles[key]`
 * (for example a config entry title), else the key. Sorted by title.
 */
export function listWindows(
  hass: HomeAssistant,
  registry: EntityRegistryEntry[],
  fallbackTitles: Record<string, string> = {},
): WindowOption[] {
  const out: WindowOption[] = [];
  for (const rows of indexRegistry(registry).withPosition) {
    if (rows.position?.disabled_by) continue;
    const win = resolved(hass, rows);
    let title = windowTitle(hass, win);
    if (title === win.windowKey && fallbackTitles[win.windowKey]) {
      title = fallbackTitles[win.windowKey];
    }
    const option: WindowOption = { window_key: win.windowKey, title };
    const cover = attributeCovers(positionAttrs(hass, rows))[0];
    if (cover) option.cover = cover;
    out.push(option);
  }
  return out.sort(
    (a, b) => a.title.localeCompare(b.title) || a.window_key.localeCompare(b.window_key),
  );
}

/**
 * Memoized discovery for single-window cards, which re-run on every HA state
 * tick (HA hands over a fresh `hass` object each time). Resolving the ref is
 * cheap (one attribute read per window), so it runs every call; the result is
 * reused when the registry, the resolved window, `hass.devices` (title), the
 * Position state (covers, type) and the control-status state are all
 * reference-equal to the previous call. Returning the **same**
 * `DiscoveredEntities` object keeps `_discovered` (and the child props derived
 * from it) stable across unrelated ticks.
 */
export function createDiscoveryMemo(): (
  hass: HomeAssistant,
  target: WindowTarget,
  registry: EntityRegistryEntry[],
) => DiscoveredEntities | null {
  let last: {
    registry: EntityRegistryEntry[];
    rows: WindowRows;
    windowKey: string;
    devices: unknown;
    posState: unknown;
    ctrlState: unknown;
    result: DiscoveredEntities;
  } | null = null;

  return (hass, target, registry) => {
    const ref = toRef(target);
    const win = ref ? resolveWindow(hass, ref, indexRegistry(registry)) : null;
    if (!win) {
      last = null;
      return null;
    }

    const devices = (hass as HassWithDevices).devices;
    const posId = win.rows.entities.target_position_sensor;
    const ctrlId = win.rows.entities.control_status_sensor;
    const posState = posId ? hass.states[posId] : undefined;
    const ctrlState = ctrlId ? hass.states[ctrlId] : undefined;

    if (
      last !== null &&
      last.registry === registry &&
      last.rows === win.rows &&
      last.windowKey === win.windowKey &&
      last.devices === devices &&
      last.posState === posState &&
      last.ctrlState === ctrlState
    ) {
      return last.result;
    }

    const result = assembleDiscovered(hass, win);
    last = {
      registry,
      rows: win.rows,
      windowKey: win.windowKey,
      devices,
      posState,
      ctrlState,
      result,
    };
    return result;
  };
}

/** Result of multi-window discovery: the windows that resolved, plus the refs that didn't. */
export interface DiscoveryListResult {
  list: DiscoveredEntities[];
  missing: WindowRef[];
}

/**
 * Memoized discovery for the multi-window cards (sky-compass card), which accept
 * a list of refs. Each ref runs through its own {@link createDiscoveryMemo}, so a
 * per-window result is reference-stable across ticks. This wrapper additionally
 * returns the **same `{ list, missing }` object** (and therefore the same `list`
 * array) when the ref list and every per-window result are unchanged — so the
 * array handed to the child compass/chart stays reference-stable and does not
 * defeat their own `shouldUpdate`. Two refs that resolve to the same window
 * produce one overlay.
 */
export function createDiscoveryListMemo(): (
  hass: HomeAssistant,
  refs: WindowRef[],
  registry: EntityRegistryEntry[],
) => DiscoveryListResult {
  const memos = new Map<string, ReturnType<typeof createDiscoveryMemo>>();
  let lastIds: string[] = [];
  let lastResults: (DiscoveredEntities | null)[] = [];
  let cached: DiscoveryListResult = { list: [], missing: [] };

  return (hass, refs, registry) => {
    const ids = refs.map(windowRefId);
    const results = refs.map((ref, i) => {
      let memo = memos.get(ids[i]);
      if (!memo) {
        memo = createDiscoveryMemo();
        memos.set(ids[i], memo);
      }
      return memo(hass, ref, registry);
    });
    // Drop per-window memos for refs no longer configured.
    if (memos.size > ids.length) {
      for (const id of memos.keys()) if (!ids.includes(id)) memos.delete(id);
    }

    const unchanged =
      lastIds.length === ids.length &&
      lastIds.every((id, i) => id === ids[i]) &&
      lastResults.length === results.length &&
      lastResults.every((r, i) => r === results[i]);
    if (unchanged) return cached;

    lastIds = ids;
    lastResults = results;
    const list: DiscoveredEntities[] = [];
    const missing: WindowRef[] = [];
    const seen = new Set<string>();
    refs.forEach((ref, i) => {
      const d = results[i];
      if (!d) missing.push(ref);
      else if (!seen.has(d.window_key)) {
        seen.add(d.window_key);
        list.push(d);
      }
    });
    cached = { list, missing };
    return cached;
  };
}
