// The card editors offer windows (not config entries) and save a pick as
// `window:`. A saved legacy `entry_id:` config is left untouched until the
// user picks a different window.
import { describe, it, expect, vi } from 'vitest';
import '../src/adaptive-cover-tile-card-editor';
import '../src/adaptive-cover-decision-card-editor';
import '../src/adaptive-cover-card-editor';
import type { HomeAssistant } from 'custom-card-helpers';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

type AnyConfig = Record<string, unknown> & { type: string };

interface EditorLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  setConfig(config: AnyConfig): void;
  _windows: { window_key: string; title: string }[] | null;
  _registry?: EntityRegistryEntry[] | null;
}

type HaFormLike = HTMLElement & { data?: Record<string, unknown> };

const WINDOWS = [
  { window_key: 'win_a', title: 'Kitchen' },
  { window_key: 'win_b', title: 'Living' },
];

function hassWith(callWS: (msg: { type: string }) => Promise<unknown>): HomeAssistant {
  return {
    states: {},
    callWS: vi.fn().mockImplementation(callWS),
    connection: { subscribeEvents: vi.fn().mockResolvedValue(() => {}) },
  } as unknown as HomeAssistant;
}

async function mount(tag: string, config: AnyConfig, hass?: HomeAssistant): Promise<EditorLike> {
  const el = document.createElement(tag) as EditorLike;
  el.hass = hass ?? hassWith(() => Promise.resolve([]));
  el._windows = WINDOWS;
  el.setConfig(config);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

function captureEmits(el: HTMLElement): AnyConfig[] {
  const out: AnyConfig[] = [];
  el.addEventListener('config-changed', (e: Event) => out.push((e as CustomEvent).detail.config));
  return out;
}

function lastOf(emits: AnyConfig[]): AnyConfig {
  expect(emits.length).toBeGreaterThan(0);
  return emits[emits.length - 1];
}

function fireValue(el: EditorLike, value: Record<string, unknown>): void {
  const form = el.shadowRoot!.querySelector('ha-form') as HTMLElement;
  form.dispatchEvent(
    new CustomEvent('value-changed', { bubbles: true, composed: true, detail: { value } }),
  );
}

describe.each([
  ['adaptive-cover-tile-card-editor', 'custom:adaptive-cover-tile-card'],
  ['adaptive-cover-decision-card-editor', 'custom:adaptive-cover-decision-card'],
])('%s', (tag, type) => {
  it('shows a legacy entry_id in the window picker', async () => {
    const el = await mount(tag, { type, entry_id: 'win_a' });
    const form = el.shadowRoot!.querySelector('ha-form') as HaFormLike;
    expect(form.data!.window).toBe('win_a');
    expect(form.data!.entry_id).toBeUndefined();
  });

  it('leaves a legacy entry_id untouched when another field changes', async () => {
    const el = await mount(tag, { type, entry_id: 'win_a' });
    const emits = captureEmits(el);
    fireValue(el, { type, window: 'win_a', title: 'Renamed', name: 'Renamed' });
    const last = lastOf(emits);
    expect(last.entry_id).toBe('win_a');
    expect(last.window).toBeUndefined();
  });

  it('saves a newly picked window as `window` and drops the legacy entry_id', async () => {
    const el = await mount(tag, { type, entry_id: 'win_a' });
    const emits = captureEmits(el);
    fireValue(el, { type, window: 'win_b' });
    const last = lastOf(emits);
    expect(last.window).toBe('win_b');
    expect(last.entry_id).toBeUndefined();
  });

  it('keeps a `window` config on `window`', async () => {
    const el = await mount(tag, { type, window: 'win_a' });
    const emits = captureEmits(el);
    fireValue(el, { type, window: 'win_b' });
    expect(lastOf(emits).window).toBe('win_b');
  });

  it('auto-selects the only window of a new card as `window`', async () => {
    const registry: EntityRegistryEntry[] = [
      {
        entity_id: 'sensor.only_cover_position',
        unique_id: 'win_only_Cover Position',
        platform: 'adaptive_cover',
        config_entry_id: 'house',
        config_subentry_id: 'win_only',
        device_id: null,
      },
    ];
    const hass = hassWith((msg) =>
      Promise.resolve(msg.type === 'config/entity_registry/list' ? registry : []),
    );
    const el = document.createElement(tag) as EditorLike;
    const emits = captureEmits(el);
    el.hass = hass;
    el.setConfig({ type });
    document.body.appendChild(el);
    await el.updateComplete;
    await vi.waitFor(() => expect(emits.some((c) => c.window === 'win_only')).toBe(true));
    expect(emits.find((c) => c.window === 'win_only')!.entry_id).toBeUndefined();
  });
});

describe('adaptive-cover-card-editor (main card)', () => {
  it('selects the legacy entry_id in the window <select> and saves a new pick as `window`', async () => {
    const el = await mount('adaptive-cover-card-editor', {
      type: 'custom:adaptive-cover-card',
      entry_id: 'win_a',
    });
    const select = el.shadowRoot!.querySelector('select.select') as HTMLSelectElement;
    expect(select.value).toBe('win_a');

    const emits = captureEmits(el);
    select.value = 'win_b';
    select.dispatchEvent(new Event('change'));
    const last = lastOf(emits);
    expect(last.window).toBe('win_b');
    expect(last.entry_id).toBeUndefined();
  });

  it('does not rewrite the config when the same window is re-picked', async () => {
    const el = await mount('adaptive-cover-card-editor', {
      type: 'custom:adaptive-cover-card',
      entry_id: 'win_a',
    });
    const select = el.shadowRoot!.querySelector('select.select') as HTMLSelectElement;
    const emits = captureEmits(el);
    select.value = 'win_a';
    select.dispatchEvent(new Event('change'));
    expect(emits).toEqual([]);
  });
});
