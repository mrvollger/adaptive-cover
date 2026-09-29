/// <reference types="node" />
// House discovery (lib/house-model.ts) and the mode mapping
// (lib/house-actions.ts windowMode / windowStatus) against the real house:
// 15 windows on 3 floors plus the hub, from tests/fixtures/house-hass.ts.
import { describe, it, expect } from 'vitest';

import { discoverHouse, stripRoomName, watchedEntityIds } from '../src/lib/house-model';
import { countModes, groupMode, windowMode, windowStatus } from '../src/lib/house-actions';
import {
  FIXTURE_NOW,
  HUB_ENTRY,
  WINDOW_ENTRIES,
  houseFixture,
  mixedHouse,
  withLegacyMoves,
  withStates,
} from './fixtures/house-hass';

/** floor → room → window names, the shape the card renders. */
function layout(model: ReturnType<typeof discoverHouse>) {
  return model.floors.map((f) => ({
    floor: f.name,
    rooms: f.rooms.map((r) => ({ room: r.name, windows: r.windows.map((w) => w.name) })),
  }));
}

const HOUSE_LAYOUT = [
  {
    floor: 'Upstairs',
    rooms: [
      { room: 'Master', windows: ['Door', 'East', 'South', 'Trap'] },
      { room: 'Office', windows: ['Door', 'East', 'North'] },
      { room: 'SW bedroom', windows: ["Leanne's door", "Leanne's south"] },
    ],
  },
  { floor: 'Main', rooms: [{ room: 'Family', windows: ['Door', 'East', 'South'] }] },
  { floor: 'Ground', rooms: [{ room: 'Den', windows: ['South', 'Southwest', 'West'] }] },
];

