// Rewritten for the Adaptive Cover integration's single rich Cover Position
// sensor (state = target %, attributes = intent / decision_trace / sun / …).
// Removed with their features: the off-schedule banner tests (no
// in_time_window attribute), the handler-grid trace rows, and the climate
// panel's temperature/threshold/inactive_reason surface.
import { describe, it, expect, vi } from 'vitest';
import '../src/components/decision-strip';
import '../src/components/cover-bar';
import '../src/components/overrides-panel';
import '../src/components/header-pill';
import '../src/components/climate-panel';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';

interface LitLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discovered?: DiscoveredEntities;
  compact?: boolean;
}

async function mount<T extends LitLike>(tag: string): Promise<T> {
  const el = document.createElement(tag) as T;
  document.body.appendChild(el);
  return el;
}

async function flush(el: LitLike): Promise<void> {
  await el.updateComplete;
}

const baseDiscovered: DiscoveredEntities = {
  entry_id: 'entry1',
  entry_title: 'Test',
  cover_type: 'cover_blind',
  entities: {},
  managed_covers: [],
};

describe('acp-decision-strip', () => {
  function traceHass(
    lines: string[],
    intent = 'calculated',
    state = '42',
  ): HomeAssistant {
    return {
      states: {
        'sensor.cover_position': {
          state,
          attributes: { intent, decision_trace: lines },
        },
      },
    } as unknown as HomeAssistant;
  }

  const traceDiscovered: DiscoveredEntities = {
    ...baseDiscovered,
    entities: { target_position_sensor: 'sensor.cover_position' },
  };

  it('renders one row per decision_trace line with the final line highlighted', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = traceHass([
      'privacy: not configured',
      'climate: mode off',
      'sun in view: tracking',
    ]);
    el.discovered = traceDiscovered;
    await flush(el);
    const rows = el.shadowRoot!.querySelectorAll('.row');
    expect(rows.length).toBe(3);
    const winners = el.shadowRoot!.querySelectorAll('.row.winner');
    expect(winners.length).toBe(1);
    // The winning row is the LAST trace line.
    expect(winners[0].textContent).toContain('sun in view: tracking');
  });

  it('labels the winner from the intent attribute via the handler i18n table', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = traceHass(['sun in view: tracking'], 'calculated');
    el.discovered = traceDiscovered;
    await flush(el);
    expect(el.shadowRoot!.querySelector('.head .winner')!.textContent).toContain('Sun tracking');
  });

  it('falls back to the raw intent string for unknown intents', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = traceHass(['???'], 'mystery_intent');
    el.discovered = traceDiscovered;
    await flush(el);
    expect(el.shadowRoot!.querySelector('.head .winner')!.textContent).toContain('mystery_intent');
  });

  it('renders the plain-English summary with intent label, target %, and final reason', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = traceHass(['privacy: not configured', 'sun in view: tracking'], 'calculated', '42');
    el.discovered = traceDiscovered;
    await flush(el);
    const summary = el.shadowRoot!.querySelector('.summary');
    expect(summary?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'Sun tracking 42% — sun in view: tracking',
    );
  });

  it('hides the summary when show-summary is off', async () => {
    interface StripLike extends LitLike {
      showSummary?: boolean;
    }
    const el = await mount<StripLike>('acp-decision-strip');
    el.hass = traceHass(['sun in view: tracking']);
    el.discovered = traceDiscovered;
    el.showSummary = false;
    await flush(el);
    expect(el.shadowRoot!.querySelector('.summary')).toBeNull();
  });

  it('shows only the final (winning) line when hide-inactive is set', async () => {
    interface StripLike extends LitLike {
      hideInactive?: boolean;
    }
    const el = await mount<StripLike>('acp-decision-strip');
    el.hass = traceHass(['a', 'b', 'the winner line']);
    el.discovered = traceDiscovered;
    el.hideInactive = true;
    await flush(el);
    const rows = el.shadowRoot!.querySelectorAll('.row');
    expect(rows.length).toBe(1);
    expect(rows[0].classList.contains('winner')).toBe(true);
    expect(rows[0].textContent).toContain('the winner line');
  });

  it('shows a placeholder when the trace is missing', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: {} };
    await flush(el);
    expect(el.shadowRoot!.querySelector('.placeholder')).toBeTruthy();
  });

  it('shows a placeholder when decision_trace is an empty list', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.hass = traceHass([]);
    el.discovered = traceDiscovered;
    await flush(el);
    expect(el.shadowRoot!.querySelector('.placeholder')).toBeTruthy();
  });
});

