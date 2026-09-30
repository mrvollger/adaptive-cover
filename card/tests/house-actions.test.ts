/// <reference types="node" />
// The service calls behind each house-card control (lib/house-actions.ts),
// against the real house. Group actions must be one call per service with
// every target in one entity_id list.
import { describe, it, expect, vi } from 'vitest';

import { discoverHouse, type HouseModel, type HouseWindow } from '../src/lib/house-model';
import {
  autoOption,
  canHold,
  climateState,
  dominantClimateMethod,
  holdDuration,
  hubCanHold,
  msUntilTonight,
  planClimate,
  planCovers,
  planHold,
  planHouseCovers,
  planHouseMode,
  planReturnAll,
  planWindowsMode,
  runCalls,
  windowMode,
  windowStatus,
  type HouseScope,
} from '../src/lib/house-actions';
import {
  HUB_CLIMATE_SWITCH,
  HUB_DEVICE,
  HUB_MODE_SELECT,
  houseFixture,
  mixedHouse,
  p5House,
  withHubClimate,
  withStates,
  type HouseFixture,
  type HouseTestHass,
} from './fixtures/house-hass';

function setup(hass?: (fx: HouseFixture) => HouseTestHass) {
  const fx = houseFixture();
  const h = hass ? hass(fx) : fx.hass;
  const model = discoverHouse(h, null);
  const byName = (name: string): HouseWindow => model.windows.find((w) => w.deviceName === name)!;
  const room = (areaId: string) => model.windows.filter((w) => w.areaId === areaId);
  const scope = (useHub = true): HouseScope => ({ hub: model.hub, windows: model.windows, useHub });
  return { fx, hass: h, model, byName, room, scope };
}

const ids = (model: HouseModel, role: keyof HouseWindow['entities']) =>
  model.windows.map((w) => w.entities[role]!);

describe('autoOption', () => {
  it('picks the climate option when preferred, else sun tracking', () => {
    const opts = ['Manual', 'Sun tracking', 'Sun + climate'];
    expect(autoOption(opts, true)).toBe('Sun + climate');
    expect(autoOption(opts, false)).toBe('Sun tracking');
    expect(autoOption(['Manual', 'Sun tracking'], true)).toBe('Sun tracking');
  });

  it('picks the explicit auto option of the P5 and house selects', () => {
    expect(autoOption(['auto', 'hold', 'off'], true)).toBe('auto');
    expect(autoOption(['Manual', 'Adaptive', 'Mixed'], false)).toBe('Adaptive');
  });
});

describe('room and window modes', () => {
  it('Off for a room: one select_option to Manual for all its windows', () => {
    const { hass, room, fx } = setup();
    const office = room('office');
    expect(planWindowsMode(hass, office, 'off')).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: {
          entity_id: ['Office door', 'Office east', 'Office north'].map((t) => fx.eid(t, 'mode')),
          option: 'Manual',
        },
      },
    ]);
  });

  it('Off skips windows that are already off', () => {
    const { hass, room, fx } = setup(mixedHouse);
    const calls = planWindowsMode(hass, room('den'), 'off');
    expect(calls).toHaveLength(1);
    expect(calls[0].data.entity_id).toEqual([
      fx.eid('Den south', 'mode'),
      fx.eid('Den southwest', 'mode'),
    ]);
  });

  it('Auto for a room: control on for the Off windows, then Return to auto for Off + Hold', () => {
    const { hass, room, fx } = setup((f) =>
      withStates(mixedHouse(f), {
        [f.eid('Master trap', 'mode')]: { state: 'Manual' },
        [f.eid('Master trap', 'controlSwitch')]: { state: 'off' },
        [f.eid('Master south', 'mode')]: { state: 'Manual' },
        [f.eid('Master south', 'controlSwitch')]: { state: 'off' },
        // Master south used plain sun tracking before it was switched off.
        [f.eid('Master south', 'climateSwitch')]: { state: 'off' },
      }),
    );
    // Master: Door on hold, Trap and South off, East auto.
    expect(planWindowsMode(hass, room('master_bedroom'), 'auto')).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: [fx.eid('Master south', 'mode')], option: 'Sun tracking' },
      },
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: [fx.eid('Master trap', 'mode')], option: 'Sun + climate' },
      },
      {
        domain: 'button',
        service: 'press',
        data: {
          entity_id: ['Master door', 'Master south', 'Master trap'].map((t) =>
            fx.eid(t, 'returnButton'),
          ),
        },
      },
    ]);
  });

  it('Auto for a room that is only on hold: one Return to auto press', () => {
    const { hass, room, fx } = setup(mixedHouse);
    expect(planWindowsMode(hass, room('office'), 'auto')).toEqual([
      {
        domain: 'button',
        service: 'press',
        data: {
          entity_id: ['Office door', 'Office east', 'Office north'].map((t) =>
            fx.eid(t, 'returnButton'),
          ),
        },
      },
    ]);
  });

  it('Auto on windows already on auto does nothing', () => {
    const { hass, room } = setup(mixedHouse);
    expect(planWindowsMode(hass, room('family_room'), 'auto')).toEqual([]);
  });

  it('uses the Automatic control switch when the window has no Mode select', () => {
    const { hass, byName } = setup(mixedHouse);
    const den = { ...byName('Den west'), entities: { ...byName('Den west').entities } };
    delete den.entities.mode;
    expect(planWindowsMode(hass, [den], 'auto')[0]).toEqual({
      domain: 'switch',
      service: 'turn_on',
      data: { entity_id: [den.entities.controlSwitch] },
    });
    const south = { ...byName('Den south'), entities: { ...byName('Den south').entities } };
    delete south.entities.mode;
    expect(planWindowsMode(hass, [south], 'off')).toEqual([
      {
        domain: 'switch',
        service: 'turn_off',
        data: { entity_id: [south.entities.controlSwitch] },
      },
    ]);
  });

  it('Hold has no service today: no calls, and canHold is false', () => {
    const { hass, room } = setup();
    expect(canHold(hass, room('office'))).toBe(false);
    expect(planWindowsMode(hass, room('office'), 'hold')).toEqual([]);
  });

  it('Hold on P5 Mode selects: one adaptive_cover.hold call for the room', () => {
    const { fx, room } = setup(p5House);
    const selects = ['Office door', 'Office east', 'Office north'].map((t) => fx.eid(t, 'mode'));
    const hass = p5House(fx);
    expect(canHold(hass, room('office'))).toBe(true);
    expect(planWindowsMode(hass, room('office'), 'hold')).toEqual([
      { domain: 'adaptive_cover', service: 'hold', data: { entity_id: selects } },
    ]);
    expect(planWindowsMode(hass, room('office'), 'off')[0].data.option).toBe('off');
  });
});

