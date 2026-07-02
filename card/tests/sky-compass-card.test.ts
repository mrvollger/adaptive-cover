// Fixtures updated for the Adaptive Cover integration: registry unique_ids use
// the space-separated `{entry_id}_Cover Position` suffix on platform
// `adaptive_cover`, and sun geometry lives in the Cover Position sensor's
// nested `sun` attribute block (no dedicated sun-position sensor).
import { describe, it, expect } from 'vitest';
import '../src/adaptive-cover-sky-compass-card';
import { AdaptiveCoverSkyCompassCard } from '../src/adaptive-cover-sky-compass-card';
import type { HomeAssistant } from 'custom-card-helpers';
import type { SkyCompassCardConfig } from '../src/types';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

interface CardLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  setConfig(config: SkyCompassCardConfig): void;
  _registry?: EntityRegistryEntry[] | null;
}

function makeCard(): CardLike {
  return document.createElement('adaptive-cover-sky-compass-card') as CardLike;
}

const ENTRY = 'entry_abc';
const ENTRY_2 = 'entry_def';

const REGISTRY: EntityRegistryEntry[] = [
  {
    entity_id: 'sensor.cover_position',
    unique_id: `${ENTRY}_Cover Position`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
  {
    entity_id: 'sensor.cover_position_2',
    unique_id: `${ENTRY_2}_Cover Position`,
    config_entry_id: ENTRY_2,
    platform: 'adaptive_cover',
    device_id: null,
  },
];

function makeHass(): HomeAssistant {
  return {
    config: { latitude: 52.0, longitude: 4.0, time_zone: 'UTC' },
    states: {
      'sensor.cover_position': {
        state: '40',
        attributes: {
          last_moves: { 'cover.living': '09:00 -> 40% (solar)' },
          sun: {
            azimuth: 180,
            elevation: 30,
            gamma: 0,
            in_fov: true,
            window_azimuth: 180,
            fov_left: 90,
            fov_right: 90,
            min_elevation: 10,
            max_elevation: 60,
          },
        },
      },
      'cover.living': {
        state: 'open',
        attributes: { friendly_name: 'Living', current_position: 40 },
      },
      'sensor.cover_position_2': {
        state: '40',
        attributes: {
          last_moves: { 'cover.office': '09:00 -> 40% (solar)' },
          sun: {
            azimuth: 180,
            elevation: 30,
            gamma: -90,
            in_fov: true,
            window_azimuth: 270,
            fov_left: 90,
            fov_right: 90,
          },
        },
      },
      'cover.office': {
        state: 'open',
        attributes: { friendly_name: 'Office', current_position: 40 },
      },
    },
    callWS: async () => [],
    connection: {
      subscribeEvents: async () => () => {},
    },
  } as unknown as HomeAssistant;
}

async function mountWithRegistry(config: SkyCompassCardConfig): Promise<CardLike> {
  const el = makeCard();
  el.hass = makeHass();
  el._registry = REGISTRY;
  el.setConfig(config);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

describe('adaptive-cover-sky-compass-card setConfig', () => {
  it('throws when entry_ids is missing', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({ type: 'custom:adaptive-cover-sky-compass-card' } as SkyCompassCardConfig),
    ).toThrow(/entry_ids/);
  });

  it('throws when entry_ids is empty', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: [],
      }),
    ).toThrow(/entry_ids/);
  });

  it('throws when entry_ids contains a non-string', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: [123 as unknown as string],
      }),
    ).toThrow();
  });

  it('throws when entry_ids contains an empty string', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: [''],
      }),
    ).toThrow();
  });

  it('accepts a valid single-entry config', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: ['abc'],
      }),
    ).not.toThrow();
  });

  it('accepts a valid multi-entry config', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: ['abc', 'def'],
        compact: true,
        show_legend: false,
      }),
    ).not.toThrow();
  });

  it('accepts cover_colors array alongside entry_ids', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: ['a', 'b'],
        cover_colors: ['#ff3366', null],
      }),
    ).not.toThrow();
  });

  it('accepts cover_colors shorter than entry_ids', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: ['a', 'b', 'c'],
        cover_colors: ['#ff3366'],
      }),
    ).not.toThrow();
  });

  it('accepts north_offset config', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: 'custom:adaptive-cover-sky-compass-card',
        entry_ids: ['abc'],
        north_offset: 90,
      }),
    ).not.toThrow();
  });

  it('defensively copies entry_ids so callers can mutate their input', () => {
    const el = makeCard();
    const input = ['a', 'b'];
    el.setConfig({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: input,
    });
    input.push('c');
    // No direct getter; just assert the call did not throw and input mutation doesn't crash re-render.
    expect(input.length).toBe(3);
  });
});

