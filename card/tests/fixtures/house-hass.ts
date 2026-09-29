/// <reference types="node" />
// A `hass` for the house card, built from the sanitized snapshot of the live
// house (tests/fixtures/house_snapshot/, adaptive_cover 1.13.5): 15 windows +
// the "Adaptive Cover All" hub, 3 floors, the physical covers and their areas.
//
// - surface 'today' projects the snapshot onto the current entity surface
//   (P1): every row gets its translation key and the Position sensor gets
//   window_key / cover_entity / cover_type. This is what the card sees now.
// - surface 'legacy' is the snapshot as captured: no translation keys, no
//   window attributes. Only the full registry (unique_id) identifies rows.
//
// Only 3 of the 15 window devices have an area in the snapshot; the others
// get theirs from the physical cover's device, which exercises the fallback.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { vi, type Mock } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';

import type { EntityRegistryEntry } from '../../src/lib/entity-registry';

// import.meta.dirname, not new URL(): under happy-dom the global URL is the
// DOM's, which does not resolve file: URLs.
const SNAPSHOT = resolve(import.meta.dirname, '../../../tests/fixtures/house_snapshot');
const load = <T>(name: string): T => JSON.parse(readFileSync(resolve(SNAPSHOT, name), 'utf8')) as T;

type State = { state: string; attributes: Record<string, unknown> };

interface SnapshotEntry {
  entry_id: string;
  title: string;
  role: 'window' | 'hub' | 'disabled_legacy';
  data: { name?: string; sensor_type?: string } | null;
  options: Record<string, unknown> | null;
}
interface SnapshotDevice {
  device_id: string;
  name: string | null;
  name_by_user: string | null;
  area_id: string | null;
  config_entries: string[];
}
type SnapshotRow = EntityRegistryEntry & {
  domain: string;
  area_id: string | null;
  hidden_by: string | null;
};
interface PhysicalCover {
  entity_id: string;
  platform: string;
  device_id: string;
  device_name: string;
  device_area_id: string | null;
  registry_area_id: string | null;
  state_now: string;
  current_position_now: number;
}

const ENTRIES = load<{ entries: SnapshotEntry[] }>('config_entries.json').entries;
const DEVICES = load<{ devices: SnapshotDevice[] }>('device_registry.json').devices;
const REGISTRY = load<{ entities: SnapshotRow[] }>('entity_registry.json').entities;
const STATES = load<{ states: Record<string, State> }>('entity_states.json').states;
const COVERS = load<{ covers: PhysicalCover[] }>('physical_covers.json').covers;
const FLOORS_AREAS = load<{
  floors: Array<{ floor_id: string; name: string; level: number; icon: string | null }>;
  areas: Array<{ area_id: string; name: string; floor_id: string | null }>;
}>('floors_areas.json');

export const WINDOW_ENTRIES = ENTRIES.filter((e) => e.role === 'window');
export const HUB_ENTRY = ENTRIES.find((e) => e.role === 'hub')!;
const HUB_PREFIX = 'adaptive_cover_hub_';

/** entity_surface.py: (domain, unique_id suffix) → translation key. */
const WINDOW_TKEY: Record<string, string> = {
  'sensor:Cover Position': 'target_position',
  'sensor:Control Method': 'control',
  'sensor:Start Sun': 'start_sun',
  'sensor:End Sun': 'end_sun',
  'sensor:Next State Change': 'next_change',
  'sensor:Last State Change': 'last_change',
  'select:mode_select': 'mode',
  'button:Reset Manual Override': 'return_to_auto',
  'binary_sensor:Manual Override': 'manual_override',
  'binary_sensor:Sun Infront': 'sun_motion',
  'switch:Toggle Control': 'control_toggle',
  'switch:Manual Override': 'manual_toggle',
  'switch:Climate Mode': 'switch_mode',
  'switch:Outside Temperature': 'temp_toggle',
  'switch:Lux': 'lux_toggle',
  'switch:Irradiance': 'irradiance_toggle',
};
const HUB_TKEY: Record<string, string | null> = {
  'cover:cover': null,
  'select:house_mode': 'house_mode',
  'button:reset_all': 'return_all_to_auto',
};

