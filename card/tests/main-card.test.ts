// Fixtures updated for the Adaptive Cover integration: registry unique_ids use
// the space-separated `{entry_id}_Cover Position` / `{entry_id}_Toggle Control`
// suffixes on platform `adaptive_cover`; sun geometry and managed covers come
// from the Cover Position sensor's `sun` / `last_moves` attributes. The header
// now carries only the Auto pill (Toggle Control switch) — the Pro-era
// integration-enabled pill is gone.
import { describe, it, expect } from 'vitest';
import '../src/adaptive-cover-card';
import { AdaptiveCoverCard } from '../src/adaptive-cover-card';
import type { HomeAssistant } from 'custom-card-helpers';
import type { AdaptiveCoverCardConfig } from '../src/types';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

interface CardLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  setConfig(config: AdaptiveCoverCardConfig): void;
  _registry?: EntityRegistryEntry[] | null;
}

const ENTRY = 'entry_abc';

const REGISTRY: EntityRegistryEntry[] = [
  {
    entity_id: 'sensor.cover_position',
    unique_id: `${ENTRY}_Cover Position`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
  {
    entity_id: 'switch.toggle_control',
    unique_id: `${ENTRY}_Toggle Control`,
    config_entry_id: ENTRY,
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
          intent: 'calculated',
          decision_trace: ['sun in view: tracking'],
          last_moves: { 'cover.living': '09:00 -> 40% (solar)' },
          sun: {
            azimuth: 180,
            elevation: 30,
            gamma: 0,
            in_fov: true,
            window_azimuth: 180,
            fov_left: 90,
            fov_right: 90,
          },
        },
      },
      'switch.toggle_control': { state: 'on', attributes: {} },
      'cover.living': {
        state: 'open',
        attributes: { friendly_name: 'Living', current_position: 40 },
      },
    },
    callWS: async () => [],
    connection: {
      subscribeEvents: async () => () => {},
    },
  } as unknown as HomeAssistant;
}

async function mountWithRegistry(
  config: AdaptiveCoverCardConfig,
  registry: EntityRegistryEntry[] = REGISTRY,
): Promise<CardLike> {
  const el = document.createElement('adaptive-cover-card') as CardLike;
  el.hass = makeHass();
  el._registry = registry;
  el.setConfig(config);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

describe('adaptive-cover-card cover_colors (issue #132)', () => {
  it('forwards cover_colors to the embedded sky compass', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
      cover_colors: ['#ff3366'],
    });
    interface CompassEl extends HTMLElement {
      coverColors?: unknown[];
    }
    const compass = el.shadowRoot!.querySelector('acp-sky-compass') as CompassEl;
    expect(compass).toBeTruthy();
    expect(compass.coverColors).toEqual(['#ff3366']);
  });

  it('passes an empty array when cover_colors is omitted', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
    });
    interface CompassEl extends HTMLElement {
      coverColors?: unknown[];
    }
    const compass = el.shadowRoot!.querySelector('acp-sky-compass') as CompassEl;
    expect(compass).toBeTruthy();
    expect(compass.coverColors).toEqual([]);
  });

  it('forwards cover_colors to the embedded Sun Today elevation chart', async () => {
    // The standalone sky-compass card already wires this; the root card must too
    // so the override carries into the Sun Today chart, not just the compass.
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
      cover_colors: ['#ff3366'],
    });
    interface ChartEl extends HTMLElement {
      coverColors?: unknown[];
    }
    const chart = el.shadowRoot!.querySelector('acp-elevation-chart') as ChartEl;
    expect(chart).toBeTruthy();
    expect(chart.coverColors).toEqual(['#ff3366']);
  });
});

interface GridOptions {
  columns: number;
  rows: number | string;
  min_columns: number;
  max_columns: number;
}
interface GridCardLike extends CardLike {
  getGridOptions(): GridOptions;
}

describe('AdaptiveCoverCard.getGridOptions', () => {
  it('spans the full section width and auto-sizes its height (issue #146)', () => {
    const card = document.createElement('adaptive-cover-card') as GridCardLike;
    card.setConfig({ type: 'custom:adaptive-cover-card', entry_id: ENTRY });
    const opts = card.getGridOptions();
    expect(opts.columns).toBe(12);
    expect(opts.min_columns).toBe(6);
    expect(opts.max_columns).toBe(12);
    expect(opts.rows).toBe('auto');
  });

  it('stays auto-height regardless of the number of visible sections (issue #146)', () => {
    const oneSection = document.createElement('adaptive-cover-card') as GridCardLike;
    oneSection.setConfig({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
      show_sections: ['covers'],
    });
    const allSections = document.createElement('adaptive-cover-card') as GridCardLike;
    allSections.setConfig({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
      show_sections: ['sky', 'elevation', 'decision', 'covers', 'overrides', 'climate'],
    });
    expect(oneSection.getGridOptions().rows).toBe('auto');
    expect(allSections.getGridOptions().rows).toBe('auto');
  });
});

describe('main card show_decision_summary config (issue #173)', () => {
  it('sets showSummary to false on the strip when show_decision_summary: false', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
      show_decision_summary: false,
    });
    interface StripEl extends HTMLElement {
      showSummary?: boolean;
    }
    const strip = el.shadowRoot!.querySelector('acp-decision-strip') as StripEl;
    expect(strip).toBeTruthy();
    expect(strip.showSummary).toBe(false);
  });

  it('keeps showSummary true when show_decision_summary is omitted', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
    });
    interface StripEl extends HTMLElement {
      showSummary?: boolean;
    }
    const strip = el.shadowRoot!.querySelector('acp-decision-strip') as StripEl;
    expect(strip).toBeTruthy();
    expect(strip.showSummary).toBe(true);
  });
});

describe('header layout — long entry title', () => {
  it('renders the header with a title span', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
    });
    const header = el.shadowRoot!.querySelector('.header');
    expect(header).toBeTruthy();
    const title = header!.querySelector('.title');
    expect(title).toBeTruthy();
  });

  it('header does not use align-items: center (which clips wrapped titles)', () => {
    // CSS layout overflow is not catchable by happy-dom, but we can assert that
    // the LitElement.styles CSSResult does not contain the clipping combination.
    const styles = (AdaptiveCoverCard as unknown as { styles: { cssText: string } }).styles
      .cssText;
    expect(styles).toMatch(/\.header\s*\{[^}]*align-items:\s*flex-start/);
  });
});

describe('header Auto pill (Toggle Control switch)', () => {
  interface PillEl extends HTMLElement {
    on?: boolean;
    label?: string;
  }

  it('renders exactly one pill — the Auto pill — when the Toggle Control switch is discovered', async () => {
    const el = await mountWithRegistry({
      type: 'custom:adaptive-cover-card',
      entry_id: ENTRY,
    });
    const pills = el.shadowRoot!.querySelectorAll('.header acp-header-pill');
    expect(pills.length).toBe(1);
    const pill = pills[0] as PillEl;
    expect(pill.label).toBe('Auto');
    expect(pill.on).toBe(true);
  });

  it('omits the pill entirely when the Toggle Control switch is not discovered', async () => {
    const registryNoSwitch = REGISTRY.filter((e) => e.entity_id !== 'switch.toggle_control');
    const el = await mountWithRegistry(
      { type: 'custom:adaptive-cover-card', entry_id: ENTRY },
      registryNoSwitch,
    );
    expect(el.shadowRoot!.querySelector('.header acp-header-pill')).toBeNull();
  });
});
