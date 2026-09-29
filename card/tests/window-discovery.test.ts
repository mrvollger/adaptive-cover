// Window discovery without `config_entry_id`: attribute-first resolution,
// the unique_id-prefix fallback, `cover:` bindings, legacy `entry_id:`
// configs, and a registry shaped like the house after the P7 consolidation
// (one house config entry; windows are subentries). The live-house snapshot
// is covered in house-snapshot-discovery.test.ts.
import { describe, it, expect } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';

import {
  createDiscoveryMemo,
  discoverEntities,
  listWindows,
  windowRegistrySlice,
} from '../src/lib/entity-discovery';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';
import {
  configuredWindowKey,
  windowRefFromConfig,
  windowRefId,
  windowRefLabel,
  windowRefsFromConfig,
  withWindowKey,
} from '../src/lib/window-binding';
import { windowSettingsPath, windowSettingsTarget } from '../src/lib/settings-link';

type State = { state: string; attributes: Record<string, unknown> };

/** The ten role entities of one window, keyed by unique_id prefix `key`. */
function windowRows(
  key: string,
  slug: string,
  owner: { config_entry_id: string; config_subentry_id?: string | null; device_id?: string },
): EntityRegistryEntry[] {
  const row = (entity_id: string, suffix: string): EntityRegistryEntry => ({
    entity_id,
    unique_id: `${key}_${suffix}`,
    platform: 'adaptive_cover',
    config_entry_id: owner.config_entry_id,
    config_subentry_id: owner.config_subentry_id ?? null,
    device_id: owner.device_id ?? `dev_${slug}`,
  });
  return [
    row(`sensor.${slug}_cover_position`, 'Cover Position'),
    row(`sensor.${slug}_start_sun`, 'Start Sun'),
    row(`sensor.${slug}_end_sun`, 'End Sun'),
    row(`sensor.${slug}_control_method`, 'Control Method'),
    row(`binary_sensor.${slug}_sun_infront`, 'Sun Infront'),
    row(`binary_sensor.${slug}_manual_override`, 'Manual Override'),
    row(`switch.${slug}_toggle_control`, 'Toggle Control'),
    row(`switch.${slug}_manual_override`, 'Manual Override'),
    row(`switch.${slug}_climate_mode`, 'Climate Mode'),
    row(`button.${slug}_reset_manual_override`, 'Reset Manual Override'),
    // Entities the card does not bind to still share the prefix.
    row(`select.${slug}_mode`, 'mode_select'),
  ];
}

const HOUSE = '01HOUSE';

/** The hub's own entities: not a window (no `{key}_Cover Position`). */
const HUB_ROWS: EntityRegistryEntry[] = [
  {
    entity_id: 'cover.adaptive_cover_all',
    unique_id: 'adaptive_cover_hub_cover',
    platform: 'adaptive_cover',
    config_entry_id: HOUSE,
    device_id: 'dev_house',
  },
  {
    entity_id: 'button.adaptive_cover_all_reset_all_manual_overrides',
    unique_id: 'adaptive_cover_hub_reset_all',
    platform: 'adaptive_cover',
    config_entry_id: HOUSE,
    device_id: 'dev_house',
  },
];

// ---------------------------------------------------------------------------
// (b) Subentry-shaped registry: every row has the house config_entry_id.
// "Office door" was migrated (key = its old entry_id, subentry id differs);
// "Den west" was added after P7 (key = its subentry id).
// ---------------------------------------------------------------------------
const MIGRATED_KEY = '01OFFICEDOOROLDENTRY';
const MIGRATED_SUB = '01OFFICEDOORSUBENTRY';
const NEW_KEY = '01DENWESTSUBENTRY';

function subentryRegistry(): EntityRegistryEntry[] {
  return [
    ...HUB_ROWS,
    ...windowRows(MIGRATED_KEY, 'office_door', {
      config_entry_id: HOUSE,
      config_subentry_id: MIGRATED_SUB,
    }),
    ...windowRows(NEW_KEY, 'den_west', { config_entry_id: HOUSE, config_subentry_id: NEW_KEY }),
    {
      entity_id: 'cover.office_door_shade',
      unique_id: 'zha-office-door',
      platform: 'zha',
      config_entry_id: 'zha_entry',
      device_id: 'dev_zha',
    },
  ];
}

function subentryHass(states: Record<string, State> = {}): HomeAssistant {
  return {
    states,
    devices: {
      dev_office_door: {
        id: 'dev_office_door',
        name: 'Office door',
        name_by_user: null,
        config_entries: [HOUSE],
      },
      dev_den_west: {
        id: 'dev_den_west',
        name: 'Den west',
        name_by_user: 'Den west window',
        config_entries: [HOUSE],
      },
      dev_house: { id: 'dev_house', name: 'Adaptive Cover All', config_entries: [HOUSE] },
    },
  } as unknown as HomeAssistant;
}

