/// <reference types="node" />
// The house card (custom:adaptive-cover-house-card) rendered against the real
// house: layout, labels, and the service calls each control sends.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '../src/adaptive-cover-house-card';
import type { AdaptiveCoverHouseCardConfig } from '../src/types';
import { holdDuration, msUntilTonight } from '../src/lib/house-actions';
import {
  FIXTURE_NOW,
  HUB_CLIMATE_SWITCH,
  HUB_DEVICE,
  houseFixture,
  mixedHouse,
  p5House,
  withHubClimate,
  withStates,
  type HouseFixture,
  type HouseTestHass,
} from './fixtures/house-hass';

const TYPE = 'custom:adaptive-cover-house-card';

interface CardLike extends HTMLElement {
  hass?: HouseTestHass;
  updateComplete: Promise<boolean>;
  setConfig(config: AdaptiveCoverHouseCardConfig): void;
}

async function mount(
  hass: HouseTestHass,
  config: Partial<AdaptiveCoverHouseCardConfig> = {},
): Promise<CardLike> {
  const el = document.createElement('adaptive-cover-house-card') as CardLike;
  el.setConfig({ type: TYPE, layout: 'wide', ...config });
  el.hass = hass;
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

const $ = (el: CardLike, sel: string) => el.shadowRoot!.querySelector<HTMLElement>(sel);
const $$ = (el: CardLike, sel: string) =>
  Array.from(el.shadowRoot!.querySelectorAll<HTMLElement>(sel));
const text = (node: Element | null) => (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

async function click(el: CardLike, node: HTMLElement | null | undefined): Promise<void> {
  expect(node, 'element to click').toBeTruthy();
  node!.click();
  await el.updateComplete;
  // Let runCalls' awaited service calls settle.
  await new Promise((r) => setTimeout(r, 0));
}

function roomEl(el: CardLike, areaId: string): HTMLElement {
  const node = $(el, `.room[data-room="${areaId}"]`);
  expect(node, `room ${areaId}`).toBeTruthy();
  return node!;
}

function segment(scope: ParentNode, mode: string): HTMLElement {
  return scope.querySelector<HTMLElement>(`.seg-btn[data-mode="${mode}"]`)!;
}

let fx: HouseFixture;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(FIXTURE_NOW));
  fx = houseFixture();
});
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('config', () => {
  it('stub config binds nothing (the whole house)', async () => {
    const Card = customElements.get('adaptive-cover-house-card') as unknown as {
      getStubConfig(): AdaptiveCoverHouseCardConfig;
      getConfigForm(): { schema: Array<{ name: string; selector: Record<string, unknown> }> };
    };
    expect(Card.getStubConfig()).toEqual({ type: TYPE });
    const form = Card.getConfigForm();
    expect(form.schema.map((s) => s.name)).toEqual([
      'title',
      'floors',
      'areas',
      'layout',
      'show_upcoming',
    ]);
    expect(form.schema[1].selector).toEqual({ floor: { multiple: true } });
    expect(form.schema[2].selector).toEqual({ area: { multiple: true } });
  });

  it('rejects floors / areas that are not lists of ids', () => {
    const el = document.createElement('adaptive-cover-house-card') as CardLike;
    expect(() => el.setConfig({ type: TYPE, floors: 'upstairs' as unknown as string[] })).toThrow(
      /floors/,
    );
    expect(() => el.setConfig({ type: TYPE, areas: [1 as unknown as string] })).toThrow(/areas/);
    expect(() => el.setConfig({ type: TYPE, floors: ['upstairs'] })).not.toThrow();
  });

  it('is listed in the card picker', () => {
    expect(window.customCards.some((c) => c.type === 'adaptive-cover-house-card')).toBe(true);
  });
});

