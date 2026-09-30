/// <reference types="node" />
// The house card's settings sheets (refactor plan P6): a room's or floor's
// menu opens its sheet, "House settings" opens the house sheet. Rendered
// against the live house on the v1.20 surface; the calls each editor sends.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '../src/adaptive-cover-house-card';
import type { AdaptiveCoverHouseCardConfig } from '../src/types';
import {
  FIXTURE_NOW,
  HUB_DEVICE,
  HUB_SETTINGS,
  houseFixture,
  layeredHouse,
  type HouseFixture,
  type HouseTestHass,
} from './fixtures/house-hass';

const TYPE = 'custom:adaptive-cover-house-card';
const UP = 'sensor.upstairs_indoor_temperature';

interface CardLike extends HTMLElement {
  hass?: HouseTestHass;
  updateComplete: Promise<boolean>;
  setConfig(config: AdaptiveCoverHouseCardConfig): void;
}

async function settle(el: CardLike): Promise<void> {
  for (let i = 0; i < 3; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
    await el.updateComplete;
    const body = el.shadowRoot!.querySelector('acp-settings-sheet') as
      | (HTMLElement & { updateComplete: Promise<boolean> })
      | null;
    if (body) await body.updateComplete;
  }
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
const text = (node: Element | null | undefined) =>
  (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

function body(el: CardLike): ShadowRoot {
  const node = $(el, 'acp-settings-sheet');
  expect(node, 'settings sheet body').toBeTruthy();
  return node!.shadowRoot!;
}

function row(el: CardLike, key: string): HTMLElement {
  const node = body(el).querySelector<HTMLElement>(`.row[data-key="${key}"]`);
  expect(node, `row ${key}`).toBeTruthy();
  return node!;
}

async function click(el: CardLike, node: Element | null | undefined): Promise<void> {
  expect(node, 'element to click').toBeTruthy();
  (node as HTMLElement).click();
  await settle(el);
}

async function type(el: CardLike, key: string, value: string): Promise<void> {
  const input = row(el, key).querySelector<HTMLInputElement>('input')!;
  input.value = value;
  input.dispatchEvent(new Event('input'));
  await settle(el);
}

async function openRoom(el: CardLike, areaId: string): Promise<void> {
  await click(el, $(el, `.room[data-room="${areaId}"] .menu-btn`));
  await click(el, $(el, `.room[data-room="${areaId}"] .menu-item[data-item="room-settings"]`));
}

async function openFloor(el: CardLike, floorId: string): Promise<void> {
  await click(el, $(el, `[data-floor="${floorId}"] .menu-btn`));
  await click(el, $(el, `[data-floor="${floorId}"] .menu-item[data-item="floor-settings"]`));
}

let fx: HouseFixture;
let hass: HouseTestHass;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(FIXTURE_NOW));
  fx = houseFixture();
  hass = layeredHouse(fx);
});
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('menus', () => {
  it('every room card and floor header has a menu; unassigned groups have none', async () => {
    const el = await mount(hass);
    const menus = Array.from(el.shadowRoot!.querySelectorAll('.menu-btn')).map((b) =>
      b.getAttribute('data-menu'),
    );
    expect(menus).toEqual([
      'floor:upstairs',
      'area:master_bedroom',
      'area:office',
      'area:sw_bedroom',
      'floor:main',
      'area:family_room',
      'floor:ground',
      'area:den',
    ]);
    const btn = $(el, '.room[data-room="office"] .menu-btn')!;
    expect(btn.getAttribute('aria-label')).toBe('More for Office');
    await click(el, btn);
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    expect(text($(el, '.menu'))).toBe('Room settings');
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle(el);
    expect($(el, '.menu')).toBeNull();
    // A click elsewhere on the card closes it too; opening another switches.
    await click(el, btn);
    await click(el, $(el, '[data-floor="main"] .menu-btn'));
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(text($(el, '.menu'))).toBe('Floor settings');
    await click(el, $(el, 'h1'));
    expect($(el, '.menu')).toBeNull();
    expect(hass.callService).not.toHaveBeenCalled();
  });
});

