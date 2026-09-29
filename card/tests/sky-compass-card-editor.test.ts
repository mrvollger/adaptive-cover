import { describe, it, expect } from 'vitest';
import '../src/adaptive-cover-sky-compass-card-editor';
import type { SkyCompassCardConfig } from '../src/types';

interface EditorLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: unknown;
  setConfig(config: SkyCompassCardConfig): void;
  _windows: { window_key: string; title: string }[] | null;
  _onCoverColorChange(index: number, value: string): void;
  _onCoverColorReset(index: number): void;
  _onWindowToggle(key: string, enabled: boolean): void;
  _onToggle(key: string, enabled: boolean): void;
  _onNorthOffsetChange(e: Event): void;
}

function makeEditor(): EditorLike {
  const el = document.createElement('adaptive-cover-sky-compass-card-editor') as EditorLike;
  el.hass = { states: {}, callWS: async () => [] };
  return el;
}

describe('editor north_offset', () => {
  it('emits north_offset in config-changed when changed', () => {
    const el = makeEditor();
    el._windows = [{ window_key: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:x', entry_ids: ['a'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    const fakeEvent = { target: { value: '90' } } as unknown as Event;
    el._onNorthOffsetChange(fakeEvent);
    expect(emitted).not.toBeNull();
    expect(emitted!.north_offset).toBe(90);
  });

  it('non-numeric north_offset input emits 0', () => {
    const el = makeEditor();
    el._windows = [{ window_key: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:x', entry_ids: ['a'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    const fakeEvent = { target: { value: 'abc' } } as unknown as Event;
    el._onNorthOffsetChange(fakeEvent);
    expect(emitted!.north_offset).toBe(0);
  });
});

describe('editor show_elevation_chart toggle', () => {
  it('emits show_elevation_chart in config-changed when toggled off', () => {
    const el = makeEditor();
    el._windows = [{ window_key: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:x', entry_ids: ['a'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onToggle('show_elevation_chart', false);
    expect(emitted).not.toBeNull();
    expect(emitted!.show_elevation_chart).toBe(false);
  });

  it('renders a show_elevation_chart checkbox in the display toggles, defaulting on', async () => {
    const el = makeEditor();
    el._windows = [{ window_key: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:x', entry_ids: ['a'] });
    document.body.appendChild(el);
    await el.updateComplete;

    const labels = Array.from(el.shadowRoot!.querySelectorAll('.toggle-label')).map(
      (n) => n.textContent?.trim() ?? '',
    );
    expect(labels).toContain('Sun-today chart');
  });
});

describe('editor cover_colors', () => {
  it('emits cover_colors on color change', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({ type: 'custom:x', entry_ids: ['a', 'b'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorChange(0, '#ff3366');
    expect(emitted).not.toBeNull();
    expect(emitted!.cover_colors).toEqual(['#ff3366']);
  });

  it('setting a second slot preserves the first', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({ type: 'custom:x', entry_ids: ['a', 'b'], cover_colors: ['#ff3366'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorChange(1, '#00aaff');
    expect(emitted!.cover_colors).toEqual(['#ff3366', '#00aaff']);
  });

  it('Reset clears a single slot; all-null array is omitted from config', () => {
    const el = makeEditor();
    el._windows = [{ window_key: 'a', title: 'Kitchen' }];
    el.setConfig({ type: 'custom:x', entry_ids: ['a'], cover_colors: ['#ff3366'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorReset(0);
    expect(emitted!.cover_colors).toBeUndefined();
  });

  it('Reset of one slot keeps other overrides', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({
      type: 'custom:x',
      entry_ids: ['a', 'b'],
      cover_colors: ['#ff3366', '#00aaff'],
    });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onCoverColorReset(0);
    expect(emitted!.cover_colors).toEqual([null, '#00aaff']);
  });

  it('toggling a legacy entry off saves `windows` and re-aligns cover_colors', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({
      type: 'custom:x',
      entry_ids: ['a', 'b'],
      cover_colors: ['#ff3366', '#00aaff'],
    });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onWindowToggle('a', false);
    expect(emitted!.windows).toEqual(['b']);
    expect(emitted!.entry_ids).toBeUndefined();
    expect(emitted!.cover_colors).toEqual(['#00aaff']);
  });

  it('toggling a legacy entry off with only that entry colored omits cover_colors', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({
      type: 'custom:x',
      entry_ids: ['a', 'b'],
      cover_colors: ['#ff3366', null],
    });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onWindowToggle('a', false);
    expect(emitted!.windows).toEqual(['b']);
    expect(emitted!.entry_ids).toBeUndefined();
    expect(emitted!.cover_colors).toBeUndefined();
  });
});

describe('editor window selection', () => {
  it('toggling a window on appends it to `windows` in picker order', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    el.setConfig({ type: 'custom:x', windows: ['b'] });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onWindowToggle('a', true);
    expect(emitted!.windows).toEqual(['a', 'b']);
  });

  it('keeps `covers` bindings and their colors when a window is toggled', () => {
    const el = makeEditor();
    el._windows = [
      { window_key: 'a', title: 'Kitchen' },
      { window_key: 'b', title: 'Living' },
    ];
    // Overlay order: windows, covers, entry_ids → a, cover.x, b.
    el.setConfig({
      type: 'custom:x',
      windows: ['a'],
      covers: ['cover.x'],
      entry_ids: ['b'],
      cover_colors: ['#111111', '#222222', '#333333'],
    });

    let emitted: SkyCompassCardConfig | null = null;
    el.addEventListener('config-changed', (e: Event) => {
      emitted = (e as CustomEvent).detail.config;
    });

    el._onWindowToggle('a', false);
    // New order: windows [b], covers [cover.x].
    expect(emitted!.windows).toEqual(['b']);
    expect(emitted!.covers).toEqual(['cover.x']);
    expect(emitted!.entry_ids).toBeUndefined();
    expect(emitted!.cover_colors).toEqual(['#333333', '#222222']);
  });
});