describe('wide layout', () => {
  it('renders the header, floors top-down, rooms and all 15 rows', async () => {
    const el = await mount(fx.hass);
    expect(text($(el, 'h1'))).toBe('Shades');
    expect(text($(el, '.sub'))).toBe('15 windows · 5 rooms · 3 floors');
    expect(text($(el, '.sun-pill'))).toMatch(/^Sun 142° · 38° up · sets 7:22\s?PM$/);
    expect($$(el, '.floor-head h2').map(text)).toEqual(['Upstairs', 'Main', 'Ground', 'Coming up']);
    expect($$(el, '.room h3').map(text)).toEqual([
      'Master',
      'Office',
      'SW bedroom',
      'Family',
      'Den',
    ]);
    expect($$(el, '.row')).toHaveLength(15);
    expect(text($(el, '.bar-state'))).toBe('All on auto');
    expect(segment($(el, '.house-bar')!, 'auto').getAttribute('aria-pressed')).toBe('true');
  });

  it('shows Mixed with counts, the room modes and the row chips', async () => {
    const el = await mount(mixedHouse(fx));
    expect(text($(el, '.bar-state'))).toBe('Mixed: 10 auto, 4 hold, 1 off');
    const house = $(el, '.house-bar')!;
    expect(MODES.map((m) => segment(house, m).getAttribute('aria-pressed'))).toEqual([
      'false',
      'false',
      'false',
    ]);

    const office = roomEl(el, 'office');
    expect(segment(office, 'hold').getAttribute('aria-pressed')).toBe('true');
    expect(text(office.querySelector('.room-title .muted'))).toBe('3 windows');

    const master = roomEl(el, 'master_bedroom');
    expect(text(master.querySelector('.room-title .muted'))).toBe('4 windows · sun on 2 · mixed');
    const door = master.querySelector(`.row[data-window="${fx.keyOf('Master door')}"]`)!;
    expect(text(door.querySelector('.chip'))).toBe('Hold · 1h 12m');
    expect(text(door.querySelector('.row-next'))).toBe('Back to auto in 1h 12m');
    expect(text(door.querySelector('.pos'))).toBe('3%');
    expect(door.querySelector<HTMLElement>('.glyph')!.getAttribute('style')).toContain(
      '--fabric: 97%',
    );

    const east = master.querySelector(`.row[data-window="${fx.keyOf('Master east')}"]`)!;
    expect(east.querySelector('.sun-icon')).toBeTruthy();
    expect(east.querySelector('.glyph.sun')).toBeTruthy();
    expect(text(east.querySelector('.row-next'))).toMatch(/^Next: 38% at 11:05\s?AM$/);

    const denWest = roomEl(el, 'den').querySelector(`.row[data-window="${fx.keyOf('Den west')}"]`)!;
    expect(text(denWest.querySelector('.chip'))).toBe('Off');
    expect(text(denWest.querySelector('.row-next'))).toBe('Automatic control is off');
  });

  it('filters rows with the chips', async () => {
    const el = await mount(mixedHouse(fx));
    expect($$(el, '.chip-btn').map(text)).toEqual([
      'All 15',
      'Sun on glass · 5',
      'On hold · 4',
      'Off · 1',
    ]);
    await click(el, $(el, '.chip-btn[data-filter="hold"]'));
    expect($$(el, '.row')).toHaveLength(4);
    expect($$(el, '.room h3').map(text)).toEqual(['Master', 'Office']);
    await click(el, $(el, '.chip-btn[data-filter="off"]'));
    expect($$(el, '.row')).toHaveLength(1);
    expect($$(el, '.floor-head h2').map(text)).toEqual(['Ground', 'Coming up']);
  });

  it('lists the coming moves, grouped by time and position, and sunset', async () => {
    const el = await mount(mixedHouse(fx));
    const rows = $$(el, '.up-row').map(text);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatch(/^11:05\s?AM Master east, Family east Moves to 38%$/);
    expect(rows[1]).toMatch(/^7:22\s?PM Sunset Windows on auto go to their evening position$/);
  });

  it('hides "Coming up" when show_upcoming is false', async () => {
    const el = await mount(mixedHouse(fx), { show_upcoming: false });
    expect($(el, '.upcoming')).toBeNull();
  });

  it('only renders again when a watched entity changes', async () => {
    const el = await mount(fx.hass);
    const renders = vi.spyOn(el as unknown as { render(): unknown }, 'render');
    el.hass = withStates(fx.hass, { 'light.kitchen': { state: 'on' } });
    await el.updateComplete;
    expect(renders).not.toHaveBeenCalled();
    el.hass = withStates(fx.hass, { [fx.eid('Den west', 'manualOverride')]: { state: 'on' } });
    await el.updateComplete;
    expect(renders).toHaveBeenCalledTimes(1);
  });

  it('shows an empty state when the house has no windows', async () => {
    const hass = { ...fx.hass, entities: {} } as HouseTestHass;
    const el = await mount(hass);
    expect(text($(el, '.empty'))).toMatch(/No Adaptive Cover windows found/);
  });
});

const MODES = ['auto', 'hold', 'off'];