describe('the room sheet', () => {
  it('shows each setting: this room’s value or where it comes from, and the house value', async () => {
    const el = await mount(hass);
    await openRoom(el, 'office');
    const sheet = $(el, '.settings-sheet')!;
    expect(sheet.getAttribute('data-level')).toBe('area');
    expect(sheet.getAttribute('data-id')).toBe('office');
    expect(text(sheet.querySelector('.sheet-title'))).toBe('Room settings Office');
    expect(hass.callWS).toHaveBeenCalledWith({
      type: 'call_service',
      domain: 'adaptive_cover',
      service: 'get_profile',
      service_data: {},
      return_response: true,
    });

    const sections = Array.from(body(el).querySelectorAll('.section h3')).map((h) => text(h));
    expect(sections).toEqual([
      'Hand moves',
      'Climate',
      'Daily schedule',
      'Positions',
      'Glare',
      'Privacy',
    ]);

    const start = row(el, 'start_time');
    expect(text(start.querySelector('.state'))).toBe('This room: 07:30');
    expect(text(start.querySelector('.house'))).toBe('House: Midnight');
    expect(start.querySelector<HTMLInputElement>('input')!.value).toBe('07:30');
    expect(text(start.querySelector('.reset'))).toBe('Reset to house');

    expect(text(row(el, 'sunrise_offset').querySelector('.state'))).toBe(
      'This room: 45 min after sunrise',
    );
    const low = row(el, 'temp_low');
    expect(text(low.querySelector('.state'))).toBe('From the house: 72 °F');
    expect(low.querySelector('.reset')).toBeNull();
    expect(low.querySelector<HTMLInputElement>('input')!.value).toBe('72');
    expect(text(low.querySelector('.save'))).toBe('Set for this room');

    const sensor = row(el, 'temp_entity');
    expect(text(sensor.querySelector('.state'))).toBe(`From Upstairs: ${UP}`);
    expect(text(sensor.querySelector('.house'))).toBe('Set per floor');

    const climate = row(el, 'climate_on');
    expect(climate.querySelector('.seg-btn[data-value="on"]')!.getAttribute('aria-pressed')).toBe(
      'true',
    );
    // The office windows have no window exceptions.
    expect(body(el).querySelector('.windows')).toBeNull();
  });

  it('Save stores the room value with set_profile (area + id)', async () => {
    const el = await mount(hass);
    await openRoom(el, 'office');
    await type(el, 'start_time', '07:45');
    await click(el, row(el, 'start_time').querySelector('.save'));
    await type(el, 'manual_override_duration', '240');
    await click(el, row(el, 'manual_override_duration').querySelector('.save'));
    await click(el, row(el, 'climate_on').querySelector('.seg-btn[data-value="off"]'));
    expect(hass.callService.mock.calls).toEqual([
      ['adaptive_cover', 'set_profile', { scope: 'area', id: 'office', start_time: '07:45:00' }],
      [
        'adaptive_cover',
        'set_profile',
        {
          scope: 'area',
          id: 'office',
          manual_override_duration: { hours: 4, minutes: 0, seconds: 0 },
        },
      ],
      ['adaptive_cover', 'set_profile', { scope: 'area', id: 'office', climate_on: false }],
    ]);
    // The sheet shows what it stored.
    expect(text(row(el, 'start_time').querySelector('.state'))).toBe('This room: 07:45');
    expect(text(row(el, 'climate_on').querySelector('.state'))).toBe('This room: Off');
  });

  it('Set for this room stores the shown value as is', async () => {
    const el = await mount(hass);
    await openRoom(el, 'office');
    await click(el, row(el, 'temp_high').querySelector('.save'));
    expect(hass.callService.mock.calls).toEqual([
      ['adaptive_cover', 'set_profile', { scope: 'area', id: 'office', temp_high: 75 }],
    ]);
  });

  it('Reset to house sends null and the row uses the house value again', async () => {
    const el = await mount(hass);
    await openRoom(el, 'office');
    await click(el, row(el, 'start_time').querySelector('.reset'));
    expect(hass.callService.mock.calls).toEqual([
      ['adaptive_cover', 'set_profile', { scope: 'area', id: 'office', start_time: null }],
    ]);
    expect(text(row(el, 'start_time').querySelector('.state'))).toBe('From the house: Midnight');
    expect(row(el, 'start_time').querySelector('.reset')).toBeNull();
  });

  it('lists the windows with their own values and opens one', async () => {
    const el = await mount(hass);
    await openRoom(el, 'master_bedroom');
    const wins = Array.from(body(el).querySelectorAll<HTMLElement>('.windows .win'));
    expect(wins.map((w) => text(w))).toEqual([
      'Master door Position when the sun is not on the glass, Evening position',
      'Master south Privacy delay after sunset (kept from before), Privacy position (kept from before)',
      'Master trap Start following the sun (kept from before), Evening position from (kept from before)',
    ]);
    expect(
      Array.from(row(el, 'default_percentage').querySelectorAll('.exc')).map((c) => text(c)),
    ).toEqual(['Master door · 100%']);
    expect(
      Array.from(row(el, 'sunset_offset').querySelectorAll('.exc')).map((c) => text(c)),
    ).toEqual(['Master trap · 15 min after sunset (kept from before)']);
    // Values the Position sensor does not show come from get_profile (window).
    expect(
      Array.from(row(el, 'privacy_offset').querySelectorAll('.exc')).map((c) => text(c)),
    ).toEqual(['Master south · 30 min (kept from before)']);
    expect(
      Array.from(row(el, 'sunrise_offset').querySelectorAll('.exc')).map((c) => text(c)),
    ).toEqual(['Master trap · At sunrise (kept from before)']);
    await click(el, wins[0]);
    expect($(el, '.settings-sheet')).toBeNull();
    expect(text($(el, '.sheet .sheet-title h2'))).toBe('Door');
  });

  it('without get_profile: provenance still says what the room sets', async () => {
    const older = layeredHouse(fx, undefined, { profiles: 'missing' });
    const el = await mount(older);
    await openRoom(el, 'office');
    expect($(el, '.settings-sheet .not-lifted')).toBeNull();
    const start = row(el, 'start_time');
    expect(text(start.querySelector('.state'))).toBe('Set for this room');
    expect(start.querySelector<HTMLInputElement>('input')!.value).toBe('');
    expect(start.querySelector<HTMLButtonElement>('.save')!.disabled).toBe(true);
    // Values the Position sensors show are known anyway.
    expect(text(row(el, 'default_percentage').querySelector('.state'))).toBe('This room: 100%');
    expect(text(row(el, 'default_percentage').querySelector('.house'))).toBe('House: 99%');
    await type(el, 'start_time', '08:00');
    expect(start.querySelector<HTMLButtonElement>('.save')!.disabled).toBe(false);
  });

  it('a house without layered settings yet: a notice, and nothing can be stored', async () => {
    const early = layeredHouse(fx, undefined, { profiles: 'not_lifted' });
    const el = await mount(early);
    await openRoom(el, 'office');
    expect(text($(el, '.settings-sheet .not-lifted'))).toMatch(
      /^House settings are not available yet/,
    );
    const start = row(el, 'start_time');
    expect(start.querySelector<HTMLButtonElement>('.save')!.disabled).toBe(true);
    expect(start.querySelector<HTMLButtonElement>('.reset')!.disabled).toBe(true);
    expect(start.querySelector<HTMLInputElement>('input')!.disabled).toBe(true);
    const climate = row(el, 'climate_on').querySelector<HTMLButtonElement>('.seg-btn');
    expect(climate!.disabled).toBe(true);
  });

  it('a failed save is a notification and changes nothing', async () => {
    hass.callService.mockRejectedValueOnce(new Error('not settable on a area'));
    const el = await mount(hass);
    const seen: string[] = [];
    el.addEventListener('hass-notification', (e) =>
      seen.push((e as CustomEvent<{ message: string }>).detail.message),
    );
    await openRoom(el, 'office');
    await click(el, row(el, 'start_time').querySelector('.reset'));
    expect(seen).toEqual(['Adaptive Cover: not settable on a area']);
    expect(text(row(el, 'start_time').querySelector('.state'))).toBe('This room: 07:30');
  });

  it('closes with the close button, the scrim and Escape', async () => {
    const el = await mount(hass);
    await openRoom(el, 'office');
    await click(el, $(el, '.settings-sheet .close'));
    expect($(el, '.settings-sheet')).toBeNull();
    await openRoom(el, 'office');
    await click(el, $(el, '.scrim'));
    expect($(el, '.settings-sheet')).toBeNull();
    await openRoom(el, 'office');
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle(el);
    expect($(el, '.settings-sheet')).toBeNull();
  });
});