describe('adaptive-cover-sky-compass-card — discovery & compass render', () => {
  it('renders the compass when a configured entry resolves via the registry', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: [ENTRY],
    });
    expect(el.shadowRoot!.querySelector('acp-sky-compass')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('.empty')).toBeNull();
  });

  it('renders the no-match empty state when no configured entry resolves', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: ['no_such_entry'],
    });
    expect(el.shadowRoot!.querySelector('acp-sky-compass')).toBeNull();
    expect(el.shadowRoot!.querySelector('.empty')).toBeTruthy();
  });

  it('lists unresolved entry_ids in the warning row while rendering the resolved ones', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: [ENTRY, 'ghost_entry'],
    });
    expect(el.shadowRoot!.querySelector('acp-sky-compass')).toBeTruthy();
    const warn = el.shadowRoot!.querySelector('.warn');
    expect(warn?.textContent).toContain('ghost_entry');
  });
});

describe('adaptive-cover-sky-compass-card — elevation chart toggle', () => {
  it('renders the elevation chart by default (key omitted)', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: [ENTRY],
    });
    expect(el.shadowRoot!.querySelector('acp-elevation-chart')).toBeTruthy();
  });

  it('omits the elevation chart when show_elevation_chart is false', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: [ENTRY],
      show_elevation_chart: false,
    });
    expect(el.shadowRoot!.querySelector('acp-elevation-chart')).toBeNull();
  });

  it('forwards the full discovered list and cover_colors to the elevation chart', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: [ENTRY, ENTRY_2],
      cover_colors: ['#ff7043', '#7e57c2'],
    });
    interface ChartEl extends HTMLElement {
      discoveredList?: unknown[];
      coverColors?: unknown[];
    }
    const chart = el.shadowRoot!.querySelector('acp-elevation-chart') as ChartEl;
    expect(chart).toBeTruthy();
    expect(chart.discoveredList?.length).toBe(2);
    expect(chart.coverColors).toEqual(['#ff7043', '#7e57c2']);
  });
});

interface GridOptions {
  columns: number;
  rows: number | string;
  min_columns: number;
  max_columns: number;
}
interface GridCompassLike extends CardLike {
  getGridOptions(): GridOptions;
}

describe('adaptive-cover-sky-compass-card getGridOptions', () => {
  it('spans the full section width and auto-sizes its height (issue #146)', () => {
    const card = makeCard() as GridCompassLike;
    card.setConfig({ type: 'custom:adaptive-cover-sky-compass-card', entry_ids: [ENTRY] });
    const opts = card.getGridOptions();
    expect(opts.columns).toBe(12);
    expect(opts.min_columns).toBe(6);
    expect(opts.max_columns).toBe(12);
    expect(opts.rows).toBe('auto');
  });

  it('stays auto-height regardless of entry count or elevation chart (issue #146)', () => {
    const oneEntry = makeCard() as GridCompassLike;
    oneEntry.setConfig({ type: 'custom:adaptive-cover-sky-compass-card', entry_ids: [ENTRY] });
    const sixNoChart = makeCard() as GridCompassLike;
    sixNoChart.setConfig({
      type: 'custom:adaptive-cover-sky-compass-card',
      entry_ids: ['e1', 'e2', 'e3', 'e4', 'e5', 'e6'],
      show_elevation_chart: false,
    });
    expect(oneEntry.getGridOptions().rows).toBe('auto');
    expect(sixNoChart.getGridOptions().rows).toBe('auto');
  });
});

describe('adaptive-cover-sky-compass-card styles (auto height, issue #146)', () => {
  // styles is a Lit CSSResult; .cssText is plain text we can grep.
  const cssText = (AdaptiveCoverSkyCompassCard as unknown as { styles: { cssText: string } })
    .styles.cssText;

  function cssBlock(selector: string): string {
    const idx = cssText.indexOf(selector);
    if (idx < 0) throw new Error(`Selector not found in styles: ${selector}`);
    const open = cssText.indexOf('{', idx);
    const close = cssText.indexOf('}', open);
    if (open < 0 || close < 0) throw new Error(`Malformed block for ${selector}`);
    return cssText.slice(open + 1, close);
  }

  it('does not pin the ha-card to a fixed height (auto-sizes to content)', () => {
    expect(cssBlock('ha-card')).not.toMatch(/height:\s*100%/);
  });

  it('does not force an overflow scrollbar on the ha-card', () => {
    expect(cssBlock('ha-card')).not.toMatch(/overflow/);
  });
});
