import { describe, it, expect } from 'vitest';
import {
  discoverEntities,
  createDiscoveryMemo,
  createDiscoveryListMemo,
} from '../src/lib/entity-discovery';
import type { HomeAssistant } from 'custom-card-helpers';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

const ENTRY_ID = 'entry1';

// The Adaptive Cover integration's unique_ids are `${entry_id}_${suffix}` where
// the suffixes contain SPACES ('Cover Position', 'Start Sun', …) — copied
// verbatim from the integration's sensor/binary_sensor/switch/button modules.
function makeRegistry(): EntityRegistryEntry[] {
  const entry = (entity_id: string, suffix: string): EntityRegistryEntry => ({
    entity_id,
    unique_id: `${ENTRY_ID}_${suffix}`,
    platform: 'adaptive_cover',
    config_entry_id: ENTRY_ID,
    device_id: 'ac_device_living',
  });
  return [
    entry('sensor.living_room_blinds_cover_position', 'Cover Position'),
    entry('sensor.living_room_blinds_start_sun', 'Start Sun'),
    entry('sensor.living_room_blinds_end_sun', 'End Sun'),
    entry('sensor.living_room_blinds_control_method', 'Control Method'),
    entry('binary_sensor.living_room_blinds_sun_infront', 'Sun Infront'),
    entry('binary_sensor.living_room_blinds_manual_override', 'Manual Override'),
    entry('switch.living_room_blinds_toggle_control', 'Toggle Control'),
    entry('switch.living_room_blinds_manual_override', 'Manual Override'),
    entry('switch.living_room_blinds_climate_mode', 'Climate Mode'),
    entry('button.living_room_blinds_reset_manual_override', 'Reset Manual Override'),
    // Unrelated foreign entity — must be ignored
    {
      entity_id: 'sensor.kitchen_light',
      unique_id: 'kitchen_light_brightness',
      platform: 'hue',
      config_entry_id: 'other_entry',
      device_id: 'other_device',
    },
  ];
}

function makeHass(): HomeAssistant {
  const h: unknown = {
    devices: {
      ac_device_living: {
        id: 'ac_device_living',
        name: 'Living Room Blinds',
        config_entries: [ENTRY_ID],
      },
    },
    states: {
      'sensor.living_room_blinds_cover_position': {
        state: '42',
        attributes: {
          intent: 'calculated',
          last_moves: { 'cover.living_room_left': '07:00 -> 42% (calculated)' },
          move_blocked_by: { 'cover.living_room_right': 'position_delta' },
        },
      },
      'sensor.living_room_blinds_control_method': { state: 'intermediate', attributes: {} },
      'cover.living_room_left': { state: 'open', attributes: { current_position: 40 } },
      'cover.living_room_right': { state: 'open', attributes: { current_position: 38 } },
    },
  };
  return h as HomeAssistant;
}

const CONFIG = { type: 'custom:adaptive-cover-card', entry_id: ENTRY_ID };

