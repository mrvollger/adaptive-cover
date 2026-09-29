// @vitest-environment node
/// <reference types="node" />
// Discovery against the sanitized snapshot of the live house
// (tests/fixtures/house_snapshot/, captured 2026-09-28 from adaptive_cover
// 1.13.5). Today every window is its own config entry. The snapshot is also
// projected into the shape the house takes after the P7 consolidation (one
// house config entry, windows as subentries) to check that every card config
// on the real `dashboard-shades` keeps resolving to the same entities.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';

import {
  createDiscoveryListMemo,
  discoverEntities,
  listWindows,
  windowRegistrySlice,
} from '../src/lib/entity-discovery';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';
import { windowRefsFromConfig } from '../src/lib/window-binding';
import { windowSettingsPath, windowSettingsTarget } from '../src/lib/settings-link';
import type { DiscoveredEntities } from '../src/types';

const SNAPSHOT = fileURLToPath(new URL('../../tests/fixtures/house_snapshot/', import.meta.url));
const load = <T>(name: string): T => JSON.parse(readFileSync(`${SNAPSHOT}${name}`, 'utf8')) as T;

interface SnapshotDevice {
  device_id: string;
  name: string | null;
  name_by_user: string | null;
  config_entries: string[];
}
interface SnapshotEntry {
  entry_id: string;
  title: string;
  role: 'window' | 'hub' | 'disabled_legacy';
}
interface CardConfig {
  type: string;
  entry_id?: string;
  entry_ids?: string[];
  cover?: string;
}
type State = { state: string; attributes: Record<string, unknown> };

const REGISTRY = load<{ entities: EntityRegistryEntry[] }>('entity_registry.json').entities;
const DEVICES = load<{ devices: SnapshotDevice[] }>('device_registry.json').devices;
const STATES = load<{ states: Record<string, State> }>('entity_states.json').states;
const ENTRIES = load<{ entries: SnapshotEntry[] }>('config_entries.json').entries;
const DASHBOARD = load<Record<string, unknown>>('dashboard_shades.json');

const WINDOW_ENTRIES = ENTRIES.filter((e) => e.role === 'window');
const HUB_ENTRY = ENTRIES.find((e) => e.role === 'hub')!;
const TITLES = Object.fromEntries(ENTRIES.map((e) => [e.entry_id, e.title]));

/** Every adaptive-cover card config on the live `dashboard-shades`. */
function dashboardCards(): CardConfig[] {
  const out: CardConfig[] = [];
  const walk = (o: unknown): void => {
    if (Array.isArray(o)) o.forEach(walk);
    else if (o && typeof o === 'object') {
      const rec = o as Record<string, unknown>;
      if (typeof rec.type === 'string' && rec.type.startsWith('custom:adaptive-cover')) {
        out.push(rec as unknown as CardConfig);
      }
      Object.values(rec).forEach(walk);
    }
  };
  walk(DASHBOARD);
  return out;
}
const TILES = dashboardCards().filter((c) => c.type === 'custom:adaptive-cover-tile-card');
const COMPASS = dashboardCards().find((c) => c.type === 'custom:adaptive-cover-sky-compass-card')!;

function makeHass(
  devices: SnapshotDevice[] = DEVICES,
  states: Record<string, State> = STATES,
): HomeAssistant {
  return {
    states,
    devices: Object.fromEntries(
      devices.map((d) => [
        d.device_id,
        {
          id: d.device_id,
          name: d.name,
          name_by_user: d.name_by_user,
          config_entries: d.config_entries,
        },
      ]),
    ),
  } as unknown as HomeAssistant;
}

const ROLES = [
  'target_position_sensor',
  'start_sensor',
  'end_sensor',
  'control_status_sensor',
  'sun_infront_binary',
  'manual_override_binary',
  'automatic_control_switch',
  'manual_toggle_switch',
  'climate_mode_switch',
  'reset_override_button',
];

/**
 * The house after the P7 consolidation: every window row moves to the house
 * (today's hub) entry as a subentry whose id differs from the window key
 * (a migrated window keeps its old entry_id as the key). Unique_ids, entity_ids
 * and device ids do not change.
 */