describe('discoverHouse: the real house on today’s entity surface', () => {
  it('finds the 15 windows, grouped floor → room, top floor first', () => {
    const fx = houseFixture();
    const model = discoverHouse(fx.hass, null);
    expect(model.windows).toHaveLength(15);
    expect(layout(model)).toEqual(HOUSE_LAYOUT);
    expect(model.needsRegistry).toBe(false);
  });

  it('keys each window by the window_key attribute (the entry id today)', () => {
    const fx = houseFixture();
    const model = discoverHouse(fx.hass, null);
    expect(new Set(model.windows.map((w) => w.key))).toEqual(
      new Set(WINDOW_ENTRIES.map((e) => e.entry_id)),
    );
  });

  it('maps every role of a window by translation key and device', () => {
    const fx = houseFixture();
    const model = discoverHouse(fx.hass, null);
    const w = model.windows.find((x) => x.key === fx.keyOf('Office north'))!;
    expect(w.entities).toEqual({
      position: fx.eid('Office north', 'position'),
      mode: fx.eid('Office north', 'mode'),
      returnButton: fx.eid('Office north', 'returnButton'),
      manualOverride: fx.eid('Office north', 'manualOverride'),
      sunInFront: fx.eid('Office north', 'sunInFront'),
      controlMethod: fx.eid('Office north', 'controlMethod'),
      controlSwitch: fx.eid('Office north', 'controlSwitch'),
      climateSwitch: fx.eid('Office north', 'climateSwitch'),
    });
    expect(w.covers).toEqual(['cover.office_north_shades']);
    expect(w.coverType).toBe('cover_blind');
    expect(w.deviceName).toBe('Office north');
  });

  it('finds the hub: house cover, house select and Return all button', () => {
    const model = discoverHouse(houseFixture().hass, null);
    expect(model.hub).toEqual({
      cover: 'cover.adaptive_cover_all',
      modeSelect: 'select.adaptive_cover_all_cover_control_mode',
      returnButton: 'button.adaptive_cover_all_reset_all_manual_overrides',
    });
  });

  it('takes the room from the physical cover when the window device has none', () => {
    const fx = houseFixture();
    // 12 of the 15 window devices have no area in the live house.
    const devId = fx.hass.entities[fx.eid('Den west', 'position')].device_id as string;
    expect(fx.hass.devices[devId].area_id).toBeNull();
    const w = discoverHouse(fx.hass, null).windows.find((x) => x.key === fx.keyOf('Den west'))!;
    expect(w.areaId).toBe('den');
    expect(w.floorId).toBe('ground');
  });

  it('prefers the window device area over the cover area, and the entity area over both', () => {
    const fx = houseFixture();
    const pos = fx.eid('Den west', 'position');
    const devId = fx.hass.entities[pos].device_id as string;
    fx.hass.devices[devId] = { ...fx.hass.devices[devId], area_id: 'kitchen' };
    let w = discoverHouse(fx.hass, null).windows.find((x) => x.key === fx.keyOf('Den west'))!;
    expect([w.areaId, w.floorId]).toEqual(['kitchen', 'main']);

    fx.hass.entities = {
      ...fx.hass.entities,
      [pos]: { ...fx.hass.entities[pos], area_id: 'office' },
    };
    w = discoverHouse(fx.hass, null).windows.find((x) => x.key === fx.keyOf('Den west'))!;
    expect([w.areaId, w.floorId]).toEqual(['office', 'upstairs']);
  });

  it('puts a window without any area in an "Unassigned" room, after the floors', () => {
    const fx = houseFixture();
    const cover = fx.coverOf('Den west');
    const coverDev = fx.hass.entities[cover].device_id as string;
    fx.hass.devices[coverDev] = { ...fx.hass.devices[coverDev], area_id: null };
    const model = discoverHouse(fx.hass, null);
    const last = model.floors[model.floors.length - 1];
    expect(last).toMatchObject({ id: null, name: 'Other' });
    expect(last.rooms.map((r) => [r.id, r.name, r.windows.map((w) => w.deviceName)])).toEqual([
      [null, 'Unassigned', ['Den west']],
    ]);
    expect(model.windows).toHaveLength(15);
  });

  it('puts a room without a floor in the "Other" group', () => {
    const fx = houseFixture();
    fx.hass.areas = { ...fx.hass.areas, den: { ...fx.hass.areas.den, floor_id: null } };
    const model = discoverHouse(fx.hass, null);
    expect(model.floors.map((f) => f.name)).toEqual(['Upstairs', 'Main', 'Other']);
    expect(model.floors[2].rooms.map((r) => r.name)).toEqual(['Den']);
  });

  it('shows rooms without a floor heading when the house has no floors', () => {
    const fx = houseFixture();
    fx.hass.floors = {};
    const model = discoverHouse(fx.hass, null);
    expect(model.floors).toHaveLength(1);
    expect(model.floors[0].name).toBe('');
    expect(model.floors[0].rooms.map((r) => r.name)).toEqual([
      'Den',
      'Family',
      'Master',
      'Office',
      'SW bedroom',
    ]);
  });

  it('skips hidden entities: a hidden Position sensor hides the window', () => {
    const fx = houseFixture();
    const pos = fx.eid('Den west', 'position');
    fx.hass.entities = { ...fx.hass.entities, [pos]: { ...fx.hass.entities[pos], hidden: true } };
    const model = discoverHouse(fx.hass, null);
    expect(model.windows).toHaveLength(14);
    expect(model.windows.some((w) => w.key === fx.keyOf('Den west'))).toBe(false);
  });

  it('skips a hidden role but keeps the window', () => {
    const fx = houseFixture();
    const sel = fx.eid('Den west', 'mode');
    fx.hass.entities = { ...fx.hass.entities, [sel]: { ...fx.hass.entities[sel], hidden: true } };
    const w = discoverHouse(fx.hass, null).windows.find((x) => x.key === fx.keyOf('Den west'))!;
    expect(w.entities.mode).toBeUndefined();
    expect(w.entities.controlSwitch).toBe(fx.eid('Den west', 'controlSwitch'));
  });

  it('filters by floors and areas (union)', () => {
    const fx = houseFixture();
    const names = (filter: { floors?: string[]; areas?: string[] }) =>
      discoverHouse(fx.hass, null, filter).windows.map((w) => w.deviceName);
    expect(names({ floors: ['ground'] })).toEqual(['Den south', 'Den southwest', 'Den west']);
    expect(names({ areas: ['office'] })).toEqual(['Office door', 'Office east', 'Office north']);
    expect(names({ floors: ['main'], areas: ['den'] })).toEqual([
      'Family door',
      'Family east',
      'Family south',
      'Den south',
      'Den southwest',
      'Den west',
    ]);
  });

  it('lists every entity the card must watch', () => {
    const fx = houseFixture();
    const ids = watchedEntityIds(discoverHouse(fx.hass, null));
    expect(ids).toContain(fx.eid('Master door', 'manualOverride'));
    expect(ids).toContain('cover.master_door_shades');
    expect(ids).toContain('select.adaptive_cover_all_cover_control_mode');
    expect(ids).toContain('sun.sun');
  });
});