describe('discoverEntities (unique_id based)', () => {
  it('maps every Adaptive Cover entity by (platform, unique_id suffix)', () => {
    const d = discoverEntities(makeHass(), CONFIG, makeRegistry());
    expect(d).not.toBeNull();
    expect(d!.entry_title).toBe('Living Room Blinds');
    expect(d!.entities.target_position_sensor).toBe('sensor.living_room_blinds_cover_position');
    expect(d!.entities.start_sensor).toBe('sensor.living_room_blinds_start_sun');
    expect(d!.entities.end_sensor).toBe('sensor.living_room_blinds_end_sun');
    expect(d!.entities.control_status_sensor).toBe('sensor.living_room_blinds_control_method');
    expect(d!.entities.sun_infront_binary).toBe('binary_sensor.living_room_blinds_sun_infront');
    expect(d!.entities.manual_override_binary).toBe(
      'binary_sensor.living_room_blinds_manual_override',
    );
    expect(d!.entities.automatic_control_switch).toBe(
      'switch.living_room_blinds_toggle_control',
    );
    expect(d!.entities.manual_toggle_switch).toBe('switch.living_room_blinds_manual_override');
    expect(d!.entities.climate_mode_switch).toBe('switch.living_room_blinds_climate_mode');
    expect(d!.entities.reset_override_button).toBe(
      'button.living_room_blinds_reset_manual_override',
    );
    expect(d!.device_id).toBe('ac_device_living');
  });

  it('disambiguates the Manual Override binary sensor vs switch by platform', () => {
    const d = discoverEntities(makeHass(), CONFIG, makeRegistry());
    expect(d!.entities.manual_override_binary).toMatch(/^binary_sensor\./);
    expect(d!.entities.manual_toggle_switch).toMatch(/^switch\./);
  });

  it('discovers managed covers from the union of last_moves and move_blocked_by keys, sorted', () => {
    const d = discoverEntities(makeHass(), CONFIG, makeRegistry());
    expect(d!.managed_covers).toEqual(['cover.living_room_left', 'cover.living_room_right']);
  });

  it('leaves managed_covers empty before the integration records any move', () => {
    const hass = makeHass() as unknown as { states: Record<string, unknown> };
    hass.states['sensor.living_room_blinds_cover_position'] = { state: '42', attributes: {} };
    const d = discoverEntities(hass as unknown as HomeAssistant, CONFIG, makeRegistry());
    expect(d!.managed_covers).toEqual([]);
  });

  it('defaults cover_type to cover_blind', () => {
    const d = discoverEntities(makeHass(), CONFIG, makeRegistry());
    expect(d!.cover_type).toBe('cover_blind');
  });

  it('marks the entry cover_tilt only when every managed cover is tilt-only', () => {
    const hass = makeHass() as unknown as { states: Record<string, Record<string, unknown>> };
    hass.states['cover.living_room_left'] = {
      state: 'open',
      attributes: { current_tilt_position: 30 },
    };
    hass.states['cover.living_room_right'] = {
      state: 'open',
      attributes: { current_tilt_position: 60 },
    };
    const d = discoverEntities(hass as unknown as HomeAssistant, CONFIG, makeRegistry());
    expect(d!.cover_type).toBe('cover_tilt');
  });

  it('stays cover_blind when a managed cover reports current_position alongside tilt', () => {
    const hass = makeHass() as unknown as { states: Record<string, Record<string, unknown>> };
    hass.states['cover.living_room_left'] = {
      state: 'open',
      attributes: { current_tilt_position: 30, current_position: 40 },
    };
    hass.states['cover.living_room_right'] = {
      state: 'open',
      attributes: { current_tilt_position: 60 },
    };
    const d = discoverEntities(hass as unknown as HomeAssistant, CONFIG, makeRegistry());
    expect(d!.cover_type).toBe('cover_blind');
  });

  it('ignores non-adaptive_cover entities even if they share the config_entry_id', () => {
    const reg = makeRegistry();
    reg.push({
      entity_id: 'sensor.random_other',
      unique_id: `${ENTRY_ID}_Cover Position`, // looks like ours!
      platform: 'some_other_integration',
      config_entry_id: ENTRY_ID,
      device_id: null,
    });
    const d = discoverEntities(makeHass(), CONFIG, reg);
    expect(d!.entities.target_position_sensor).toBe('sensor.living_room_blinds_cover_position');
  });

  it('returns null when no adaptive_cover entity has the given config_entry_id', () => {
    expect(
      discoverEntities(
        makeHass(),
        { type: 'custom:adaptive-cover-card', entry_id: 'nonexistent' },
        makeRegistry(),
      ),
    ).toBeNull();
  });

  it('returns null when the registry is empty', () => {
    expect(discoverEntities(makeHass(), CONFIG, [])).toBeNull();
  });

  it('still succeeds if hass.devices is missing — only loses the display title', () => {
    const hass = { states: {} } as HomeAssistant;
    const d = discoverEntities(hass, CONFIG, makeRegistry());
    expect(d).not.toBeNull();
    expect(d!.entry_title).toBe(ENTRY_ID);
    expect(d!.entities.target_position_sensor).toBe('sensor.living_room_blinds_cover_position');
  });

  it('skips entries whose unique_id does not start with the entry_id prefix', () => {
    const reg = makeRegistry();
    reg.push({
      entity_id: 'sensor.stale_prefix',
      unique_id: 'some_other_prefix_Cover Position',
      platform: 'adaptive_cover',
      config_entry_id: ENTRY_ID,
      device_id: 'ac_device_living',
    });
    const d = discoverEntities(makeHass(), CONFIG, reg);
    expect(d!.entities.target_position_sensor).toBe('sensor.living_room_blinds_cover_position');
  });
});