function translationKey(row: SnapshotRow): string | null {
  if (row.unique_id.startsWith(HUB_PREFIX)) {
    return HUB_TKEY[`${row.domain}:${row.unique_id.slice(HUB_PREFIX.length)}`] ?? null;
  }
  const suffix = row.unique_id.slice(row.config_entry_id!.length + 1);
  if (row.domain === 'number') return suffix.replace(/^number_/, '');
  return WINDOW_TKEY[`${row.domain}:${suffix}`] ?? null;
}

/** Window roles by their unique_id suffix (for `eid`). */
export const ROLE_SUFFIX = {
  position: 'Cover Position',
  mode: 'mode_select',
  returnButton: 'Reset Manual Override',
  manualOverride: 'Manual Override',
  sunInFront: 'Sun Infront',
  controlMethod: 'Control Method',
  controlSwitch: 'Toggle Control',
  climateSwitch: 'Climate Mode',
} as const;
const ROLE_DOMAIN: Record<keyof typeof ROLE_SUFFIX, string> = {
  position: 'sensor',
  mode: 'select',
  returnButton: 'button',
  manualOverride: 'binary_sensor',
  sunInFront: 'binary_sensor',
  controlMethod: 'sensor',
  controlSwitch: 'switch',
  climateSwitch: 'switch',
};

export type HouseTestHass = HomeAssistant & {
  callService: Mock;
  callWS: Mock;
  entities: Record<string, Record<string, unknown>>;
  devices: Record<string, Record<string, unknown>>;
  areas: Record<string, Record<string, unknown>>;
  floors: Record<string, Record<string, unknown>>;
};

export interface HouseFixture {
  hass: HouseTestHass;
  /** The full registry rows (for the unique_id fallback). */
  registry: EntityRegistryEntry[];
  /** Window key (entry_id) of a window by its entry title. */
  keyOf(title: string): string;
  /** Entity id of a window role, by the window's entry title. */
  eid(title: string, role: keyof typeof ROLE_SUFFIX): string;
  /** The window's (first) physical cover. */
  coverOf(title: string): string;
}

export interface FixtureOptions {
  surface?: 'today' | 'legacy';
  /** Fixed "now" for sun.sun and next moves. */
  now?: string;
}

export const FIXTURE_NOW = '2026-09-29T10:40:00-06:00';

