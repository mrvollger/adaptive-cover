/**
 * Tests for the decision strip against the Adaptive Cover integration's data
 * contract: the Cover Position sensor carries `decision_trace` (a list of
 * prose lines) and `intent` (the winning engine intent). Each line renders as
 * one row; the last line is the winner.
 *
 * Replaces the Pro-era decision-strip-filter / -held-position / -throttle
 * suites — the per-handler grid, handler filtering, held-position cell, and
 * throttle-countdown banner no longer exist in this integration.
 */
import { describe, it, expect } from 'vitest';
import '../src/components/decision-strip';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';

interface StripLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discovered?: DiscoveredEntities;
  hideInactive?: boolean;
  showSummary?: boolean;
}

const discovered: DiscoveredEntities = {
  entry_id: 'entry1',
  entry_title: 'Test',
  cover_type: 'cover_blind',
  entities: { target_position_sensor: 'sensor.x_cover_position' },
  managed_covers: [],
};

function makeHass(opts: {
  state?: string;
  intent?: string;
  trace?: string[];
}): HomeAssistant {
  return {
    states: {
      'sensor.x_cover_position': {
        state: opts.state ?? '63',
        attributes: {
          ...(opts.intent !== undefined ? { intent: opts.intent } : {}),
          ...(opts.trace !== undefined ? { decision_trace: opts.trace } : {}),
        },
      },
    },
  } as unknown as HomeAssistant;
}

async function mount(
  hass: HomeAssistant,
  setup?: (el: StripLike) => void,
): Promise<StripLike> {
  const el = document.createElement('acp-decision-strip') as StripLike;
  el.hass = hass;
  el.discovered = discovered;
  setup?.(el);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

const TRACE = ['manual override inactive', 'climate mode off', 'sun in view: tracking'];

describe('acp-decision-strip', () => {
  it('renders one row per decision_trace line, in order', async () => {
    const el = await mount(makeHass({ intent: 'calculated', trace: TRACE }));
    const rows = el.shadowRoot!.querySelectorAll('.rows .row');
    expect(rows.length).toBe(3);
    Array.from(rows).forEach((row, i) => {
      expect(row.querySelector('.idx')!.textContent!.trim()).toBe(String(i + 1));
      expect(row.querySelector('.reason-inline')!.textContent).toContain(TRACE[i]);
    });
  });

  it('marks only the last row as the winner, with a ✓ badge', async () => {
    const el = await mount(makeHass({ intent: 'calculated', trace: TRACE }));
    const rows = Array.from(el.shadowRoot!.querySelectorAll('.rows .row'));
    const winners = rows.filter((r) => r.classList.contains('winner'));
    expect(winners.length).toBe(1);
    expect(winners[0]).toBe(rows[rows.length - 1]);
    expect(winners[0].querySelector('.badge')!.textContent).toContain('✓');
    // Non-winner rows have no ✓ badge.
    for (const row of rows.slice(0, -1)) {
      expect(row.querySelector('.badge')).toBeNull();
    }
  });

  it('shows only the last (winning) row when hide-inactive is set', async () => {
    const el = await mount(makeHass({ intent: 'calculated', trace: TRACE }), (e) => {
      e.hideInactive = true;
    });
    const rows = el.shadowRoot!.querySelectorAll('.rows .row');
    expect(rows.length).toBe(1);
    expect(rows[0].classList.contains('winner')).toBe(true);
    expect(rows[0].querySelector('.reason-inline')!.textContent).toContain(TRACE[2]);
  });

  it('renders the placeholder when there is no trace', async () => {
    const empty = await mount(makeHass({ intent: 'default', trace: [] }));
    expect(empty.shadowRoot!.querySelector('.placeholder')).toBeTruthy();
    expect(empty.shadowRoot!.querySelector('.rows')).toBeNull();

    const missing = await mount(makeHass({ intent: 'default' }));
    expect(missing.shadowRoot!.querySelector('.placeholder')).toBeTruthy();
  });

  it('labels the winner in the head using the intent i18n label', async () => {
    const el = await mount(makeHass({ intent: 'calculated', trace: TRACE }));
    const winner = el.shadowRoot!.querySelector('.head .winner')!;
    expect(winner.textContent).toContain('Winner: Sun tracking');
  });

  it('falls back to the raw intent string for an unknown winner', async () => {
    const el = await mount(makeHass({ intent: 'mystery_intent', trace: TRACE }));
    const winner = el.shadowRoot!.querySelector('.head .winner')!;
    expect(winner.textContent).toContain('mystery_intent');
  });

  it('renders the summary sentence with the sensor state as the position', async () => {
    const el = await mount(makeHass({ state: '63', intent: 'calculated', trace: TRACE }));
    const summary = el.shadowRoot!.querySelector('.summary')!;
    expect(summary).toBeTruthy();
    expect(summary.textContent).toContain('Sun tracking 63% — sun in view: tracking');
  });

  it('omits the summary when show-summary is off', async () => {
    const el = await mount(makeHass({ intent: 'calculated', trace: TRACE }), (e) => {
      e.showSummary = false;
    });
    expect(el.shadowRoot!.querySelector('.summary')).toBeNull();
  });
});