describe('service calls', () => {
  it('room Off: one select_option for the room', async () => {
    const el = await mount(fx.hass);
    await click(el, segment(roomEl(el, 'office'), 'off'));
    expect(fx.hass.callService.mock.calls).toEqual([
      [
        'select',
        'select_option',
        {
          entity_id: ['Office door', 'Office east', 'Office north'].map((t) => fx.eid(t, 'mode')),
          option: 'Manual',
        },
      ],
    ]);
  });

  it('room Auto on a held room: one Return to auto press', async () => {
    const hass = mixedHouse(fx);
    const el = await mount(hass);
    await click(el, segment(roomEl(el, 'office'), 'auto'));
    expect(hass.callService.mock.calls).toEqual([
      [
        'button',
        'press',
        {
          entity_id: ['Office door', 'Office east', 'Office north'].map((t) =>
            fx.eid(t, 'returnButton'),
          ),
        },
      ],
    ]);
  });

  it('Hold is disabled with a tooltip and sends nothing', async () => {
    const el = await mount(fx.hass);
    const hold = segment(roomEl(el, 'office'), 'hold');
    expect(hold.getAttribute('aria-disabled')).toBe('true');
    expect(hold.getAttribute('title')).toMatch(/moved by hand or with Open or Close/);
    await click(el, hold);
    expect(fx.hass.callService).not.toHaveBeenCalled();
  });

  it('house Off: the hub select', async () => {
    const el = await mount(fx.hass);
    await click(el, segment($(el, '.house-bar')!, 'off'));
    expect(fx.hass.callService.mock.calls).toEqual([
      [
        'select',
        'select_option',
        { entity_id: ['select.adaptive_cover_all_cover_control_mode'], option: 'Manual' },
      ],
    ]);
  });

  it('house Auto from Mixed: hub select, then the hub Return all button, in order', async () => {
    const hass = mixedHouse(fx);
    const el = await mount(hass);
    await click(el, segment($(el, '.house-bar')!, 'auto'));
    expect(hass.callService.mock.calls).toEqual([
      [
        'select',
        'select_option',
        { entity_id: ['select.adaptive_cover_all_cover_control_mode'], option: 'Adaptive' },
      ],
      ['button', 'press', { entity_id: ['button.adaptive_cover_all_reset_all_manual_overrides'] }],
    ]);
  });

  it('Return all to auto, Open all, Close all', async () => {
    const el = await mount(fx.hass);
    await click(el, $(el, '.return-all'));
    await click(el, $(el, '.open-all'));
    await click(el, $(el, '.close-all'));
    expect(fx.hass.callService.mock.calls).toEqual([
      ['button', 'press', { entity_id: ['button.adaptive_cover_all_reset_all_manual_overrides'] }],
      ['cover', 'open_cover', { entity_id: ['cover.adaptive_cover_all'] }],
      ['cover', 'close_cover', { entity_id: ['cover.adaptive_cover_all'] }],
    ]);
  });

  it('P5: the House settings link opens the house device; Climate is the house switch', async () => {
    const hass = withHubClimate(p5House(fx), 'on');
    const el = await mount(hass);
    expect($(el, '.house-bar .settings')!.getAttribute('href')).toBe(
      `/config/devices/device/${HUB_DEVICE}`,
    );
    await click(el, $(el, '.climate'));
    expect(hass.callService.mock.calls).toEqual([
      ['switch', 'turn_off', { entity_id: [HUB_CLIMATE_SWITCH] }],
    ]);
  });

  it('Climate toggle: one switch call for all 15 Climate mode switches', async () => {
    const el = await mount(fx.hass);
    const btn = $(el, '.climate')!;
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    await click(el, btn);
    const [call] = fx.hass.callService.mock.calls;
    expect(call[0]).toBe('switch');
    expect(call[1]).toBe('turn_off');
    expect((call[2] as { entity_id: string[] }).entity_id).toHaveLength(15);
  });

  it('a filtered card acts on its own windows, not through the hub', async () => {
    const el = await mount(fx.hass, { floors: ['ground'] });
    expect(text($(el, '.eyebrow'))).toBe('These windows');
    expect($$(el, '.row')).toHaveLength(3);
    await click(el, segment($(el, '.house-bar')!, 'off'));
    await click(el, $(el, '.open-all'));
    expect(fx.hass.callService.mock.calls).toEqual([
      [
        'select',
        'select_option',
        {
          entity_id: ['Den south', 'Den southwest', 'Den west'].map((t) => fx.eid(t, 'mode')),
          option: 'Manual',
        },
      ],
      [
        'cover',
        'open_cover',
        {
          entity_id: [
            'cover.den_south_shades',
            'cover.sw_sw_1st_floor_bed',
            'cover.den_west_shades',
          ],
        },
      ],
    ]);
  });

  it('reports a failed call as a notification', async () => {
    fx.hass.callService.mockRejectedValueOnce(new Error('boom'));
    const el = await mount(fx.hass);
    const seen: string[] = [];
    el.addEventListener('hass-notification', (e) =>
      seen.push((e as CustomEvent<{ message: string }>).detail.message),
    );
    await click(el, $(el, '.open-all'));
    expect(seen).toEqual(['Adaptive Cover: boom']);
  });
});