export function houseFixture(opts: FixtureOptions = {}): HouseFixture {
  const surface = opts.surface ?? 'today';
  const byTitle = new Map(WINDOW_ENTRIES.map((e) => [e.title, e]));
  const entryCovers = (e: SnapshotEntry): string[] =>
    ((e.options?.group ?? e.options?.entities ?? []) as string[]).slice();

  const floors = Object.fromEntries(FLOORS_AREAS.floors.map((f) => [f.floor_id, { ...f }]));
  const areas = Object.fromEntries(FLOORS_AREAS.areas.map((a) => [a.area_id, { ...a }]));
  const devices: Record<string, Record<string, unknown>> = {};
  for (const d of DEVICES) {
    devices[d.device_id] = {
      id: d.device_id,
      name: d.name,
      name_by_user: d.name_by_user,
      area_id: d.area_id,
      config_entries: d.config_entries,
    };
  }
  const entities: Record<string, Record<string, unknown>> = {};
  const states: Record<string, State> = {};
  for (const c of COVERS) {
    if (c.platform === 'adaptive_cover') continue; // the hub cover is a registry row
    devices[c.device_id] ??= {
      id: c.device_id,
      name: c.device_name,
      name_by_user: null,
      area_id: c.device_area_id,
    };
    entities[c.entity_id] = {
      entity_id: c.entity_id,
      platform: c.platform,
      device_id: c.device_id,
      area_id: c.registry_area_id,
    };
    states[c.entity_id] = {
      state: c.state_now,
      attributes: { current_position: c.current_position_now, device_class: 'shade' },
    };
  }

  const activeRows = REGISTRY.filter(
    (r) => r.platform === 'adaptive_cover' && !r.disabled_by && r.config_entry_id !== null,
  ).filter((r) => {
    const entry = ENTRIES.find((e) => e.entry_id === r.config_entry_id);
    return entry?.role !== 'disabled_legacy';
  });
  for (const r of activeRows) {
    entities[r.entity_id] = {
      entity_id: r.entity_id,
      platform: r.platform,
      device_id: r.device_id,
      area_id: r.area_id,
      hidden: !!r.hidden_by,
      ...(surface === 'today' ? { translation_key: translationKey(r) } : {}),
    };
  }
  for (const [id, st] of Object.entries(STATES)) {
    states[id] = { state: st.state, attributes: { ...st.attributes } };
  }
  states['cover.adaptive_cover_all'] ??= {
    state: 'open',
    attributes: { current_position: 1, covers: 15 },
  };
  const now = Date.parse(opts.now ?? FIXTURE_NOW);
  states['sun.sun'] = {
    state: 'above_horizon',
    attributes: {
      azimuth: 142.3,
      elevation: 38.4,
      next_setting: new Date(now + 8.7 * 3600_000).toISOString(),
      next_rising: new Date(now + 20 * 3600_000).toISOString(),
    },
  };

  const rowOf = (key: string, role: keyof typeof ROLE_SUFFIX): SnapshotRow | undefined =>
    activeRows.find(
      (r) => r.unique_id === `${key}_${ROLE_SUFFIX[role]}` && r.domain === ROLE_DOMAIN[role],
    );

  // Position attributes of today's surface, plus a plausible decision trace.
  for (const e of WINDOW_ENTRIES) {
    const pos = rowOf(e.entry_id, 'position');
    if (!pos) continue;
    const st = states[pos.entity_id];
    const covers = entryCovers(e);
    st.attributes.decision_trace = [
      'privacy: not configured',
      'climate: intermediate, presence unknown',
      'sun in view: tracking',
    ];
    st.attributes.intent ??= 'calculated';
    st.attributes.azimuth_window = e.options?.set_azimuth ?? null;
    if (surface === 'today') {
      st.attributes.window_key = e.entry_id;
      st.attributes.cover_entity = covers[0] ?? null;
      st.attributes.cover_type = e.data?.sensor_type ?? 'cover_blind';
      st.attributes.override_until = null;
      st.attributes.next_move = null;
    }
  }

  const hass = {
    states,
    entities,
    devices,
    areas,
    floors,
    config: { time_zone: 'America/Denver' },
    locale: { language: 'en', time_format: '12', time_zone: 'server' },
    language: 'en',
    callService: vi.fn(async () => undefined),
    callWS: vi.fn(async (msg: { type: string }) =>
      msg.type === 'config/entity_registry/list' ? activeRows.map((r) => ({ ...r })) : [],
    ),
    connection: { subscribeEvents: vi.fn(async () => () => undefined) },
  } as unknown as HouseTestHass;

  return {
    hass,
    registry: activeRows.map((r) => ({ ...r })),
    keyOf(title) {
      const e = byTitle.get(title);
      if (!e) throw new Error(`no window titled ${title}`);
      return e.entry_id;
    },
    eid(title, role) {
      const row = rowOf(this.keyOf(title), role);
      if (!row) throw new Error(`no ${role} for ${title}`);
      return row.entity_id;
    },
    coverOf(title) {
      return entryCovers(byTitle.get(title)!)[0];
    },
  };
}

/** The legacy surface after each window moved its cover once: the 1.13
 *  Position sensor names its covers only in `last_moves`. */
export function withLegacyMoves(fx: HouseFixture): HouseTestHass {
  const changes: Record<string, { attributes: Record<string, unknown> }> = {};
  for (const e of WINDOW_ENTRIES) {
    changes[fx.eid(e.title, 'position')] = {
      attributes: { last_moves: { [fx.coverOf(e.title)]: '07:02 -> 100% (solar)' } },
    };
  }
  return withStates(fx.hass, changes);
}

/** A copy of `hass` with some states replaced (new `states` object, so a
 *  card sees the change). Attributes merge into the existing ones. */
export function withStates<T extends HomeAssistant>(
  hass: T,
  changes: Record<string, { state?: string; attributes?: Record<string, unknown> }>,
): T {
  const states = { ...hass.states } as Record<string, State>;
  for (const [id, ch] of Object.entries(changes)) {
    const prev = states[id] ?? { state: 'unknown', attributes: {} };
    states[id] = {
      state: ch.state ?? prev.state,
      attributes: { ...prev.attributes, ...(ch.attributes ?? {}) },
    };
  }
  return { ...hass, states } as T;
}