describe('discoverHouse: the unique_id fallback (no translation keys, no window attributes)', () => {
  it('asks for the registry when the display rows cannot be classified', () => {
    const fx = houseFixture({ surface: 'legacy' });
    const model = discoverHouse(fx.hass, null);
    expect(model.windows).toHaveLength(0);
    expect(model.needsRegistry).toBe(true);
  });

  it('with the registry, finds the 15 windows; rooms come from device areas only', () => {
    // The 1.13 Position sensor does not name its covers until it moved them,
    // so only the 3 window devices that have an area get a room.
    const fx = houseFixture({ surface: 'legacy' });
    const model = discoverHouse(fx.hass, fx.registry);
    expect(model.windows).toHaveLength(15);
    expect(layout(model)).toEqual([
      {
        floor: 'Upstairs',
        rooms: [
          { room: 'Master', windows: ['Trap'] },
          { room: 'Office', windows: ['East', 'North'] },
        ],
      },
      {
        floor: 'Other',
        rooms: [
          {
            room: 'Unassigned',
            windows: [
              'Den south',
              'Den southwest',
              'Den west',
              'Family door',
              'Family east',
              'Family south',
              "Leanne's door",
              "Leanne's south",
              'Master door',
              'Master east',
              'Master south',
              'Office door',
            ],
          },
        ],
      },
    ]);
  });

  it('with the registry and moved covers, finds the same house by unique_id prefix', () => {
    const fx = houseFixture({ surface: 'legacy' });
    const model = discoverHouse(withLegacyMoves(fx), fx.registry);
    expect(layout(model)).toEqual(HOUSE_LAYOUT);
    expect(model.needsRegistry).toBe(false);
    const w = model.windows.find((x) => x.key === fx.keyOf('Master trap'))!;
    expect(w.entities.mode).toBe(fx.eid('Master trap', 'mode'));
    expect(w.entities.returnButton).toBe(fx.eid('Master trap', 'returnButton'));
    expect(w.configEntryId).toBe(fx.keyOf('Master trap'));
    expect(model.hub.modeSelect).toBe('select.adaptive_cover_all_cover_control_mode');
  });

  it('never filters on config_entry_id (windows as subentries of one house entry)', () => {
    const fx = houseFixture({ surface: 'legacy' });
    const consolidated = fx.registry.map((r) => ({
      ...r,
      config_entry_id: HUB_ENTRY.entry_id,
      config_subentry_id: r.unique_id.startsWith('adaptive_cover_hub_')
        ? null
        : `sub_${r.config_entry_id}`,
    }));
    const hass = withLegacyMoves(fx);
    const model = discoverHouse(hass, consolidated);
    expect(layout(model)).toEqual(HOUSE_LAYOUT);
    expect(model.windows.map((w) => w.key)).toEqual(
      discoverHouse(hass, fx.registry).windows.map((w) => w.key),
    );
    const w = model.windows.find((x) => x.key === fx.keyOf('Office east'))!;
    expect(w.configEntryId).toBe(HUB_ENTRY.entry_id);
    expect(w.configSubentryId).toBe(`sub_${fx.keyOf('Office east')}`);
  });

  it('skips rows the registry marks hidden or disabled', () => {
    const fx = houseFixture({ surface: 'legacy' });
    const pos = fx.eid('Den west', 'position');
    const registry = fx.registry.map((r) =>
      r.entity_id === pos ? { ...r, disabled_by: 'user' } : r,
    );
    expect(discoverHouse(fx.hass, registry).windows).toHaveLength(14);
  });
});

describe('stripRoomName', () => {
  it.each([
    ['Master east', 'Master', 'East'],
    ['Office north', 'Office', 'North'],
    ['Den southwest', 'Den', 'Southwest'],
    ["Leanne's door", 'SW bedroom', "Leanne's door"],
    ['Master', 'Master', 'Master'],
    ['Mastery window', 'Master', 'Mastery window'],
    ['Family - door', 'Family', 'Door'],
    ['Kitchen east', null, 'Kitchen east'],
  ])('%s in %s → %s', (name, room, expected) => {
    expect(stripRoomName(name, room)).toBe(expected);
  });
});