describe('detail sheet', () => {
  async function openSheet(hass: HouseTestHass, title: string, config = {}) {
    const el = await mount(hass, config);
    await click(el, $(el, `.row[data-window="${fx.keyOf(title)}"]`));
    const sheet = $(el, '.sheet');
    expect(sheet).toBeTruthy();
    return { el, sheet: sheet! };
  }

  it('shows where, position, mode, why and the setup link', async () => {
    const { sheet } = await openSheet(mixedHouse(fx), 'Master east');
    expect(text(sheet.querySelector('.sheet-title'))).toBe('Upstairs · Master East');
    expect(text(sheet.querySelector('.big-pos'))).toBe('0%');
    expect(text(sheet.querySelector('.target'))).toBe('Target 40%');
    expect(segment(sheet, 'auto').getAttribute('aria-pressed')).toBe('true');
    expect(text(sheet.querySelector('.why-text'))).toBe('Sun tracking: sun in view: tracking');
    expect(sheet.querySelector('details li')).toBeTruthy();
    expect(text(sheet.querySelector('.hint'))).toMatch(/move it with Open or Close/);
    expect(sheet.querySelector('.setup a')!.getAttribute('href')).toBe(
      `/config/integrations/integration/adaptive_cover#config_entry=${fx.keyOf('Master east')}`,
    );
    expect(text(sheet.querySelector('.sheet-foot > .muted'))).toBe('Faces 100° E');
  });

  it('explains a hold', async () => {
    const { sheet } = await openSheet(mixedHouse(fx), 'Master door');
    expect(text(sheet.querySelector('.why-text'))).toMatch(
      /^On hold until 11:52\s?AM\. Auto takes over again after that\.$/,
    );
    expect(text(sheet.querySelector('.chip'))).toBe('Hold · 1h 12m');
  });

  it('Open / Stop / Close move this window’s cover', async () => {
    const { el, sheet } = await openSheet(fx.hass, 'Office north');
    await click(el, sheet.querySelector<HTMLElement>('.cmd-open'));
    await click(el, sheet.querySelector<HTMLElement>('.cmd-stop'));
    await click(el, sheet.querySelector<HTMLElement>('.cmd-close'));
    expect(fx.hass.callService.mock.calls).toEqual([
      ['cover', 'open_cover', { entity_id: ['cover.office_north_shades'] }],
      ['cover', 'stop_cover', { entity_id: ['cover.office_north_shades'] }],
      ['cover', 'close_cover', { entity_id: ['cover.office_north_shades'] }],
    ]);
  });

  it('the window Mode: Off selects Manual; Auto on an Off window turns control back on', async () => {
    const hass = mixedHouse(fx);
    const { el, sheet } = await openSheet(hass, 'Den west');
    expect(segment(sheet, 'off').getAttribute('aria-pressed')).toBe('true');
    await click(el, segment(sheet, 'auto'));
    expect(hass.callService.mock.calls).toEqual([
      [
        'select',
        'select_option',
        { entity_id: [fx.eid('Den west', 'mode')], option: 'Sun + climate' },
      ],
      ['button', 'press', { entity_id: [fx.eid('Den west', 'returnButton')] }],
    ]);
  });

  it('P5: Hold chips hold this window for 1 h / 2 h / 4 h / until tonight', async () => {
    const hass = p5House(fx);
    const { el, sheet } = await openSheet(hass, 'Office north');
    expect(sheet.querySelector('.hint')).toBeNull();
    const chips = Array.from(sheet.querySelectorAll<HTMLElement>('.hold-chip'));
    expect(chips.map((c) => text(c))).toEqual(['1 h', '2 h', '4 h', 'Until tonight']);
    await click(el, sheet.querySelector<HTMLElement>('.hold-chip[data-hold="4h"]'));
    await click(el, sheet.querySelector<HTMLElement>('.hold-chip[data-hold="tonight"]'));
    const mode = fx.eid('Office north', 'mode');
    const tonight = msUntilTonight(Date.now());
    expect(hass.callService.mock.calls).toEqual([
      [
        'adaptive_cover',
        'hold',
        { entity_id: [mode], duration: { hours: 4, minutes: 0, seconds: 0 } },
      ],
      ['adaptive_cover', 'hold', { entity_id: [mode], duration: holdDuration(tonight) }],
    ]);
  });

  it('P5: the window Mode Off and Auto are select_option off / auto', async () => {
    const hass = p5House(fx, mixedHouse(fx));
    const { el, sheet } = await openSheet(hass, 'Den west');
    expect(segment(sheet, 'off').getAttribute('aria-pressed')).toBe('true');
    await click(el, segment(sheet, 'auto'));
    await click(el, segment(sheet, 'hold'));
    expect(hass.callService.mock.calls).toEqual([
      ['select', 'select_option', { entity_id: [fx.eid('Den west', 'mode')], option: 'auto' }],
      ['adaptive_cover', 'hold', { entity_id: [fx.eid('Den west', 'mode')] }],
    ]);
  });

  it('closes with the close button, the scrim and Escape', async () => {
    const { el } = await openSheet(fx.hass, 'Office north');
    await click(el, $(el, '.sheet .close'));
    expect($(el, '.sheet')).toBeNull();

    await click(el, $(el, `.row[data-window="${fx.keyOf('Office north')}"]`));
    await click(el, $(el, '.scrim'));
    expect($(el, '.sheet')).toBeNull();

    await click(el, $(el, `.row[data-window="${fx.keyOf('Office north')}"]`));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await el.updateComplete;
    expect($(el, '.sheet')).toBeNull();
  });

  it('Window setup navigates inside HA', async () => {
    const { el, sheet } = await openSheet(fx.hass, 'Office north');
    const pushed = vi.spyOn(history, 'pushState');
    const seen = vi.fn();
    window.addEventListener('location-changed', seen);
    await click(el, sheet.querySelector<HTMLElement>('.setup a'));
    expect(pushed).toHaveBeenCalledWith(
      null,
      '',
      `/config/integrations/integration/adaptive_cover#config_entry=${fx.keyOf('Office north')}`,
    );
    expect(seen).toHaveBeenCalled();
    expect($(el, '.sheet')).toBeNull();
    window.removeEventListener('location-changed', seen);
    pushed.mockRestore();
  });
});