describe('createDiscoveryMemo', () => {
  it('returns discovery result on first call', () => {
    const memo = createDiscoveryMemo();
    const result = memo(makeHass(), CONFIG, makeRegistry());
    expect(result).not.toBeNull();
    expect(result!.entry_id).toBe(ENTRY_ID);
  });

  it('returns cached result when all inputs are reference-equal', () => {
    const memo = createDiscoveryMemo();
    const hass = makeHass();
    const registry = makeRegistry();
    const first = memo(hass, CONFIG, registry);
    const second = memo(hass, CONFIG, registry);
    expect(second).toBe(first); // same reference — no recompute
  });

  it('recomputes when the registry reference changes', () => {
    const memo = createDiscoveryMemo();
    const hass = makeHass();
    const first = memo(hass, CONFIG, makeRegistry());
    const second = memo(hass, CONFIG, makeRegistry()); // new array, same content
    expect(second).not.toBe(first);
  });

  it('recomputes when entry_id changes', () => {
    const memo = createDiscoveryMemo();
    const hass = makeHass();
    const registry = makeRegistry();
    memo(hass, CONFIG, registry);
    const result2 = memo(hass, { ...CONFIG, entry_id: 'other_entry' }, registry);
    expect(result2).toBeNull();
  });

  it('returns the SAME result reference across a new hass that shares the relevant state refs', () => {
    // HA hands over a fresh `hass` object on every state tick. As long as the registry,
    // `hass.devices`, and the states discovery reads (Cover Position + Control Method)
    // are reference-equal, the memo must return the same object so child props stay stable.
    const memo = createDiscoveryMemo();
    const registry = makeRegistry();
    const hass1 = makeHass() as unknown as {
      devices: unknown;
      states: Record<string, unknown>;
    };
    const first = memo(hass1 as unknown as HomeAssistant, CONFIG, registry);

    const hass2 = {
      devices: hass1.devices,
      states: {
        ...hass1.states,
        'light.kitchen': { state: 'on', attributes: {} },
      },
    } as unknown as HomeAssistant;
    const second = memo(hass2, CONFIG, registry);
    expect(second).toBe(first); // unrelated tick → no recompute, stable reference
  });

  it('recomputes when the Cover Position state object reference changes', () => {
    const memo = createDiscoveryMemo();
    const registry = makeRegistry();
    const hass1 = makeHass() as unknown as { states: Record<string, unknown>; devices: unknown };
    const first = memo(hass1 as unknown as HomeAssistant, CONFIG, registry);

    // Same registry/devices, but the position sensor is a new object with a
    // third managed cover recorded in last_moves.
    const hass2 = {
      devices: hass1.devices,
      states: {
        ...hass1.states,
        'sensor.living_room_blinds_cover_position': {
          state: '42',
          attributes: {
            last_moves: {
              'cover.living_room_left': 'x',
              'cover.living_room_right': 'x',
              'cover.attic': 'x',
            },
          },
        },
      },
    } as unknown as HomeAssistant;
    const second = memo(hass2, CONFIG, registry);
    expect(second).not.toBe(first);
    expect(second!.managed_covers).toEqual([
      'cover.attic',
      'cover.living_room_left',
      'cover.living_room_right',
    ]);
  });
});

describe('createDiscoveryListMemo', () => {
  const TYPE = 'custom:adaptive-cover-sky-compass-card';

  it('resolves configured entries and reports unknown ones as missing', () => {
    const memo = createDiscoveryListMemo();
    const result = memo(makeHass(), [ENTRY_ID, 'nope'], makeRegistry(), TYPE);
    expect(result.list).toHaveLength(1);
    expect(result.list[0].entry_id).toBe(ENTRY_ID);
    expect(result.missing).toEqual(['nope']);
  });

  it('returns the SAME result object (and list array) across a new hass that shares the relevant state refs', () => {
    const memo = createDiscoveryListMemo();
    const registry = makeRegistry();
    const hass1 = makeHass() as unknown as { devices: unknown; states: Record<string, unknown> };
    const first = memo(hass1 as unknown as HomeAssistant, [ENTRY_ID], registry, TYPE);

    const hass2 = {
      devices: hass1.devices,
      states: { ...hass1.states, 'light.kitchen': { state: 'on', attributes: {} } },
    } as unknown as HomeAssistant;
    const second = memo(hass2, [ENTRY_ID], registry, TYPE);
    expect(second).toBe(first);
    expect(second.list).toBe(first.list); // stable array reference → no child churn
  });

  it('recomputes when a relevant state object reference changes', () => {
    const memo = createDiscoveryListMemo();
    const registry = makeRegistry();
    const hass1 = makeHass() as unknown as { devices: unknown; states: Record<string, unknown> };
    const first = memo(hass1 as unknown as HomeAssistant, [ENTRY_ID], registry, TYPE);

    const hass2 = {
      devices: hass1.devices,
      states: {
        ...hass1.states,
        'sensor.living_room_blinds_cover_position': {
          state: '55',
          attributes: { last_moves: { 'cover.solo': 'x' } },
        },
      },
    } as unknown as HomeAssistant;
    const second = memo(hass2, [ENTRY_ID], registry, TYPE);
    expect(second).not.toBe(first);
    expect(second.list[0].managed_covers).toEqual(['cover.solo']);
  });

  it('recomputes when the entry_ids list changes', () => {
    const memo = createDiscoveryListMemo();
    const hass = makeHass();
    const registry = makeRegistry();
    const first = memo(hass, [ENTRY_ID], registry, TYPE);
    const second = memo(hass, [ENTRY_ID, 'nope'], registry, TYPE);
    expect(second).not.toBe(first);
    expect(second.missing).toEqual(['nope']);
  });
});