describe('(b) subentry-shaped registry: one house config_entry_id', () => {
  const registry = subentryRegistry();

  it('resolves a migrated window by its window key', () => {
    const d = discoverEntities(subentryHass(), { window: MIGRATED_KEY }, registry)!;
    expect(d.window_key).toBe(MIGRATED_KEY);
    expect(d.entry_title).toBe('Office door');
    expect(d.entities.target_position_sensor).toBe('sensor.office_door_cover_position');
    expect(d.entities.reset_override_button).toBe('button.office_door_reset_manual_override');
    // Nothing from the other window or the hub leaks in.
    expect(Object.values(d.entities).every((id) => id!.includes('office_door'))).toBe(true);
    expect(d.config_entry_id).toBe(HOUSE);
    expect(d.config_subentry_id).toBe(MIGRATED_SUB);
  });

  it('resolves a legacy `entry_id:` tile of a migrated window (entry_id == window key)', () => {
    const legacy = discoverEntities(subentryHass(), { entry_id: MIGRATED_KEY }, registry)!;
    const modern = discoverEntities(subentryHass(), { window: MIGRATED_KEY }, registry)!;
    expect(legacy.entities).toEqual(modern.entities);
  });

  it('resolves a window added after the consolidation (key == subentry id)', () => {
    const d = discoverEntities(subentryHass(), { window: NEW_KEY }, registry)!;
    expect(d.window_key).toBe(NEW_KEY);
    expect(d.entry_title).toBe('Den west window'); // name_by_user wins
    expect(d.entities.target_position_sensor).toBe('sensor.den_west_cover_position');
  });

  it('does not resolve the house entry id as a window', () => {
    // Filtering on config_entry_id would have matched every window here.
    expect(discoverEntities(subentryHass(), { entry_id: HOUSE }, registry)).toBeNull();
    expect(discoverEntities(subentryHass(), { window: HOUSE }, registry)).toBeNull();
  });

  it('does not resolve a subentry id that is not the window key', () => {
    // A migrated window keeps its old entry_id as key; its subentry id is not a binding key.
    expect(discoverEntities(subentryHass(), { window: MIGRATED_SUB }, registry)).toBeNull();
  });

  it('lists both windows (not the hub) for the editors', () => {
    expect(listWindows(subentryHass(), registry)).toEqual([
      { window_key: NEW_KEY, title: 'Den west window' },
      { window_key: MIGRATED_KEY, title: 'Office door' },
    ]);
  });

  it('slices only the rows of the resolved window', () => {
    const slice = windowRegistrySlice(subentryHass(), { window: MIGRATED_KEY }, registry);
    expect(slice).toHaveLength(11);
    expect(slice.every((r) => r.unique_id.startsWith(`${MIGRATED_KEY}_`))).toBe(true);
  });

  it('links a subentry window’s settings to its house entry', () => {
    const d = discoverEntities(subentryHass(), { window: NEW_KEY }, registry)!;
    expect(windowSettingsTarget(d)).toEqual({
      kind: 'subentry',
      entry_id: HOUSE,
      subentry_id: NEW_KEY,
    });
    expect(windowSettingsPath(windowSettingsTarget(d))).toBe(
      `/config/integrations/integration/adaptive_cover#config_entry=${HOUSE}`,
    );
  });
});