describe('mode mapping (today’s surface → Auto / Hold / Off)', () => {
  const now = Date.parse(FIXTURE_NOW);

  function modesOf(hass = mixedHouse(houseFixture())) {
    const model = discoverHouse(hass, null);
    return Object.fromEntries(model.windows.map((w) => [w.deviceName, windowMode(hass, w)]));
  }

  it('Auto by default', () => {
    const fx = houseFixture();
    const modes = modesOf(fx.hass);
    expect(Object.values(modes)).toEqual(Array(15).fill('auto'));
  });

  it('Hold when the Manual override sensor is on; Off when the Mode select is Manual', () => {
    const modes = modesOf();
    expect(modes['Master door']).toBe('hold');
    expect(modes['Office north']).toBe('hold');
    expect(modes['Den west']).toBe('off');
    expect(modes['Master east']).toBe('auto');
    expect(countModes(Object.values(modes))).toEqual({ auto: 10, hold: 4, off: 1 });
  });

  it('Off when only the Automatic control switch says so (no Mode select)', () => {
    const fx = houseFixture();
    const sel = fx.eid('Den west', 'mode');
    fx.hass.entities = { ...fx.hass.entities, [sel]: { ...fx.hass.entities[sel], hidden: true } };
    const hass = withStates(fx.hass, { [fx.eid('Den west', 'controlSwitch')]: { state: 'off' } });
    expect(modesOf(hass)['Den west']).toBe('off');
  });

  it('Off wins over a latched hold', () => {
    const fx = houseFixture();
    const hass = withStates(fx.hass, {
      [fx.eid('Den west', 'mode')]: { state: 'Manual' },
      [fx.eid('Den west', 'manualOverride')]: { state: 'on' },
    });
    expect(modesOf(hass)['Den west']).toBe('off');
  });

  it('reads the P5 Mode select (auto / hold / off) directly', () => {
    const fx = houseFixture();
    const sel = fx.eid('Den west', 'mode');
    const p5 = (state: string) =>
      withStates(fx.hass, { [sel]: { state, attributes: { options: ['auto', 'hold', 'off'] } } });
    expect(modesOf(p5('hold'))['Den west']).toBe('hold');
    expect(modesOf(p5('off'))['Den west']).toBe('off');
    expect(modesOf(p5('auto'))['Den west']).toBe('auto');
  });

  it('groupMode: one mode, mixed, or null', () => {
    expect(groupMode(['auto', 'auto'])).toBe('auto');
    expect(groupMode(['hold', 'hold'])).toBe('hold');
    expect(groupMode(['auto', 'off'])).toBe('mixed');
    expect(groupMode([])).toBeNull();
  });

  it('windowStatus: hold end, live position, target, sun, next move, trace', () => {
    const fx = houseFixture();
    const hass = mixedHouse(fx);
    const model = discoverHouse(hass, null);
    const door = model.windows.find((w) => w.deviceName === 'Master door')!;
    const s = windowStatus(hass, door);
    expect(s.mode).toBe('hold');
    expect(Date.parse(s.holdUntil!) - now).toBe(72 * 60_000);
    // Live cover position (3 in the snapshot), not the target.
    expect(s.position).toBe(3);
    expect(s.available).toBe(true);
    expect(s.azimuth).toBe(145);

    const east = model.windows.find((w) => w.deviceName === 'Master east')!;
    const e = windowStatus(hass, east);
    expect(e.sunOnGlass).toBe(true);
    expect(e.target).toBe(40);
    expect(e.nextMove).toEqual({ time: new Date(now + 25 * 60_000).toISOString(), position: 38 });
    expect(e.intent).toBe('calculated');
    expect(e.trace[e.trace.length - 1]).toBe('sun in view: tracking');
  });

  it('windowStatus: falls back to override_until and to the target position', () => {
    const fx = houseFixture();
    const pos = fx.eid('Den west', 'position');
    const hass = withStates(fx.hass, {
      [fx.eid('Den west', 'manualOverride')]: { state: 'on', attributes: { until: null } },
      [pos]: { state: '55', attributes: { override_until: '2026-09-29T12:00:00-06:00' } },
      [fx.coverOf('Den west')]: { state: 'unavailable', attributes: { current_position: null } },
    });
    const w = discoverHouse(hass, null).windows.find((x) => x.key === fx.keyOf('Den west'))!;
    const s = windowStatus(hass, w);
    expect(s.holdUntil).toBe('2026-09-29T12:00:00-06:00');
    expect(s.position).toBe(55);
  });
});