function consolidated(): { registry: EntityRegistryEntry[]; devices: SnapshotDevice[] } {
  const subentryOf = (entryId: string) => `sub_${entryId.toLowerCase()}`;
  const registry = REGISTRY.map((row) =>
    row.config_entry_id === HUB_ENTRY.entry_id
      ? { ...row }
      : {
          ...row,
          config_subentry_id: subentryOf(row.config_entry_id!),
          config_entry_id: HUB_ENTRY.entry_id,
        },
  );
  const devices = DEVICES.map((d) => ({ ...d, config_entries: [HUB_ENTRY.entry_id] }));
  return { registry, devices };
}

describe('house snapshot fixture', () => {
  it('has the shape the discovery tests expect', () => {
    expect(WINDOW_ENTRIES).toHaveLength(15);
    expect(REGISTRY).toHaveLength(318);
    expect(TILES).toHaveLength(15);
    expect(COMPASS.entry_ids).toHaveLength(15);
    // Today every window's rows carry its own config_entry_id.
    for (const e of WINDOW_ENTRIES) {
      expect(REGISTRY.some((r) => r.config_entry_id === e.entry_id)).toBe(true);
    }
  });
});

describe('discovery on today’s house (one config entry per window)', () => {
  const hass = makeHass();

  it.each(TILES.map((c) => [TITLES[c.entry_id!], c] as const))(
    'resolves the %s tile (legacy entry_id + cover) to its window',
    (_title, cfg) => {
      const d = discoverEntities(hass, cfg, REGISTRY)!;
      expect(d).not.toBeNull();
      expect(d.window_key).toBe(cfg.entry_id);
      expect(d.entry_title).toBe(TITLES[cfg.entry_id!]);
      expect(Object.keys(d.entities).sort()).toEqual([...ROLES].sort());
      // Every entity belongs to this window: its unique_id carries the key.
      const own = new Set(
        REGISTRY.filter((r) => r.unique_id.startsWith(`${cfg.entry_id}_`)).map((r) => r.entity_id),
      );
      for (const id of Object.values(d.entities)) expect(own.has(id!)).toBe(true);
      expect(d.config_entry_id).toBe(cfg.entry_id);
      expect(d.config_subentry_id).toBeNull();
      expect(windowSettingsPath(windowSettingsTarget(d))).toBe(
        `/config/integrations/integration/adaptive_cover#config_entry=${cfg.entry_id}`,
      );
    },
  );

  it('resolves `window:` to the same entities as the legacy `entry_id:`', () => {
    for (const cfg of TILES) {
      const legacy = discoverEntities(hass, { entry_id: cfg.entry_id }, REGISTRY)!;
      const modern = discoverEntities(hass, { window: cfg.entry_id }, REGISTRY)!;
      expect(modern.entities).toEqual(legacy.entities);
      expect(modern.device_id).toBe(legacy.device_id);
    }
  });

  it('gives the 15 tiles 15 distinct windows', () => {
    const keys = TILES.map((c) => discoverEntities(hass, c, REGISTRY)!.window_key);
    expect(new Set(keys).size).toBe(15);
  });

  it('resolves the sky compass’s 15 entry_ids with none missing', () => {
    const memo = createDiscoveryListMemo();
    const { list, missing } = memo(hass, windowRefsFromConfig(COMPASS), REGISTRY);
    expect(missing).toEqual([]);
    expect(list.map((d) => d.window_key)).toEqual(COMPASS.entry_ids);
  });

  it('does not treat the hub entry as a window', () => {
    expect(discoverEntities(hass, { window: HUB_ENTRY.entry_id }, REGISTRY)).toBeNull();
    expect(discoverEntities(hass, { entry_id: HUB_ENTRY.entry_id }, REGISTRY)).toBeNull();
  });

  it('lists the 15 windows (not the hub) with their entry titles for the editors', () => {
    const windows = listWindows(hass, REGISTRY);
    expect(windows.map((w) => w.window_key).sort()).toEqual(
      WINDOW_ENTRIES.map((e) => e.entry_id).sort(),
    );
    for (const w of windows) expect(w.title).toBe(TITLES[w.window_key]);
  });

  it('slices exactly the 21 registry rows of one window', () => {
    const cfg = TILES[0];
    const slice = windowRegistrySlice(hass, cfg, REGISTRY);
    expect(slice).toHaveLength(21);
    expect(slice.every((r) => r.config_entry_id === cfg.entry_id)).toBe(true);
  });

  it('cannot resolve a `cover:` binding before the integration publishes cover_entity', () => {
    // 1.13.5 exposes no cover attributes and the capture came right after a
    // restart (empty last_moves), so a bare `cover:` has nothing to match yet.
    const tile = TILES[0];
    expect(discoverEntities(hass, { cover: tile.cover }, REGISTRY)).toBeNull();
  });
});