describe('acp-cover-bar', () => {
  it('renders one row per managed cover, positions read from the cover entities', async () => {
    const el = await mount<LitLike>('acp-cover-bar');
    el.hass = {
      states: {
        'sensor.cover_position': { state: '42', attributes: {} },
        'cover.left': { state: 'open', attributes: { current_position: 40 } },
        'cover.right': { state: 'open', attributes: { current_position: 38 } },
        'cover.middle': { state: 'open', attributes: { current_position: 45 } },
      },
    } as unknown as HomeAssistant;
    el.discovered = {
      ...baseDiscovered,
      entities: { target_position_sensor: 'sensor.cover_position' },
      managed_covers: ['cover.left', 'cover.middle', 'cover.right'],
    };
    await flush(el);
    const covers = el.shadowRoot!.querySelectorAll('.cover');
    expect(covers.length).toBe(3);
  });

  it('renders the placeholder when no managed covers are known yet', async () => {
    const el = await mount<LitLike>('acp-cover-bar');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: {}, managed_covers: [] };
    await flush(el);
    expect(el.shadowRoot!.querySelector('.placeholder')).toBeTruthy();
  });
});

describe('acp-overrides-panel', () => {
  it('renders a Manual tile only (no Force/Motion tiles)', async () => {
    const el = await mount<LitLike>('acp-overrides-panel');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: {} };
    await flush(el);
    const labels = Array.from(el.shadowRoot!.querySelectorAll('.tile-label')).map((n) =>
      n.textContent!.trim(),
    );
    expect(labels).toContain('Manual');
    expect(labels).not.toContain('Force');
    expect(labels).not.toContain('Motion');
  });

  it('shows the manual tile active with the manual_controlled count', async () => {
    const el = await mount<LitLike>('acp-overrides-panel');
    el.hass = {
      states: {
        'binary_sensor.manual': {
          state: 'on',
          attributes: { manual_controlled: ['cover.a', 'cover.b'] },
        },
      },
    } as unknown as HomeAssistant;
    el.discovered = {
      ...baseDiscovered,
      entities: { manual_override_binary: 'binary_sensor.manual' },
    };
    await flush(el);
    const tile = el.shadowRoot!.querySelector('.tile')!;
    expect(tile.classList.contains('active')).toBe(true);
    expect(tile.querySelector('.tile-sub')?.textContent).toContain('2 active');
  });

  it('hides the reset button when no reset_override_button is discovered', async () => {
    const el = await mount<LitLike>('acp-overrides-panel');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: {} };
    await flush(el);
    expect(el.shadowRoot!.querySelector('.tile.action')).toBeNull();
  });

  it('renders the reset button when the role is populated', async () => {
    const el = await mount<LitLike>('acp-overrides-panel');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = {
      ...baseDiscovered,
      entities: { reset_override_button: 'button.reset' },
    };
    await flush(el);
    expect(el.shadowRoot!.querySelector('.tile.action')).toBeTruthy();
  });

  it('reset tile is interactive by default (no aria-disabled, no readonly class)', async () => {
    const el = await mount<LitLike>('acp-overrides-panel');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: { reset_override_button: 'button.reset' } };
    await flush(el);
    const btn = el.shadowRoot!.querySelector('.tile.action')!;
    expect(btn.hasAttribute('aria-disabled')).toBe(false);
    expect(btn.classList.contains('readonly')).toBe(false);
  });

  it('reset tile gets aria-disabled and .readonly when resetEnabled=false', async () => {
    interface OverridesLike extends LitLike {
      resetEnabled?: boolean;
    }
    const el = await mount<OverridesLike>('acp-overrides-panel');
    el.hass = { states: {} } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: { reset_override_button: 'button.reset' } };
    el.resetEnabled = false;
    await flush(el);
    const btn = el.shadowRoot!.querySelector('.tile.action')!;
    expect(btn.getAttribute('aria-disabled')).toBe('true');
    expect(btn.getAttribute('tabindex')).toBe('-1');
    expect(btn.classList.contains('readonly')).toBe(true);
  });

  it('does not call hass.callService when resetEnabled=false and tile is clicked', async () => {
    interface OverridesLike extends LitLike {
      resetEnabled?: boolean;
    }
    const callService = vi.fn();
    const el = await mount<OverridesLike>('acp-overrides-panel');
    el.hass = { states: {}, callService } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: { reset_override_button: 'button.reset' } };
    el.resetEnabled = false;
    await flush(el);
    (el.shadowRoot!.querySelector('.tile.action') as HTMLElement).click();
    expect(callService).not.toHaveBeenCalled();
  });

  it('calls hass.callService when resetEnabled=true, tile is clicked and confirmed', async () => {
    interface OverridesLike extends LitLike {
      resetEnabled?: boolean;
    }
    window.confirm = vi.fn(() => true);
    const callService = vi.fn();
    const el = await mount<OverridesLike>('acp-overrides-panel');
    el.hass = { states: {}, callService } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: { reset_override_button: 'button.reset' } };
    el.resetEnabled = true;
    await flush(el);
    (el.shadowRoot!.querySelector('.tile.action') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('button', 'press', { entity_id: 'button.reset' });
  });

  it('does not call hass.callService when the resume confirm is declined', async () => {
    interface OverridesLike extends LitLike {
      resetEnabled?: boolean;
    }
    window.confirm = vi.fn(() => false);
    const callService = vi.fn();
    const el = await mount<OverridesLike>('acp-overrides-panel');
    el.hass = { states: {}, callService } as unknown as HomeAssistant;
    el.discovered = { ...baseDiscovered, entities: { reset_override_button: 'button.reset' } };
    el.resetEnabled = true;
    await flush(el);
    (el.shadowRoot!.querySelector('.tile.action') as HTMLElement).click();
    expect(callService).not.toHaveBeenCalled();
  });
});