/** The standard mixed house used across the tests:
 *  - "Master door" on hold for 72 more minutes (a manual move),
 *  - "Office north", "Office east", "Office door" on hold,
 *  - "Den west" off (Mode = Manual, Automatic control off),
 *  - the sun on the glass of the east and south windows. */
export function mixedHouse(fx: HouseFixture, nowIso = FIXTURE_NOW): HouseTestHass {
  const now = Date.parse(nowIso);
  const until = (mins: number) => new Date(now + mins * 60_000).toISOString();
  const changes: Record<string, { state?: string; attributes?: Record<string, unknown> }> = {};
  const hold = (title: string, mins: number) => {
    changes[fx.eid(title, 'manualOverride')] = { state: 'on', attributes: { until: until(mins) } };
  };
  hold('Master door', 72);
  hold('Office north', 200);
  hold('Office east', 200);
  hold('Office door', 200);
  changes[fx.eid('Den west', 'mode')] = { state: 'Manual' };
  changes[fx.eid('Den west', 'controlSwitch')] = { state: 'off' };
  for (const title of ['Master east', 'Master south', 'Family east', 'Family south', 'Den south']) {
    changes[fx.eid(title, 'sunInFront')] = { state: 'on' };
  }
  for (const title of ['Master east', 'Family east']) {
    changes[fx.eid(title, 'position')] = {
      state: '40',
      attributes: { intent: 'calculated', next_move: { time: until(25), position: 38 } },
    };
  }
  return withStates(fx.hass, changes);
}

export const HUB_MODE_SELECT = 'select.adaptive_cover_all_cover_control_mode';

/**
 * The P5 flip projected onto `hass` (default: the fixture's): every window's
 * Mode select offers auto / hold / off and shows the window's mode (a
 * "Manual" select or a latched Manual override become off / hold, the hold
 * keeping its `until`), the house select offers auto / hold / off / mixed,
 * and the window switches are hidden aliases.
 */
export function p5House(fx: HouseFixture, hass: HouseTestHass = fx.hass): HouseTestHass {
  const changes: Record<string, { state?: string; attributes?: Record<string, unknown> }> = {};
  const modes = new Set<string>();
  for (const e of WINDOW_ENTRIES) {
    let modeId: string;
    try {
      modeId = fx.eid(e.title, 'mode');
    } catch {
      continue;
    }
    const override = hass.states[fx.eid(e.title, 'manualOverride')];
    let mode = 'auto';
    let until: unknown = null;
    if (hass.states[modeId]?.state === 'Manual') mode = 'off';
    else if (override?.state === 'on') {
      mode = 'hold';
      until = override.attributes?.until ?? null;
    }
    modes.add(mode);
    changes[modeId] = { state: mode, attributes: { options: ['auto', 'hold', 'off'], until } };
  }
  changes[HUB_MODE_SELECT] = {
    state: modes.size === 1 ? [...modes][0] : 'mixed',
    attributes: { options: ['auto', 'hold', 'off', 'mixed'] },
  };
  const out = withStates(hass, changes);
  const entities: Record<string, Record<string, unknown>> = {};
  for (const [id, row] of Object.entries(out.entities)) {
    const hidden = row.platform === 'adaptive_cover' && id.startsWith('switch.');
    entities[id] = hidden ? { ...row, hidden: true } : row;
  }
  return { ...out, entities } as HouseTestHass;
}

export const HUB_DEVICE = 'd256706cec9e1aab19295d3b7c942f4c';
export const HUB_CLIMATE_SWITCH = 'switch.adaptive_cover_all_climate';

/** The house's Climate switch on the hub device (P5 flip), in `state`. */
export function withHubClimate(hass: HouseTestHass, state: 'on' | 'off'): HouseTestHass {
  const out = withStates(hass, { [HUB_CLIMATE_SWITCH]: { state, attributes: {} } });
  const entities = {
    ...out.entities,
    [HUB_CLIMATE_SWITCH]: {
      entity_id: HUB_CLIMATE_SWITCH,
      platform: 'adaptive_cover',
      device_id: HUB_DEVICE,
      area_id: null,
      translation_key: 'climate_on',
    },
  };
  return { ...out, entities } as HouseTestHass;
}