describe('P5 Mode (auto / hold / off)', () => {
  const byTitle = (fx: HouseFixture, model: HouseModel, title: string): HouseWindow =>
    model.windows.find((w) => w.key === fx.keyOf(title))!;

  it('reads the mode and the hold end from the Mode select', () => {
    const { fx, hass, model } = setup((f) => p5House(f, mixedHouse(f)));
    expect(windowMode(hass, byTitle(fx, model, 'Den west'))).toBe('off');
    expect(windowMode(hass, byTitle(fx, model, 'Master door'))).toBe('hold');
    expect(windowMode(hass, byTitle(fx, model, 'Master east'))).toBe('auto');
    const until = hass.states[fx.eid('Master door', 'mode')].attributes.until;
    expect(until).toBeTruthy();
    expect(windowStatus(hass, byTitle(fx, model, 'Master door')).holdUntil).toBe(until);
  });

  it('Auto: one select_option to auto for Off and Hold windows (no button press)', () => {
    const { fx, hass, model } = setup((f) => p5House(f, mixedHouse(f)));
    const calls = planWindowsMode(hass, model.windows, 'auto');
    expect(calls).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: {
          entity_id: expect.arrayContaining(
            ['Den west', 'Master door', 'Office north', 'Office east', 'Office door'].map((t) =>
              fx.eid(t, 'mode'),
            ),
          ),
          option: 'auto',
        },
      },
    ]);
    expect(calls[0].data.entity_id).toHaveLength(5);
  });

  it('Hold with a duration: {hours, minutes, seconds}', () => {
    const { fx, hass, model } = setup(p5House);
    expect(planHold(hass, [byTitle(fx, model, 'Office north')], 4 * 3600_000)).toEqual([
      {
        domain: 'adaptive_cover',
        service: 'hold',
        data: {
          entity_id: [fx.eid('Office north', 'mode')],
          duration: { hours: 4, minutes: 0, seconds: 0 },
        },
      },
    ]);
    expect(holdDuration(5_430_400)).toEqual({ hours: 1, minutes: 30, seconds: 30 });
    // Older surfaces have no hold: nothing to call.
    const legacy = setup();
    const office = byTitle(legacy.fx, legacy.model, 'Office north');
    expect(planHold(legacy.hass, [office], 3600_000)).toEqual([]);
  });

  it('until tonight is the time left to the coming local midnight', () => {
    const now = Date.parse('2026-09-29T10:40:00-06:00');
    const ms = msUntilTonight(now);
    expect(ms).toBeGreaterThan(0);
    expect(ms).toBeLessThanOrEqual(24 * 3600_000);
    const end = new Date(now + ms);
    expect([end.getHours(), end.getMinutes(), end.getSeconds()]).toEqual([0, 0, 0]);
  });

  it('house: Hold and Off pick the house select; Return all to auto selects auto', () => {
    const { hass, model, scope } = setup((f) => p5House(f, mixedHouse(f)));
    expect(model.hub.modeSelect).toBe(HUB_MODE_SELECT);
    expect(hubCanHold(hass, model.hub)).toBe(true);
    const select = (option: string) => [
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: [HUB_MODE_SELECT], option },
      },
    ];
    expect(planHouseMode(hass, scope(), 'hold')).toEqual(select('hold'));
    expect(planHouseMode(hass, scope(), 'off')).toEqual(select('off'));
    expect(planHouseMode(hass, scope(), 'auto')).toEqual(select('auto'));
    expect(planReturnAll(hass, scope())).toEqual(select('auto'));
  });

  it('hidden switch aliases: the Climate mode switch is still read, the control switch is not', () => {
    const { fx, model, hass } = setup(p5House);
    const w = model.windows.find((x) => x.key === fx.keyOf('Den west'))!;
    expect(w.entities.climateSwitch).toBe(fx.eid('Den west', 'climateSwitch'));
    expect(w.entities.controlSwitch).toBeUndefined();
    expect(climateState(hass, model.windows)).toBe('on');
  });
});