describe('the floor sheet', () => {
  it('shows the floor’s indoor sensor and the thresholds; saves and resets with scope floor', async () => {
    const el = await mount(hass);
    await openFloor(el, 'upstairs');
    const sheet = $(el, '.settings-sheet')!;
    expect(sheet.getAttribute('data-level')).toBe('floor');
    expect(text(sheet.querySelector('h2'))).toBe('Upstairs floor');
    const keys = Array.from(body(el).querySelectorAll<HTMLElement>('.row')).map(
      (r) => r.dataset.key,
    );
    expect(keys).toEqual(['temp_low', 'temp_high', 'temp_entity']);
    expect(text(row(el, 'temp_entity').querySelector('.state'))).toBe(`This floor: ${UP}`);
    await type(el, 'temp_low', '70');
    await click(el, row(el, 'temp_low').querySelector('.save'));
    await click(el, row(el, 'temp_entity').querySelector('.reset'));
    expect(hass.callService.mock.calls).toEqual([
      ['adaptive_cover', 'set_profile', { scope: 'floor', id: 'upstairs', temp_low: 70 }],
      ['adaptive_cover', 'set_profile', { scope: 'floor', id: 'upstairs', temp_entity: null }],
    ]);
  });

  it('rejects a threshold outside HA’s unit range', async () => {
    const el = await mount(hass);
    await openFloor(el, 'main');
    await type(el, 'temp_high', '120');
    expect(row(el, 'temp_high').querySelector<HTMLButtonElement>('.save')!.disabled).toBe(true);
  });
});