describe('discovery on the consolidated house (windows as subentries of one entry)', () => {
  const { registry, devices } = consolidated();
  const hass = makeHass(devices);

  it('really removes the per-window config_entry_id (guards the projection)', () => {
    for (const cfg of TILES) {
      expect(registry.some((r) => r.config_entry_id === cfg.entry_id)).toBe(false);
    }
    const houseRows = registry.filter((r) => r.config_entry_id === HUB_ENTRY.entry_id);
    expect(houseRows).toHaveLength(318);
  });

  it('resolves every legacy dashboard tile to the same entities as today', () => {
    const today = makeHass();
    for (const cfg of TILES) {
      const before = discoverEntities(today, cfg, REGISTRY)!;
      const after = discoverEntities(hass, cfg, registry)!;
      expect(after).not.toBeNull();
      expect(after.window_key).toBe(before.window_key);
      expect(after.entities).toEqual(before.entities);
      expect(after.entry_title).toBe(before.entry_title);
      expect(after.device_id).toBe(before.device_id);
    }
  });

  it('points the settings link at the house entry', () => {
    const d = discoverEntities(hass, TILES[0], registry)!;
    expect(d.config_entry_id).toBe(HUB_ENTRY.entry_id);
    expect(d.config_subentry_id).toBe(`sub_${TILES[0].entry_id!.toLowerCase()}`);
    expect(windowSettingsTarget(d)).toEqual({
      kind: 'subentry',
      entry_id: HUB_ENTRY.entry_id,
      subentry_id: d.config_subentry_id,
    });
    expect(windowSettingsPath(windowSettingsTarget(d))).toBe(
      `/config/integrations/integration/adaptive_cover#config_entry=${HUB_ENTRY.entry_id}`,
    );
  });

  it('keeps the sky compass whole and the editor list at 15 windows', () => {
    const memo = createDiscoveryListMemo();
    const { list, missing } = memo(hass, windowRefsFromConfig(COMPASS), registry);
    expect(missing).toEqual([]);
    expect(list).toHaveLength(15);
    expect(listWindows(hass, registry)).toHaveLength(15);
  });

  it('does not resolve the house entry itself as a window', () => {
    expect(discoverEntities(hass, { entry_id: HUB_ENTRY.entry_id }, registry)).toBeNull();
  });
});

describe('discovery on the house once the Position sensor publishes window attributes', () => {
  // The backend change that ships with this card: `window_key`, `cover_entity`
  // and `cover_type` on each Position sensor.
  const coverOf = Object.fromEntries(TILES.map((c) => [c.entry_id!, c.cover!]));
  const states: Record<string, State> = { ...STATES };
  for (const row of REGISTRY) {
    if (!row.unique_id.endsWith('_Cover Position')) continue;
    const key = row.unique_id.slice(0, -'_Cover Position'.length);
    const st = STATES[row.entity_id];
    states[row.entity_id] = {
      ...st,
      attributes: {
        ...st.attributes,
        window_key: key,
        cover_entity: coverOf[key],
        cover_type: 'cover_blind',
      },
    };
  }
  const { registry, devices } = consolidated();
  const hass = makeHass(devices, states);

  it.each(TILES.map((c) => [c.cover!, c] as const))(
    'binds `cover: %s` to the same window as the dashboard tile',
    (cover, cfg) => {
      const byCover = discoverEntities(hass, { cover }, registry) as DiscoveredEntities;
      const byEntry = discoverEntities(hass, cfg, registry) as DiscoveredEntities;
      expect(byCover.window_key).toBe(cfg.entry_id);
      expect(byCover.entities).toEqual(byEntry.entities);
      expect(byCover.managed_covers).toEqual([cover]);
    },
  );

  it('offers each window with its cover in the editor list', () => {
    const windows = listWindows(hass, registry);
    for (const w of windows) expect(w.cover).toBe(coverOf[w.window_key]);
  });
});