describe('house controls', () => {
  it('house Off: the hub select, one call', () => {
    const { hass, scope } = setup();
    expect(planHouseMode(hass, scope(), 'off')).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: ['select.adaptive_cover_all_cover_control_mode'], option: 'Manual' },
      },
    ]);
  });

  it('house Auto: hub select to Adaptive (some window is off), then the hub Return all button', () => {
    const { hass, scope } = setup(mixedHouse);
    expect(planHouseMode(hass, scope(), 'auto')).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: ['select.adaptive_cover_all_cover_control_mode'], option: 'Adaptive' },
      },
      {
        domain: 'button',
        service: 'press',
        data: { entity_id: ['button.adaptive_cover_all_reset_all_manual_overrides'] },
      },
    ]);
  });

  it('house Auto with holds but nothing off: only the Return all button', () => {
    const { fx, scope } = setup();
    const hass = withStates(fx.hass, {
      [fx.eid('Master door', 'manualOverride')]: { state: 'on' },
    });
    expect(planHouseMode(hass, scope(), 'auto')).toEqual([
      {
        domain: 'button',
        service: 'press',
        data: { entity_id: ['button.adaptive_cover_all_reset_all_manual_overrides'] },
      },
    ]);
  });

  it('house Auto when everything is on auto: nothing', () => {
    const { hass, scope } = setup();
    expect(planHouseMode(hass, scope(), 'auto')).toEqual([]);
  });

  it('house Hold: no hub hold option today → no calls', () => {
    const { hass, model, scope } = setup();
    expect(hubCanHold(hass, model.hub)).toBe(false);
    expect(planHouseMode(hass, scope(), 'hold')).toEqual([]);
  });

  it('house Hold: the P5 hub select (Auto / Hold / Off / Mixed)', () => {
    const { fx, model, scope } = setup();
    const hass = withStates(fx.hass, {
      [model.hub.modeSelect!]: {
        state: 'Auto',
        attributes: { options: ['Auto', 'Hold', 'Off', 'Mixed'] },
      },
    });
    expect(hubCanHold(hass, model.hub)).toBe(true);
    expect(planHouseMode(hass, scope(), 'hold')).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: [model.hub.modeSelect], option: 'Hold' },
      },
    ]);
    expect(planHouseMode(hass, scope(), 'off')[0].data.option).toBe('Off');
  });

  it('without the hub (or on a filtered card) the house controls are group calls', () => {
    const { hass, model, scope, fx } = setup();
    const calls = planHouseMode(hass, scope(false), 'off');
    expect(calls).toEqual([
      {
        domain: 'select',
        service: 'select_option',
        data: { entity_id: ids(model, 'mode'), option: 'Manual' },
      },
    ]);
    expect(calls[0].data.entity_id).toHaveLength(15);
    const noHub: HouseScope = { hub: {}, windows: model.windows, useHub: true };
    expect(planHouseMode(hass, noHub, 'off')).toEqual(calls);
    // Return all with no hub button: every window's Return to auto, one call.
    const held = withStates(hass, { [fx.eid('Den west', 'manualOverride')]: { state: 'on' } });
    expect(planReturnAll(held, noHub)).toEqual([
      { domain: 'button', service: 'press', data: { entity_id: ids(model, 'returnButton') } },
    ]);
  });

  it('Return all to auto always presses the hub button', () => {
    const { hass, scope } = setup();
    expect(planReturnAll(hass, scope())).toEqual([
      {
        domain: 'button',
        service: 'press',
        data: { entity_id: ['button.adaptive_cover_all_reset_all_manual_overrides'] },
      },
    ]);
  });

  it('Open all / Close all: the hub cover', () => {
    const { scope } = setup();
    expect(planHouseCovers(scope(), 'open')).toEqual([
      { domain: 'cover', service: 'open_cover', data: { entity_id: ['cover.adaptive_cover_all'] } },
    ]);
    expect(planHouseCovers(scope(), 'close')).toEqual([
      {
        domain: 'cover',
        service: 'close_cover',
        data: { entity_id: ['cover.adaptive_cover_all'] },
      },
    ]);
  });

  it('Open all without the hub cover: one call with every cover', () => {
    const { model, scope } = setup();
    const calls = planHouseCovers(scope(false), 'open');
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ domain: 'cover', service: 'open_cover' });
    expect(calls[0].data.entity_id).toEqual(model.windows.map((w) => w.covers[0]));
  });

  it('Climate: one switch call over every Climate mode switch', () => {
    const { hass, model } = setup();
    expect(climateState(hass, model.windows)).toBe('on');
    expect(planClimate(model.windows, false)).toEqual([
      { domain: 'switch', service: 'turn_off', data: { entity_id: ids(model, 'climateSwitch') } },
    ]);
    expect(planClimate(model.windows, true)[0].service).toBe('turn_on');
  });

  it('Climate state is mixed when the switches differ; its text follows the Control method', () => {
    const { fx, model } = setup();
    const methods = (summer: number) =>
      Object.fromEntries(
        model.windows.map((w, i) => [
          w.entities.controlMethod!,
          { state: i < summer ? 'summer' : 'intermediate' },
        ]),
      );
    const off = { [fx.eid('Den west', 'climateSwitch')]: { state: 'off' } };
    const mild = withStates(fx.hass, { ...methods(4), ...off });
    expect(climateState(mild, model.windows)).toBe('mixed');
    expect(dominantClimateMethod(mild, model.windows)).toBe('intermediate');
    const hot = withStates(fx.hass, { ...methods(9), ...off });
    expect(dominantClimateMethod(hot, model.windows)).toBe('summer');
    // Windows with climate off do not count.
    const allOff = withStates(
      fx.hass,
      Object.fromEntries(model.windows.map((w) => [w.entities.climateSwitch!, { state: 'off' }])),
    );
    expect(climateState(allOff, model.windows)).toBe('off');
    expect(dominantClimateMethod(allOff, model.windows)).toBeNull();
  });
});

