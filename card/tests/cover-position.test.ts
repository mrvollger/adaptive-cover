import { describe, it, expect } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';
import {
  coverHeldPosition,
  coverSolarTarget,
  coverActualPositions,
  coverActualPosition,
  manualOverrideActive,
  isOverrideDivergence,
  displayTarget,
} from '../src/lib/cover-position';

function discovered(over: Partial<DiscoveredEntities> = {}): DiscoveredEntities {
  return {
    entry_id: 'entry1',
    entry_title: 'Test',
    cover_type: 'cover_blind',
    entities: {
      target_position_sensor: 'sensor.cover_position',
      manual_override_binary: 'binary_sensor.manual_override',
    },
    managed_covers: ['cover.a', 'cover.b'],
    ...over,
  };
}

interface Opts {
  state?: string;
  covers?: Record<string, Record<string, unknown>>;
  override?: boolean;
}

function makeHass(o: Opts): HomeAssistant {
  return {
    states: {
      'sensor.cover_position': { state: o.state ?? '0', attributes: {} },
      'binary_sensor.manual_override': {
        state: o.override ? 'on' : 'off',
        attributes: {},
      },
      ...Object.fromEntries(
        Object.entries(o.covers ?? {}).map(([id, attributes]) => [
          id,
          { state: 'open', attributes },
        ]),
      ),
    },
  } as unknown as HomeAssistant;
}

describe('cover-position helpers (Adaptive Cover sensor contract)', () => {
  it('reads the engine target from the Cover Position sensor state', () => {
    const hass = makeHass({ state: '44' });
    expect(coverHeldPosition(hass, discovered())).toBe(44);
  });

  it('returns null when the sensor state is not numeric or the sensor is missing', () => {
    expect(coverHeldPosition(makeHass({ state: 'unavailable' }), discovered())).toBeNull();
    expect(
      coverHeldPosition(makeHass({ state: '44' }), discovered({ entities: {} })),
    ).toBeNull();
  });

  it('coverSolarTarget is an alias of the held/engine target', () => {
    const hass = makeHass({ state: '61' });
    const d = discovered();
    expect(coverSolarTarget(hass, d)).toBe(61);
    expect(coverSolarTarget(hass, d)).toBe(coverHeldPosition(hass, d));
  });

  it('reads per-cover live positions from the managed cover entities', () => {
    const hass = makeHass({
      covers: {
        'cover.a': { current_position: 40 },
        'cover.b': { current_position: 50 },
      },
    });
    expect(coverActualPositions(hass, discovered())).toEqual({
      'cover.a': 40,
      'cover.b': 50,
    });
    expect(coverActualPosition(hass, discovered())).toBe(45);
  });

  it('uses current_tilt_position for tilt covers', () => {
    const hass = makeHass({
      covers: {
        'cover.a': { current_tilt_position: 30, current_position: 99 },
      },
    });
    const d = discovered({ cover_type: 'cover_tilt', managed_covers: ['cover.a'] });
    expect(coverActualPositions(hass, d)).toEqual({ 'cover.a': 30 });
    expect(coverActualPosition(hass, d)).toBe(30);
  });

  it('reports null per-cover positions for covers without a readable position', () => {
    const hass = makeHass({
      covers: { 'cover.a': { current_position: 20 }, 'cover.b': {} },
    });
    expect(coverActualPositions(hass, discovered())).toEqual({
      'cover.a': 20,
      'cover.b': null,
    });
    // Aggregate is the mean of the covers that do report.
    expect(coverActualPosition(hass, discovered())).toBe(20);
  });

  it('returns null aggregate when there are no managed covers', () => {
    const hass = makeHass({ state: '44' });
    expect(coverActualPosition(hass, discovered({ managed_covers: [] }))).toBeNull();
  });

  it('reports manual override active from the binary sensor', () => {
    expect(manualOverrideActive(makeHass({ override: true }), discovered())).toBe(true);
    expect(manualOverrideActive(makeHass({ override: false }), discovered())).toBe(false);
  });

  describe('displayTarget / isOverrideDivergence', () => {
    it('flags divergence when the override is active and actual differs from target', () => {
      const hass = makeHass({
        state: '60',
        override: true,
        covers: { 'cover.a': { current_position: 20 }, 'cover.b': { current_position: 24 } },
      });
      expect(isOverrideDivergence(hass, discovered())).toBe(true);
      // The labeled target is always the engine target (sensor state).
      expect(displayTarget(hass, discovered())).toBe(60);
    });

    it('reports no divergence when the override is inactive', () => {
      const hass = makeHass({
        state: '60',
        override: false,
        covers: { 'cover.a': { current_position: 20 }, 'cover.b': { current_position: 24 } },
      });
      expect(isOverrideDivergence(hass, discovered())).toBe(false);
      expect(displayTarget(hass, discovered())).toBe(60);
    });

    it('reports no divergence when actual rounds to the target', () => {
      const hass = makeHass({
        state: '60',
        override: true,
        covers: { 'cover.a': { current_position: 60.3 }, 'cover.b': { current_position: 59.8 } },
      });
      // Mean 60.05 → rounds to 60 → matches target.
      expect(isOverrideDivergence(hass, discovered())).toBe(false);
    });

    it('reports no divergence when the aggregate actual is unknown', () => {
      const hass = makeHass({ state: '60', override: true });
      expect(isOverrideDivergence(hass, discovered({ managed_covers: [] }))).toBe(false);
    });

    it('reports no divergence when the target is unknown', () => {
      const hass = makeHass({
        state: 'unknown',
        override: true,
        covers: { 'cover.a': { current_position: 20 }, 'cover.b': { current_position: 20 } },
      });
      expect(isOverrideDivergence(hass, discovered())).toBe(false);
    });
  });
});