describe('acp-header-pill', () => {
  interface PillLike extends HTMLElement {
    updateComplete: Promise<boolean>;
    on?: boolean;
    readonly?: boolean;
    label?: string;
  }

  it('renders with aria-disabled and tabindex=-1 when readonly=true', async () => {
    const el = document.createElement('acp-header-pill') as PillLike;
    el.on = false;
    el.readonly = true;
    el.label = 'ON';
    document.body.appendChild(el);
    await el.updateComplete;
    const btn = el.shadowRoot!.querySelector('button')!;
    expect(btn.getAttribute('aria-disabled')).toBe('true');
    expect(btn.getAttribute('tabindex')).toBe('-1');
  });

  it('adds .readonly CSS class when readonly=true', async () => {
    const el = document.createElement('acp-header-pill') as PillLike;
    el.on = true;
    el.readonly = true;
    el.label = 'ON';
    document.body.appendChild(el);
    await el.updateComplete;
    const btn = el.shadowRoot!.querySelector('button')!;
    expect(btn.classList.contains('readonly')).toBe(true);
  });

  it('does not emit pill-click when readonly=true and clicked', async () => {
    const el = document.createElement('acp-header-pill') as PillLike;
    el.on = true;
    el.readonly = true;
    el.label = 'ON';
    document.body.appendChild(el);
    await el.updateComplete;
    const listener = vi.fn();
    el.addEventListener('pill-click', listener);
    el.shadowRoot!.querySelector('button')!.click();
    expect(listener).not.toHaveBeenCalled();
  });

  it('emits pill-click when readonly=false and clicked', async () => {
    const el = document.createElement('acp-header-pill') as PillLike;
    el.on = true;
    el.readonly = false;
    el.label = 'ON';
    document.body.appendChild(el);
    await el.updateComplete;
    const listener = vi.fn();
    el.addEventListener('pill-click', listener);
    el.shadowRoot!.querySelector('button')!.click();
    expect(listener).toHaveBeenCalledOnce();
  });

  it('has no aria-disabled and no .readonly class when readonly=false', async () => {
    const el = document.createElement('acp-header-pill') as PillLike;
    el.on = false;
    el.readonly = false;
    el.label = 'OFF';
    document.body.appendChild(el);
    await el.updateComplete;
    const btn = el.shadowRoot!.querySelector('button')!;
    expect(btn.hasAttribute('aria-disabled')).toBe(false);
    expect(btn.classList.contains('readonly')).toBe(false);
  });
});