describe('window covers', () => {
  it('Open / Stop / Close the window’s own covers', () => {
    const { byName } = setup();
    const w = byName('Office north');
    expect(planCovers([w], 'open')).toEqual([
      {
        domain: 'cover',
        service: 'open_cover',
        data: { entity_id: ['cover.office_north_shades'] },
      },
    ]);
    expect(planCovers([w], 'stop')[0].service).toBe('stop_cover');
    expect(planCovers([w], 'close')[0].service).toBe('close_cover');
  });

  it('tilt windows use the tilt services', () => {
    const { byName } = setup();
    const w = { ...byName('Office north'), coverType: 'cover_tilt' };
    expect(planCovers([w], 'open')[0].service).toBe('open_cover_tilt');
    expect(planCovers([w], 'close')[0].service).toBe('close_cover_tilt');
  });
});

describe('runCalls', () => {
  it('runs calls in order, each after the previous one finished', async () => {
    const order: string[] = [];
    const hass = {
      callService: vi.fn(async (domain: string, service: string) => {
        await new Promise((r) => setTimeout(r, domain === 'select' ? 5 : 0));
        order.push(`${domain}.${service}`);
      }),
    } as unknown as HouseTestHass;
    await runCalls(hass, [
      { domain: 'select', service: 'select_option', data: {} },
      { domain: 'button', service: 'press', data: {} },
    ]);
    expect(order).toEqual(['select.select_option', 'button.press']);
  });
});

describe('P5 house settings', () => {
  it('the house Climate switch drives the Climate control', () => {
    const { hass, model, scope } = setup((f) => withHubClimate(p5House(f), 'off'));
    expect(model.hub.climateSwitch).toBe(HUB_CLIMATE_SWITCH);
    expect(model.hubDeviceId).toBe(HUB_DEVICE);
    expect(climateState(hass, model.windows, scope())).toBe('off');
    expect(planClimate(model.windows, true, hass, scope())).toEqual([
      { domain: 'switch', service: 'turn_on', data: { entity_id: [HUB_CLIMATE_SWITCH] } },
    ]);
    // A card showing some rooms acts on their windows, not the house.
    expect(climateState(hass, model.windows, scope(false))).toBe('on');
    expect(planClimate(model.windows, false, hass, scope(false))[0].data.entity_id).toHaveLength(
      15,
    );
  });
});