// ---------------------------------------------------------------------------
// (c) Attribute-first resolution.
// ---------------------------------------------------------------------------
describe('(c) attribute-first resolution', () => {
  // Two legacy windows (one entry each), so the only link between a key and a
  // sensor that disagree is the attribute.
  const registry = [
    ...windowRows('entA', 'alpha', { config_entry_id: 'entA' }),
    ...windowRows('entB', 'beta', { config_entry_id: 'entB' }),
  ];

  it('prefers the Position sensor whose window_key attribute matches over the unique_id prefix', () => {
    const hass = {
      states: {
        // The alpha sensor claims key "entB"; the beta sensor publishes nothing.
        'sensor.alpha_cover_position': { state: '10', attributes: { window_key: 'entB' } },
        'sensor.beta_cover_position': { state: '20', attributes: {} },
      },
    } as unknown as HomeAssistant;
    const d = discoverEntities(hass, { window: 'entB' }, registry)!;
    expect(d.entities.target_position_sensor).toBe('sensor.alpha_cover_position');
    expect(d.window_key).toBe('entB');
  });

  it('falls back to the unique_id prefix when no sensor publishes window_key', () => {
    const hass = { states: {} } as unknown as HomeAssistant;
    const d = discoverEntities(hass, { window: 'entB' }, registry)!;
    expect(d.entities.target_position_sensor).toBe('sensor.beta_cover_position');
  });

  it('reports the attribute window_key when a cover binding resolves', () => {
    const hass = {
      states: {
        'sensor.beta_cover_position': {
          state: '20',
          attributes: { window_key: 'entB', cover_entity: 'cover.beta' },
        },
      },
    } as unknown as HomeAssistant;
    const d = discoverEntities(hass, { cover: 'cover.beta' }, registry)!;
    expect(d.window_key).toBe('entB');
    expect(d.entities.target_position_sensor).toBe('sensor.beta_cover_position');
  });

  it('binds `cover:` through cover_entity before cover_entities membership', () => {
    const hass = {
      states: {
        // alpha lists cover.shared as a secondary cover; beta names it as its cover.
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: {
            cover_entity: 'cover.alpha',
            cover_entities: ['cover.alpha', 'cover.shared'],
          },
        },
        'sensor.beta_cover_position': { state: '20', attributes: { cover_entity: 'cover.shared' } },
      },
    } as unknown as HomeAssistant;
    expect(discoverEntities(hass, { cover: 'cover.shared' }, registry)!.window_key).toBe('entB');
  });

  it('binds `cover:` through cover_entities when no sensor names it as its cover', () => {
    const hass = {
      states: {
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: { cover_entity: 'cover.a1', cover_entities: ['cover.a1', 'cover.a2'] },
        },
      },
    } as unknown as HomeAssistant;
    const d = discoverEntities(hass, { cover: 'cover.a2' }, registry)!;
    expect(d.window_key).toBe('entA');
    expect(d.managed_covers).toEqual(['cover.a1', 'cover.a2']);
  });

  it('uses last_moves / move_blocked_by only for sensors without cover attributes', () => {
    const hass = {
      states: {
        // alpha publishes its cover, so its stale last_moves key is ignored.
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: { cover_entity: 'cover.alpha', last_moves: { 'cover.old': 'x' } },
        },
        // beta is an integration without cover attributes.
        'sensor.beta_cover_position': {
          state: '20',
          attributes: { move_blocked_by: { 'cover.old': 'position_delta' } },
        },
      },
    } as unknown as HomeAssistant;
    expect(discoverEntities(hass, { cover: 'cover.old' }, registry)!.window_key).toBe('entB');
  });

  it('returns null for a cover no window controls', () => {
    const hass = {
      states: {
        'sensor.alpha_cover_position': { state: '1', attributes: { cover_entity: 'c.a' } },
      },
    } as unknown as HomeAssistant;
    expect(discoverEntities(hass, { cover: 'cover.nowhere' }, registry)).toBeNull();
  });

  it('takes managed covers from the attributes, primary first, over last_moves', () => {
    const hass = {
      states: {
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: {
            cover_entity: 'cover.main',
            cover_entities: ['cover.side', 'cover.main'],
            last_moves: { 'cover.ghost': 'x' },
          },
        },
      },
    } as unknown as HomeAssistant;
    const d = discoverEntities(hass, { window: 'entA' }, registry)!;
    expect(d.managed_covers).toEqual(['cover.main', 'cover.side']);
  });

  it('takes the cover type from the cover_type attribute', () => {
    const hass = {
      states: {
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: { cover_entity: 'cover.awn', cover_type: 'cover_awning' },
        },
        // Tilt-only cover state would have inferred cover_tilt without the attribute.
        'cover.awn': { state: 'open', attributes: { current_tilt_position: 40 } },
      },
    } as unknown as HomeAssistant;
    expect(discoverEntities(hass, { window: 'entA' }, registry)!.cover_type).toBe('cover_awning');
  });

  it('ignores an unknown cover_type value and falls back to inference', () => {
    const hass = {
      states: {
        'sensor.alpha_cover_position': {
          state: '10',
          attributes: { cover_entity: 'cover.t', cover_type: 'venetian?' },
        },
        'cover.t': { state: 'open', attributes: { current_tilt_position: 40 } },
      },
    } as unknown as HomeAssistant;
    expect(discoverEntities(hass, { window: 'entA' }, registry)!.cover_type).toBe('cover_tilt');
  });

  it('re-resolves a `cover:` binding when the Position attributes move the cover', () => {
    const memo = createDiscoveryMemo();
    const states: Record<string, State> = {
      'sensor.alpha_cover_position': { state: '10', attributes: { cover_entity: 'cover.x' } },
      'sensor.beta_cover_position': { state: '20', attributes: { cover_entity: 'cover.y' } },
    };
    const first = memo({ states } as unknown as HomeAssistant, { cover: 'cover.x' }, registry)!;
    expect(first.window_key).toBe('entA');
    const moved = {
      states: {
        'sensor.alpha_cover_position': { state: '10', attributes: { cover_entity: 'cover.y' } },
        'sensor.beta_cover_position': { state: '20', attributes: { cover_entity: 'cover.x' } },
      },
    } as unknown as HomeAssistant;
    expect(memo(moved, { cover: 'cover.x' }, registry)!.window_key).toBe('entB');
  });
});