describe('compact attribute propagation', () => {
  it('reflects compact to the host attribute on each section', async () => {
    const el = await mount<LitLike>('acp-decision-strip');
    el.compact = true;
    await flush(el);
    expect(el.hasAttribute('compact')).toBe(true);
    el.compact = false;
    await flush(el);
    expect(el.hasAttribute('compact')).toBe(false);
  });
});

describe('acp-climate-panel', () => {
  function makeHass(sensorState?: string, switchState?: string): HomeAssistant {
    const states: Record<string, unknown> = {};
    if (sensorState !== undefined) {
      states['sensor.control_method'] = {
        entity_id: 'sensor.control_method',
        state: sensorState,
        attributes: { friendly_name: 'Control Method' },
      };
    }
    if (switchState !== undefined) {
      states['switch.climate_mode'] = {
        entity_id: 'switch.climate_mode',
        state: switchState,
        attributes: { friendly_name: 'Climate Mode' },
      };
    }
    return { states } as unknown as HomeAssistant;
  }

  function makeDiscovered(opts: { sensor?: boolean; withSwitch?: boolean }): DiscoveredEntities {
    return {
      ...baseDiscovered,
      entities: {
        ...(opts.sensor !== false ? { control_status_sensor: 'sensor.control_method' } : {}),
        ...(opts.withSwitch ? { climate_mode_switch: 'switch.climate_mode' } : {}),
      },
    };
  }

  it('hides entirely when the Climate Mode switch role is missing', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass('summer');
    el.discovered = makeDiscovered({ withSwitch: false });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.wrap')).toBeNull();
  });

  it('hides entirely when the Control Method sensor role is missing', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass(undefined, 'on');
    el.discovered = makeDiscovered({ sensor: false, withSwitch: true });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.wrap')).toBeNull();
  });

  it('hides entirely when the Control Method sensor is unavailable', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass('unavailable', 'on');
    el.discovered = makeDiscovered({ withSwitch: true });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.wrap')).toBeNull();
  });

  it('shows "Climate mode off" when the switch is off', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass('summer', 'off');
    el.discovered = makeDiscovered({ withSwitch: true });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.strategy-name')?.textContent?.trim()).toBe(
      'Climate mode off',
    );
    expect(el.shadowRoot!.querySelector('.strategy')?.classList.contains('standby')).toBe(true);
  });

  it('shows "Standby" when the switch is on but the sensor state is unknown', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass('unknown', 'on');
    el.discovered = makeDiscovered({ withSwitch: true });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.strategy-name')?.textContent?.trim()).toBe('Standby');
  });

  it.each(['winter', 'summer', 'intermediate'])(
    'renders the %s strategy from the Control Method sensor state',
    async (strategy) => {
      const el = await mount<LitLike>('acp-climate-panel');
      el.hass = makeHass(strategy, 'on');
      el.discovered = makeDiscovered({ withSwitch: true });
      await flush(el);
      expect(el.shadowRoot!.querySelector('.wrap')).toBeTruthy();
      expect(el.shadowRoot!.querySelector('.strategy-name')?.textContent?.trim()).toBe(strategy);
      // Active strategy is not the standby style.
      expect(el.shadowRoot!.querySelector('.strategy')?.classList.contains('standby')).toBe(false);
    },
  );

  it('renders no temperature tiles (removed with the Pro climate surface)', async () => {
    const el = await mount<LitLike>('acp-climate-panel');
    el.hass = makeHass('summer', 'on');
    el.discovered = makeDiscovered({ withSwitch: true });
    await flush(el);
    expect(el.shadowRoot!.querySelector('.temps')).toBeNull();
    expect(el.shadowRoot!.querySelector('.temp')).toBeNull();
  });
});