describe('phone layout', () => {
  it('one column, collapsible rooms, open where a window needs attention', async () => {
    const el = await mount(mixedHouse(fx), { layout: 'narrow' });
    expect($(el, '.root.narrow')).toBeTruthy();
    expect($(el, '.filters')).toBeNull();
    expect(text($(el, '.bar-head .muted'))).toBe('10 auto · 4 hold · 1 off');
    expect($$(el, '.phone-floor').map(text)).toEqual(['Upstairs', 'Main', 'Ground']);
    const expanded = $$(el, '.room-toggle').map((b) => [
      text(b.querySelector('.strong')),
      b.getAttribute('aria-expanded'),
      text(b.querySelector('.chip')),
    ]);
    expect(expanded).toEqual([
      ['Master', 'true', 'Mixed'],
      ['Office', 'true', 'Hold'],
      ['SW bedroom', 'false', 'Auto'],
      ['Family', 'false', 'Auto'],
      ['Den', 'true', 'Mixed'],
    ]);
    expect($$(el, '.row')).toHaveLength(4 + 3 + 3);

    const family = roomEl(el, 'family_room');
    await click(el, family.querySelector<HTMLElement>('.room-toggle'));
    expect(family.querySelectorAll('.row')).toHaveLength(3);
    expect(family.querySelector('.seg')).toBeTruthy();
  });

  it('uses the phone layout below 600 px when layout is auto', async () => {
    const el = await mount(fx.hass, { layout: 'auto' });
    expect($(el, '.root.wide')).toBeTruthy();
    (el as unknown as { _width: number })._width = 390;
    await el.updateComplete;
    expect($(el, '.root.narrow')).toBeTruthy();
  });

  it('opens the sheet as a bottom sheet', async () => {
    const el = await mount(fx.hass, { layout: 'narrow' });
    await click(el, $(el, '.room-toggle'));
    await click(el, $(el, '.row'));
    expect($(el, '.sheet.bottom')).toBeTruthy();
  });
});

describe('the unique_id fallback', () => {
  it('fetches the full registry when the display rows lack translation keys', async () => {
    const legacy = houseFixture({ surface: 'legacy' });
    const el = await mount(legacy.hass);
    expect(legacy.hass.callWS).toHaveBeenCalledWith({ type: 'config/entity_registry/list' });
    await new Promise((r) => setTimeout(r, 0));
    await el.updateComplete;
    expect($$(el, '.row')).toHaveLength(15);
  });

  it('does not fetch the registry on today’s surface', async () => {
    await mount(fx.hass);
    expect(fx.hass.callWS).not.toHaveBeenCalled();
  });
});