// ---------------------------------------------------------------------------
// (d) Legacy `entry_id:` configs on today's registry (one entry per window).
// ---------------------------------------------------------------------------
describe('(d) legacy entry_id configs', () => {
  const registry = [
    ...HUB_ROWS,
    ...windowRows('01MASTEREAST', 'master_east', { config_entry_id: '01MASTEREAST' }),
    ...windowRows('01MASTERDOOR', 'master_door', { config_entry_id: '01MASTERDOOR' }),
  ];
  const hass = { states: {} } as unknown as HomeAssistant;

  it('resolves exactly like `window:`', () => {
    const legacy = discoverEntities(hass, { entry_id: '01MASTERDOOR' }, registry)!;
    const modern = discoverEntities(hass, { window: '01MASTERDOOR' }, registry)!;
    expect(legacy).toEqual(modern);
    expect(legacy.entry_id).toBe('01MASTERDOOR');
  });

  it('keeps an `entry_id` + `cover` tile bound to the entry (cover only picks the controls)', () => {
    // cover.master_east belongs to the other window; the entry_id still wins.
    const d = discoverEntities(
      hass,
      { entry_id: '01MASTERDOOR', cover: 'cover.master_east' },
      registry,
    )!;
    expect(d.window_key).toBe('01MASTERDOOR');
  });

  it('prefers `window` over a stale `entry_id` in the same config', () => {
    const d = discoverEntities(
      hass,
      { window: '01MASTEREAST', entry_id: '01MASTERDOOR' },
      registry,
    )!;
    expect(d.window_key).toBe('01MASTEREAST');
  });

  it('links the settings button to the window’s own config entry', () => {
    const d = discoverEntities(hass, { entry_id: '01MASTEREAST' }, registry)!;
    expect(windowSettingsTarget(d)).toEqual({ kind: 'entry', entry_id: '01MASTEREAST' });
  });
});

describe('window-binding helpers', () => {
  it('parses single-window configs with window > entry_id > cover precedence', () => {
    expect(windowRefFromConfig({ window: 'w', entry_id: 'e', cover: 'cover.c' })).toEqual({
      kind: 'window',
      key: 'w',
    });
    expect(windowRefFromConfig({ entry_id: 'e', cover: 'cover.c' })).toEqual({
      kind: 'entry',
      key: 'e',
    });
    expect(windowRefFromConfig({ cover: 'cover.c' })).toEqual({
      kind: 'cover',
      entity_id: 'cover.c',
    });
    expect(windowRefFromConfig({ window: '', entry_id: '' })).toBeNull();
    expect(windowRefFromConfig(undefined)).toBeNull();
  });

  it('parses multi-window configs in windows, covers, entry_ids order', () => {
    expect(
      windowRefsFromConfig({ entry_ids: ['e'], covers: ['cover.c'], windows: ['w', ''] }),
    ).toEqual([
      { kind: 'window', key: 'w' },
      { kind: 'cover', entity_id: 'cover.c' },
      { kind: 'entry', key: 'e' },
    ]);
  });

  it('gives a window and a legacy entry with the same key the same id', () => {
    expect(windowRefId({ kind: 'window', key: 'k' })).toBe(
      windowRefId({ kind: 'entry', key: 'k' }),
    );
    expect(windowRefId({ kind: 'cover', entity_id: 'k' })).not.toBe('k');
    expect(windowRefLabel({ kind: 'cover', entity_id: 'cover.c' })).toBe('cover.c');
  });

  it('rewrites a legacy binding to `window` and keeps `cover`', () => {
    expect(withWindowKey({ entry_id: 'old', cover: 'cover.c' }, 'new')).toEqual({
      window: 'new',
      cover: 'cover.c',
    });
    expect(configuredWindowKey({ entry_id: 'old' })).toBe('old');
    expect(configuredWindowKey({ window: 'w', entry_id: 'old' })).toBe('w');
    expect(configuredWindowKey({ cover: 'cover.c' })).toBe('');
  });
});
