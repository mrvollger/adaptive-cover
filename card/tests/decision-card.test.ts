// Fixtures updated for the Adaptive Cover integration: entities are matched
// via registry unique_ids of the form `{entry_id}_{suffix}` where the suffix
// contains SPACES ("Cover Position"), platform `adaptive_cover`; the decision
// trace lives on the Cover Position sensor (intent + decision_trace), not a
// dedicated trace sensor.
import { describe, it, expect } from 'vitest';
import '../src/adaptive-cover-decision-card';
// Vite/Vitest raw import: load the card source as text (no Node fs globals, which
// the build's tsconfig does not type). Used by the reuse-guard assertions below.
import decisionCardSource from '../src/adaptive-cover-decision-card.ts?raw';
import type { HomeAssistant } from 'custom-card-helpers';
import type { AdaptiveCoverDecisionCardConfig } from '../src/types';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

const TYPE = 'custom:adaptive-cover-decision-card';
const ENTRY = 'entry_dec';

interface CardLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  setConfig(config: AdaptiveCoverDecisionCardConfig): void;
  // Internal — set directly in tests to bypass the websocket registry fetch.
  _registry?: EntityRegistryEntry[] | null;
}

function makeCard(): CardLike {
  return document.createElement('adaptive-cover-decision-card') as CardLike;
}

const REGISTRY: EntityRegistryEntry[] = [
  {
    entity_id: 'sensor.cover_position',
    unique_id: `${ENTRY}_Cover Position`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
  {
    // Role-less extra entity of the same entry — discovery must skip it.
    entity_id: 'sensor.next_state_change',
    unique_id: `${ENTRY}_Next State Change`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
];

function makeHass(): HomeAssistant {
  return {
    states: {
      'sensor.cover_position': {
        state: '42',
        attributes: {
          intent: 'calculated',
          decision_trace: ['privacy: not configured', 'sun in view: tracking'],
          last_moves: { 'cover.left': '10:12 -> 42% (solar)' },
        },
      },
      'cover.left': {
        state: 'open',
        attributes: { friendly_name: 'Left', current_position: 42 },
      },
    },
    callWS: async () => [],
    connection: {
      subscribeEvents: async () => () => {},
    },
  } as unknown as HomeAssistant;
}

async function mountWithRegistry(config: AdaptiveCoverDecisionCardConfig): Promise<CardLike> {
  const el = makeCard();
  el.hass = makeHass();
  el._registry = REGISTRY;
  el.setConfig(config);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

describe('adaptive-cover-decision-card setConfig', () => {
  it('throws when entry_id is missing', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE } as AdaptiveCoverDecisionCardConfig)).toThrow(
      /entry_id/,
    );
  });

  it('throws when entry_id is an empty string', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE, entry_id: '' })).toThrow(/entry_id/);
  });

  it('accepts a valid config', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE, entry_id: ENTRY })).not.toThrow();
  });

  it('accepts a full config with all options', () => {
    const el = makeCard();
    expect(() =>
      el.setConfig({
        type: TYPE,
        entry_id: ENTRY,
        title: 'Why?',
        compact: true,
        hide_inactive_handlers: true,
        show_decision_summary: false,
      }),
    ).not.toThrow();
  });
});

