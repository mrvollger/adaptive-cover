/// <reference types="node" />
// The Mode chips tile card feature (type: custom:adaptive-cover-mode):
// registration, which tiles it fits, and the calls each chip sends.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HomeAssistant } from 'custom-card-helpers';

import '../src/adaptive-cover-mode-feature';
import { modeFeatureSupported, modeTarget } from '../src/adaptive-cover-mode-feature';
import {
  FIXTURE_NOW,
  HUB_MODE_SELECT,
  houseFixture,
  mixedHouse,
  p5House,
  type HouseFixture,
  type HouseTestHass,
} from './fixtures/house-hass';

const TYPE = 'adaptive-cover-mode';

interface FeatureLike extends HTMLElement {
  hass?: HomeAssistant;
  context?: { entity_id?: string };
  stateObj?: { entity_id: string };
  updateComplete: Promise<boolean>;
  setConfig(config: { type: string }): void;
}

async function mount(
  hass: HouseTestHass,
  entityId: string,
  how: 'context' | 'stateObj' = 'context',
): Promise<FeatureLike> {
  const el = document.createElement(TYPE) as FeatureLike;
  el.setConfig({ type: `custom:${TYPE}` });
  el.hass = hass;
  if (how === 'context') el.context = { entity_id: entityId };
  else el.stateObj = { entity_id: entityId };
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

const chips = (el: FeatureLike) =>
  Array.from(el.shadowRoot!.querySelectorAll<HTMLElement>('.chip')).map((c) => [
    c.dataset.mode,
    c.getAttribute('aria-pressed'),
    c.getAttribute('aria-disabled'),
  ]);

async function press(el: FeatureLike, mode: string): Promise<void> {
  el.shadowRoot!.querySelector<HTMLElement>(`.chip[data-mode="${mode}"]`)!.click();
  await new Promise((r) => setTimeout(r, 0));
  await el.updateComplete;
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

describe('registration', () => {
  it('is listed in window.customCardFeatures with an editor', async () => {
    const entry = window.customCardFeatures!.find((f) => f.type === TYPE);
    expect(entry).toMatchObject({ type: TYPE, name: 'Adaptive Cover mode', configurable: true });
    expect(typeof entry!.supported).toBe('function');
    const Feature = customElements.get(TYPE) as unknown as {
      getStubConfig(): unknown;
      getConfigElement(): Promise<HTMLElement>;
    };
    expect(Feature.getStubConfig()).toEqual({ type: `custom:${TYPE}` });
    const editor = (await Feature.getConfigElement()) as HTMLElement & {
      setConfig(c: unknown): void;
      hass?: unknown;
      context?: unknown;
      updateComplete: Promise<boolean>;
    };
    expect(editor.tagName.toLowerCase()).toBe('adaptive-cover-mode-editor');
    editor.setConfig({ type: `custom:${TYPE}` });
    editor.hass = fx.hass;
    editor.context = { entity_id: 'light.kitchen' };
    document.body.appendChild(editor);
    await editor.updateComplete;
    expect(editor.shadowRoot!.textContent).toMatch(/It has no options/);
    expect(editor.shadowRoot!.querySelector('.warn')!.textContent).toMatch(/Not an Adaptive Cover/);
  });

  it('rejects a missing config', () => {
    const el = document.createElement(TYPE) as FeatureLike;
    expect(() => el.setConfig(undefined as unknown as { type: string })).toThrow();
  });
});

describe('which tiles it fits', () => {
  it('with a state object (older HA): Mode selects and covers', () => {
    const hass = p5House(fx);
    const mode = fx.eid('Office north', 'mode');
    expect(modeFeatureSupported({ ...hass.states[mode], entity_id: mode })).toBe(true);
    expect(
      modeFeatureSupported({
        entity_id: fx.eid('Office north', 'mode'),
        attributes: { options: ['Manual', 'Sun tracking'] },
      }),
    ).toBe(false);
    expect(modeFeatureSupported({ entity_id: 'cover.office_north_shades' })).toBe(true);
    expect(modeFeatureSupported({ entity_id: 'light.kitchen' })).toBe(false);
    expect(modeFeatureSupported(undefined)).toBe(false);
  });

  it('with (hass, context): the window’s entities and the house entities', () => {
    const hass = p5House(fx);
    const ok = (entity_id: string) => modeFeatureSupported(hass, { entity_id });
    expect(ok(fx.eid('Office north', 'mode'))).toBe(true);
    expect(ok('cover.office_north_shades')).toBe(true);
    expect(ok(fx.eid('Office north', 'position'))).toBe(true);
    expect(ok(HUB_MODE_SELECT)).toBe(true);
    expect(ok('cover.adaptive_cover_all')).toBe(true);
    expect(ok('light.kitchen')).toBe(false);
  });

  it('resolves a tile entity to its window or the house', () => {
    const hass = p5House(fx);
    const target = modeTarget(hass, 'cover.office_north_shades');
    expect(target?.kind).toBe('window');
    expect(target && target.kind === 'window' ? target.window.deviceName : null).toBe(
      'Office north',
    );
    expect(modeTarget(hass, HUB_MODE_SELECT)?.kind).toBe('house');
    expect(modeTarget(hass, undefined)).toBeNull();
  });
});

describe('a window tile', () => {
  it('shows the window’s mode; Auto and Off are select_option, Hold is adaptive_cover.hold', async () => {
    const hass = p5House(fx, mixedHouse(fx));
    const mode = fx.eid('Office north', 'mode');
    const el = await mount(hass, mode);
    expect(chips(el)).toEqual([
      ['auto', 'false', 'false'],
      ['hold', 'true', 'false'],
      ['off', 'false', 'false'],
    ]);
    await press(el, 'hold'); // already on hold: nothing
    await press(el, 'auto');
    await press(el, 'off');
    expect(hass.callService.mock.calls).toEqual([
      ['select', 'select_option', { entity_id: [mode], option: 'auto' }],
      ['select', 'select_option', { entity_id: [mode], option: 'off' }],
    ]);
  });

  it('on the window’s cover tile (context or stateObj) it drives the window', async () => {
    const hass = p5House(fx, mixedHouse(fx));
    const mode = fx.eid('Den west', 'mode');
    for (const how of ['context', 'stateObj'] as const) {
      hass.callService.mockClear();
      const el = await mount(hass, 'cover.den_west_shades', how);
      expect(chips(el).map((c) => c[1])).toEqual(['false', 'false', 'true']);
      await press(el, 'hold');
      expect(hass.callService.mock.calls).toEqual([
        ['adaptive_cover', 'hold', { entity_id: [mode] }],
      ]);
      el.remove();
    }
  });

  it('before P5 Hold is disabled and sends nothing', async () => {
    const el = await mount(fx.hass, fx.eid('Office north', 'mode'));
    expect(chips(el)[1]).toEqual(['hold', 'false', 'true']);
    expect(el.shadowRoot!.querySelector('.chip.hold')!.getAttribute('title')).toMatch(/by hand/);
    await press(el, 'hold');
    expect(fx.hass.callService).not.toHaveBeenCalled();
  });

  it('renders nothing for an entity that is not a window', async () => {
    const el = await mount(fx.hass, 'light.kitchen');
    expect(el.shadowRoot!.querySelector('.chips')).toBeNull();
  });

  it('follows the window’s mode', async () => {
    const hass = p5House(fx);
    const mode = fx.eid('Office north', 'mode');
    const el = await mount(hass, mode);
    expect(chips(el)[0][1]).toBe('true');
    el.hass = {
      ...hass,
      states: { ...hass.states, [mode]: { ...hass.states[mode], state: 'off' } },
    };
    await el.updateComplete;
    expect(chips(el).map((c) => c[1])).toEqual(['false', 'false', 'true']);
  });
});

describe('the house tile', () => {
  it('Mixed presses nothing; a chip sets the house select', async () => {
    const hass = p5House(fx, mixedHouse(fx));
    const el = await mount(hass, HUB_MODE_SELECT);
    expect(chips(el).map((c) => c[1])).toEqual(['false', 'false', 'false']);
    await press(el, 'hold');
    await press(el, 'auto');
    expect(hass.callService.mock.calls).toEqual([
      ['select', 'select_option', { entity_id: [HUB_MODE_SELECT], option: 'hold' }],
      ['select', 'select_option', { entity_id: [HUB_MODE_SELECT], option: 'auto' }],
    ]);
  });

  it('a failed call is a notification', async () => {
    const hass = p5House(fx);
    hass.callService.mockRejectedValueOnce(new Error('boom'));
    const el = await mount(hass, 'cover.adaptive_cover_all');
    const seen: string[] = [];
    el.addEventListener('hass-notification', (e) =>
      seen.push((e as CustomEvent<{ message: string }>).detail.message),
    );
    await press(el, 'off');
    expect(seen).toEqual(['Adaptive Cover: boom']);
  });
});