describe('the house sheet', () => {
  const value = (el: CardLike, key: string) => {
    const r = row(el, key);
    const input = r.querySelector<HTMLInputElement>('input');
    if (input) return input.value;
    return Array.from(r.querySelectorAll('.seg-btn.on, .opt.on')).map((b) => text(b));
  };

  it('House settings opens it: every house setting, the rare ones folded, and the device link', async () => {
    const el = await mount(hass);
    await click(el, $(el, '.house-bar .settings'));
    const sheet = $(el, '.settings-sheet')!;
    expect(sheet.getAttribute('data-level')).toBe('house');
    expect(text(sheet.querySelector('h2'))).toBe('House settings');
    expect(
      Array.from(body(el).querySelectorAll<HTMLElement>('.section')).map((x) => [
        x.dataset.section,
        x.tagName.toLowerCase(),
      ]),
    ).toEqual([
      ['hand', 'section'],
      ['climate', 'section'],
      ['schedule', 'section'],
      ['positions', 'section'],
      ['glare', 'section'],
      ['privacy', 'section'],
      ['movement', 'details'],
      ['sensors', 'details'],
    ]);
    // The house device's entities, then the stored house profile.
    expect(value(el, 'manual_override_duration')).toBe('120');
    expect(value(el, 'climate_on')).toEqual(['On']);
    expect(value(el, 'temp_low')).toBe('72');
    expect(value(el, 'end_time')).toBe('00:00');
    expect(value(el, 'quiet_start')).toBe('');
    expect(value(el, 'delta_position')).toBe('1');
    expect(value(el, 'default_percentage')).toBe('99');
    expect(value(el, 'weather_entity')).toBe('weather.forecast_home_2');
    expect(value(el, 'weather_state')).toEqual([
      'Clear',
      'Partly cloudy',
      'Sunny',
      'Windy',
      'Windy, cloudy',
    ]);
    // climate_mode is the setup-level switch, next to Climate control.
    expect(text(row(el, 'climate_mode').querySelector('.label'))).toBe(
      'Use climate inputs Setup: whether these windows read the climate inputs at all (a change reloads them)',
    );
    // Optional values can be cleared; nothing is reset or inherited here.
    expect(row(el, 'weather_entity').querySelector('.clear')).toBeTruthy();
    expect(row(el, 'quiet_start').querySelector('.clear')).toBeNull();
    expect(body(el).querySelector('.reset')).toBeNull();
    expect(body(el).querySelector('.state')).toBeNull();
    expect(sheet.querySelector('.more')!.getAttribute('href')).toBe(
      `/config/devices/device/${HUB_DEVICE}`,
    );
  });

  it('edits go to the house device’s entities, the rest to set_profile for the house', async () => {
    const el = await mount(hass);
    await click(el, $(el, '.house-bar .settings'));
    await click(el, row(el, 'climate_on').querySelector('.seg-btn[data-value="off"]'));
    await type(el, 'temp_low', '71');
    await click(el, row(el, 'temp_low').querySelector('.save'));
    await type(el, 'manual_override_duration', '90');
    await click(el, row(el, 'manual_override_duration').querySelector('.save'));
    await type(el, 'end_time', '21:30');
    await click(el, row(el, 'end_time').querySelector('.save'));
    await type(el, 'quiet_start', '22:00');
    await click(el, row(el, 'quiet_start').querySelector('.save'));
    await type(el, 'delta_position', '2');
    await click(el, row(el, 'delta_position').querySelector('.save'));
    await click(el, row(el, 'weather_state').querySelector('.opt[data-option="windy-variant"]'));
    await click(el, row(el, 'weather_state').querySelector('.save'));
    await click(el, row(el, 'weather_entity').querySelector('.clear'));
    expect(hass.callService.mock.calls).toEqual([
      ['switch', 'turn_off', { entity_id: [HUB_SETTINGS.climate_on] }],
      ['number', 'set_value', { entity_id: [HUB_SETTINGS.temp_low], value: 71 }],
      ['number', 'set_value', { entity_id: [HUB_SETTINGS.manual_override_duration], value: 90 }],
      ['time', 'set_value', { entity_id: [HUB_SETTINGS.end_time], time: '21:30:00' }],
      ['time', 'set_value', { entity_id: [HUB_SETTINGS.quiet_start], time: '22:00:00' }],
      ['adaptive_cover', 'set_profile', { scope: 'house', delta_position: 2 }],
      [
        'adaptive_cover',
        'set_profile',
        { scope: 'house', weather_state: ['sunny', 'partlycloudy', 'clear', 'windy'] },
      ],
      ['adaptive_cover', 'set_profile', { scope: 'house', weather_entity: null }],
    ]);
    // The sheet shows what it stored.
    expect(value(el, 'quiet_start')).toBe('22:00');
    expect(row(el, 'quiet_start').querySelector('.clear')).toBeTruthy();
    expect(row(el, 'weather_entity').querySelector('.clear')).toBeNull();
  });

  it('Save stays off until the value changes', async () => {
    const el = await mount(hass);
    await click(el, $(el, '.house-bar .settings'));
    const save = row(el, 'eye_height').querySelector<HTMLButtonElement>('.save')!;
    expect(save.disabled).toBe(true);
    await type(el, 'eye_height', '1.2');
    expect(save.disabled).toBe(true);
    await type(el, 'eye_height', '1.25');
    expect(save.disabled).toBe(false);
  });

  it('More house settings navigates to the house device', async () => {
    const el = await mount(hass);
    await click(el, $(el, '.house-bar .settings'));
    const pushed = vi.spyOn(history, 'pushState');
    await click(el, $(el, '.settings-sheet .more'));
    expect(pushed).toHaveBeenCalledWith(null, '', `/config/devices/device/${HUB_DEVICE}`);
    expect($(el, '.settings-sheet')).toBeNull();
    pushed.mockRestore();
  });

  it('an integration without set_profile has no settings menus and keeps the plain link', async () => {
    const older = {
      ...hass,
      services: { adaptive_cover: { hold: {}, change_settings: {} } },
    } as unknown as HouseTestHass;
    const el = await mount(older);
    expect($(el, '.menu-btn')).toBeNull();
    const pushed = vi.spyOn(history, 'pushState');
    await click(el, $(el, '.house-bar .settings'));
    expect($(el, '.settings-sheet')).toBeNull();
    expect(pushed).toHaveBeenCalledWith(null, '', `/config/devices/device/${HUB_DEVICE}`);
    pushed.mockRestore();
  });

  it('a card showing only some rooms keeps the plain link', async () => {
    const el = await mount(hass, { areas: ['office'] });
    const pushed = vi.spyOn(history, 'pushState');
    await click(el, $(el, '.house-bar .settings'));
    expect($(el, '.settings-sheet')).toBeNull();
    expect(pushed).toHaveBeenCalledWith(null, '', `/config/devices/device/${HUB_DEVICE}`);
    pushed.mockRestore();
  });
});

describe('phone layout', () => {
  it('an open room has Room settings; floor headers have their menu', async () => {
    const el = await mount(hass, { layout: 'narrow' });
    await click(el, $(el, '.room[data-room="office"] .room-toggle'));
    await click(el, $(el, '.room[data-room="office"] .room-settings'));
    expect($(el, '.settings-sheet.bottom')!.getAttribute('data-id')).toBe('office');
    await click(el, $(el, '.settings-sheet .close'));
    await openFloor(el, 'ground');
    expect($(el, '.settings-sheet')!.getAttribute('data-id')).toBe('ground');
  });
});