describe('adaptive-cover-decision-card render states', () => {
  it('shows a loading state and no strip while the registry is null', async () => {
    const el = makeCard();
    el.hass = makeHass();
    el._registry = null;
    el.setConfig({ type: TYPE, entry_id: ENTRY });
    document.body.appendChild(el);
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('acp-decision-strip')).toBeNull();
    expect(el.shadowRoot!.querySelector('.empty')).toBeTruthy();
  });

  it('shows a not-found state and no strip when the entry_id does not match', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: 'no_such_entry' });
    expect(el.shadowRoot!.querySelector('acp-decision-strip')).toBeNull();
    expect(el.shadowRoot!.querySelector('.empty')).toBeTruthy();
  });

  it('renders exactly one acp-decision-strip when the entry matches', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: ENTRY });
    const strips = el.shadowRoot!.querySelectorAll('acp-decision-strip');
    expect(strips.length).toBe(1);
  });

  it('forwards hass and discovered to the strip', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: ENTRY });
    interface StripEl extends HTMLElement {
      hass?: HomeAssistant;
      discovered?: { entry_id: string; entities: Record<string, string> };
    }
    const strip = el.shadowRoot!.querySelector('acp-decision-strip') as StripEl;
    expect(strip.hass).toBeTruthy();
    expect(strip.discovered?.entry_id).toBe(ENTRY);
    expect(strip.discovered?.entities.target_position_sensor).toBe('sensor.cover_position');
  });
});

describe('adaptive-cover-decision-card option attributes', () => {
  it('reflects compact + hide-inactive and drops show-summary when configured', async () => {
    const el = await mountWithRegistry({
      type: TYPE,
      entry_id: ENTRY,
      compact: true,
      hide_inactive_handlers: true,
      show_decision_summary: false,
    });
    const strip = el.shadowRoot!.querySelector('acp-decision-strip')!;
    expect(strip.hasAttribute('compact')).toBe(true);
    expect(strip.hasAttribute('hide-inactive')).toBe(true);
    expect(strip.hasAttribute('show-summary')).toBe(false);
  });

  it('forces hide-inactive on when compact alone is set', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: ENTRY, compact: true });
    const strip = el.shadowRoot!.querySelector('acp-decision-strip')!;
    expect(strip.hasAttribute('compact')).toBe(true);
    expect(strip.hasAttribute('hide-inactive')).toBe(true);
  });

  it('keeps show-summary on by default and hide-inactive off', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: ENTRY });
    const strip = el.shadowRoot!.querySelector('acp-decision-strip')!;
    expect(strip.hasAttribute('show-summary')).toBe(true);
    expect(strip.hasAttribute('hide-inactive')).toBe(false);
    expect(strip.hasAttribute('compact')).toBe(false);
  });
});

describe('adaptive-cover-decision-card title header', () => {
  it('renders a card-header when title is set', async () => {
    const el = await mountWithRegistry({
      type: TYPE,
      entry_id: ENTRY,
      title: 'Why this position?',
    });
    const header = el.shadowRoot!.querySelector('.card-header');
    expect(header).toBeTruthy();
    expect(header!.textContent).toContain('Why this position?');
  });

  it('renders no card-header when title is omitted', async () => {
    const el = await mountWithRegistry({ type: TYPE, entry_id: ENTRY });
    expect(el.shadowRoot!.querySelector('.card-header')).toBeNull();
  });
});

describe('adaptive-cover-decision-card getGridOptions', () => {
  it('spans the full section width and auto-sizes its height', () => {
    interface GridLike extends CardLike {
      getGridOptions(): {
        columns: number;
        rows: number | string;
        min_columns: number;
        max_columns: number;
      };
    }
    const el = makeCard() as GridLike;
    el.setConfig({ type: TYPE, entry_id: ENTRY });
    const opts = el.getGridOptions();
    expect(opts.columns).toBe(12);
    expect(opts.rows).toBe('auto');
    expect(opts.min_columns).toBe(4);
    expect(opts.max_columns).toBe(12);
  });
});

describe('adaptive-cover-decision-card reuse guard', () => {
  const source = decisionCardSource;

  it('imports the shared decision-strip component', () => {
    expect(source).toMatch(/import\s+['"]\.\/components\/decision-strip['"]/);
  });

  it('does not duplicate the strip trace-parsing logic', () => {
    expect(source).not.toMatch(/attrs\.trace/);
    expect(source).not.toMatch(/decision_trace/);
    expect(source).not.toMatch(/buildDecisionSentence/);
    expect(source).not.toMatch(/normalizeHandler/);
  });
});
