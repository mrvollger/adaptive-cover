import { describe, it, expect, vi } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';
import { AdaptiveCoverCard } from '../src/adaptive-cover-card';
import { AdaptiveCoverTileCard } from '../src/adaptive-cover-tile-card';
import { AdaptiveCoverSkyCompassCard } from '../src/adaptive-cover-sky-compass-card';
import { AdaptiveCoverDecisionCard } from '../src/adaptive-cover-decision-card';

function makeHass(callWS: (msg: unknown) => Promise<unknown>): HomeAssistant {
  return { callWS, states: {} } as unknown as HomeAssistant;
}

const ACP_ENTRIES = [
  { entry_id: 'a1', title: 'Living Room', domain: 'adaptive_cover' },
  { entry_id: 'b2', title: 'Kitchen', domain: 'adaptive_cover' },
];

/** One Position sensor per window; windows are listed by title. */
const ACP_REGISTRY = [
  {
    entity_id: 'sensor.a1_cover_position',
    unique_id: 'a1_Cover Position',
    platform: 'adaptive_cover',
    config_entry_id: 'a1',
    device_id: null,
  },
  {
    entity_id: 'sensor.b2_cover_position',
    unique_id: 'b2_Cover Position',
    platform: 'adaptive_cover',
    config_entry_id: 'b2',
    device_id: null,
  },
];

/** A callWS mock that dispatches between config_entries/get and the entity registry list. */
function makeAcpCallWS() {
  return vi.fn().mockImplementation((msg: { type: string }) => {
    if (msg.type === 'config/entity_registry/list') return Promise.resolve(ACP_REGISTRY);
    return Promise.resolve(ACP_ENTRIES);
  });
}

// New cards bind by `window:` (the window key). Windows are offered sorted by
// title, so "Kitchen" (b2) comes first.
describe('getStubConfig — card-picker preview discovery', () => {
  describe('main card', () => {
    it('returns the first window as `window`', async () => {
      const stub = await AdaptiveCoverCard.getStubConfig(makeHass(makeAcpCallWS()));
      expect(stub).toEqual({ type: 'custom:adaptive-cover-card', window: 'b2' });
    });

    it('falls back to an empty window when no windows exist', async () => {
      const stub = await AdaptiveCoverCard.getStubConfig(makeHass(vi.fn().mockResolvedValue([])));
      expect(stub.window).toBe('');
      expect(stub.entry_id).toBeUndefined();
    });

    it('falls back to an empty window when the websocket fetch rejects', async () => {
      const hass = makeHass(vi.fn().mockRejectedValue(new Error('boom')));
      const stub = await AdaptiveCoverCard.getStubConfig(hass);
      expect(stub.window).toBe('');
    });
  });

  describe('tile card', () => {
    it('returns the first window as `window`', async () => {
      const stub = await AdaptiveCoverTileCard.getStubConfig(makeHass(makeAcpCallWS()));
      expect(stub).toEqual({ type: 'custom:adaptive-cover-tile-card', window: 'b2' });
    });

    it('falls back to an empty window when the fetch rejects', async () => {
      const hass = makeHass(vi.fn().mockRejectedValue(new Error('boom')));
      const stub = await AdaptiveCoverTileCard.getStubConfig(hass);
      expect(stub.window).toBe('');
    });
  });

  describe('decision card', () => {
    it('returns the first window as `window`', async () => {
      const stub = await AdaptiveCoverDecisionCard.getStubConfig(makeHass(makeAcpCallWS()));
      expect(stub).toEqual({ type: 'custom:adaptive-cover-decision-card', window: 'b2' });
    });
  });

  describe('sky compass card', () => {
    it('wraps the first window in `windows`', async () => {
      const stub = await AdaptiveCoverSkyCompassCard.getStubConfig(makeHass(makeAcpCallWS()));
      expect(stub).toEqual({
        type: 'custom:adaptive-cover-sky-compass-card',
        windows: ['b2'],
      });
    });

    it('falls back to an empty windows array when no windows exist', async () => {
      const hass = makeHass(vi.fn().mockResolvedValue([]));
      const stub = await AdaptiveCoverSkyCompassCard.getStubConfig(hass);
      expect(stub.windows).toEqual([]);
    });

    it('falls back to an empty windows array when the fetch rejects', async () => {
      const hass = makeHass(vi.fn().mockRejectedValue(new Error('boom')));
      const stub = await AdaptiveCoverSkyCompassCard.getStubConfig(hass);
      expect(stub.windows).toEqual([]);
    });
  });
});
