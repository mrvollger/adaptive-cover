// Rewritten for the Adaptive Cover integration: all decision context comes
// from the single Cover Position sensor (intent / decision_trace /
// forecast_today / last_moves / move_blocked_by), the header shows a single
// winner badge, the Controls row toggles the Automatic / Climate / Manual
// detection switches, and the Advanced section adds a "Recent moves" list.
// Removed with their features: the solar-calc panel, the custom-position slot
// manager, the mismatch icon, and multi-badge (per-matched-handler) rows.
import { describe, it, expect, vi, afterEach } from 'vitest';
import '../src/components/more-info-dialog';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';

interface DialogLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discovered?: DiscoveredEntities;
  open?: boolean;
  showCompass?: boolean;
  showElevationChart?: boolean;
  badges?: Record<string, boolean>;
}

function badgeKinds(el: DialogLike): string[] {
  return Array.from(el.shadowRoot!.querySelectorAll('.header acp-tile-badge')).map((b) => {
    const span = b.shadowRoot!.querySelector('.badge') as HTMLElement;
    return (
      Array.from(span.classList)
        .filter((c) => c.startsWith('kind-'))
        .map((c) => c.slice('kind-'.length))[0] ?? ''
    );
  });
}

async function mount(props: Partial<DialogLike>): Promise<DialogLike> {
  const el = document.createElement('acp-more-info-dialog') as DialogLike;
  Object.assign(el, props);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

function discovered(extra: Partial<DiscoveredEntities['entities']> = {}): DiscoveredEntities {
  return {
    entry_id: 'entry_xyz',
    entry_title: 'Living room',
    cover_type: 'cover_blind',
    entities: {
      target_position_sensor: 'sensor.cover_position',
      reset_override_button: 'button.reset',
      ...extra,
    },
    managed_covers: ['cover.left'],
  };
}

interface HassOpts {
  /** Engine intent on the Cover Position sensor. */
  intent?: string;
  /** decision_trace prose lines; last line is the winning step. */
  trace?: string[];
  /** Extra attributes merged onto the Cover Position sensor. */
  attrs?: Record<string, unknown>;
  callService?: (...args: unknown[]) => unknown;
}

function hass(overrides: HassOpts = {}): HomeAssistant {
  return {
    states: {
      'sensor.cover_position': {
        state: '42',
        attributes: {
          intent: overrides.intent ?? 'calculated',
          decision_trace: overrides.trace ?? ['sun in view: tracking'],
          last_moves: { 'cover.left': '10:12 -> 42% (solar)' },
          ...(overrides.attrs ?? {}),
        },
      },
      'cover.left': {
        state: 'open',
        attributes: { friendly_name: 'Left blind', current_position: 40 },
      },
    },
    callService: overrides.callService ?? vi.fn(),
  } as unknown as HomeAssistant;
}

describe('acp-more-info-dialog: open/close', () => {
  it('renders no dialog content when open=false', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: false });
    expect(el.shadowRoot!.querySelector('[data-open]')).toBeNull();
  });

  it('reflects open=true via [data-open] attribute on the container', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('[data-open]')).toBeTruthy();
  });

  it('close button dispatches acp-dialog-close', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    const listener = vi.fn();
    el.addEventListener('acp-dialog-close', listener);
    (el.shadowRoot!.querySelector('button.close') as HTMLElement).click();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('acp-more-info-dialog: minute timer (now cursor)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('ticks every minute only while open', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-13T10:00:00.000Z')); // on a boundary → ticks at +60s, +120s
    const el = await mount({ hass: hass(), discovered: discovered(), open: false });

    const spy = vi.spyOn(el as unknown as { requestUpdate: () => void }, 'requestUpdate');
    vi.advanceTimersByTime(180_000);
    expect(spy).not.toHaveBeenCalled(); // closed → no timer

    el.open = true;
    await el.updateComplete;
    spy.mockClear();
    vi.advanceTimersByTime(120_000);
    expect(spy).toHaveBeenCalledTimes(2);

    el.open = false;
    await el.updateComplete;
    spy.mockClear();
    vi.advanceTimersByTime(180_000);
    expect(spy).not.toHaveBeenCalled(); // closed again → timer cleared
  });
});

describe('acp-more-info-dialog: header nav buttons', () => {
  it('omits the device-link button when discovered.device_id is missing', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('button.device-link')).toBeNull();
  });

  it('renders the device-link button when discovered.device_id is present', async () => {
    const d = { ...discovered(), device_id: 'dev_123' };
    const el = await mount({ hass: hass(), discovered: d, open: true });
    expect(el.shadowRoot!.querySelector('button.device-link')).toBeTruthy();
  });

  it('clicking device-link navigates to the device page and closes the dialog', async () => {
    const d = { ...discovered(), device_id: 'dev_123' };
    const el = await mount({ hass: hass(), discovered: d, open: true });
    const pushSpy = vi.spyOn(history, 'pushState');
    const eventSpy = vi.fn();
    window.addEventListener('location-changed', eventSpy);
    const closeSpy = vi.fn();
    el.addEventListener('acp-dialog-close', closeSpy);

    (el.shadowRoot!.querySelector('button.device-link') as HTMLElement).click();

    expect(pushSpy).toHaveBeenCalledWith(null, '', '/config/devices/device/dev_123');
    expect(eventSpy).toHaveBeenCalledTimes(1);
    expect(closeSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('location-changed', eventSpy);
    pushSpy.mockRestore();
  });

  it('always renders the options-link button regardless of device_id', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('button.options-link')).toBeTruthy();
  });

  it('clicking options-link navigates to the integration page and closes the dialog', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    const pushSpy = vi.spyOn(history, 'pushState');
    const eventSpy = vi.fn();
    window.addEventListener('location-changed', eventSpy);
    const closeSpy = vi.fn();
    el.addEventListener('acp-dialog-close', closeSpy);

    (el.shadowRoot!.querySelector('button.options-link') as HTMLElement).click();

    expect(pushSpy).toHaveBeenCalledWith(
      null,
      '',
      '/config/integrations/integration/adaptive_cover',
    );
    expect(eventSpy).toHaveBeenCalledTimes(1);
    expect(closeSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('location-changed', eventSpy);
    pushSpy.mockRestore();
  });
});

describe('acp-more-info-dialog: header content', () => {
  it('renders the discovered title in the header', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('.header .title')?.textContent?.trim()).toBe('Living room');
  });

  it('renders a single winner badge derived from the intent', async () => {
    const el = await mount({ hass: hass({ intent: 'calculated' }), discovered: discovered(), open: true });
    expect(badgeKinds(el)).toEqual(['solar']);
  });

  it('renders the plain-English decision summary line', async () => {
    const el = await mount({
      hass: hass({
        intent: 'calculated',
        trace: ['privacy: not configured', 'sun in view: tracking'],
      }),
      discovered: discovered(),
      open: true,
    });
    const txt = el.shadowRoot!.querySelector('.summary')?.textContent?.replace(/\s+/g, ' ').trim();
    expect(txt).toBe('Sun tracking 42% — sun in view: tracking');
  });

  it('shows the target position (sensor state) in the position block', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('.position-value')?.textContent?.trim()).toBe('42%');
  });
});

describe('acp-more-info-dialog: winner badge kinds + opt-in', () => {
  it('shows the solar badge when the winning intent is calculated', async () => {
    const el = await mount({
      hass: hass({ intent: 'calculated' }),
      discovered: discovered(),
      open: true,
    });
    expect(badgeKinds(el)).toContain('solar');
  });

  it('drops the solar badge when badges.solar is false even though it is active', async () => {
    const el = await mount({
      hass: hass({ intent: 'calculated' }),
      discovered: discovered(),
      open: true,
      badges: { solar: false },
    });
    expect(badgeKinds(el)).not.toContain('solar');
  });

  it('maps the privacy intent to the privacy badge and respects its opt-out', async () => {
    const on = await mount({
      hass: hass({ intent: 'privacy' }),
      discovered: discovered(),
      open: true,
    });
    expect(badgeKinds(on)).toEqual(['privacy']);

    const off = await mount({
      hass: hass({ intent: 'privacy' }),
      discovered: discovered(),
      open: true,
      badges: { privacy: false },
    });
    expect(badgeKinds(off)).toEqual([]);
  });

  it('maps climate_* intents to the climate badge', async () => {
    const el = await mount({
      hass: hass({ intent: 'climate_block_heat' }),
      discovered: discovered(),
      open: true,
    });
    expect(badgeKinds(el)).toEqual(['climate']);
  });

  it('renders a manual badge when the manual-override binary is on', async () => {
    const d = discovered({ manual_override_binary: 'binary_sensor.manual_override' });
    const h = hass({ intent: 'calculated' });
    (h.states as Record<string, { state: string; attributes: Record<string, unknown> }>)[
      'binary_sensor.manual_override'
    ] = { state: 'on', attributes: {} };
    const el = await mount({ hass: h, discovered: d, open: true });
    expect(badgeKinds(el)).toEqual(['manual']);
  });

  it('renders a single Off badge when the Toggle Control switch is off — never filtered', async () => {
    const d = discovered({ automatic_control_switch: 'switch.automatic' });
    const h = hass({ intent: 'calculated' });
    (h.states as Record<string, { state: string; attributes: Record<string, unknown> }>)[
      'switch.automatic'
    ] = { state: 'off', attributes: {} };
    const el = await mount({
      hass: h,
      discovered: d,
      open: true,
      // `off` is a state-fallback and must survive any per-kind opt-out.
      badges: { solar: false, auto: false },
    });
    expect(badgeKinds(el)).toEqual(['off']);
    const badge = el.shadowRoot!.querySelector('.header acp-tile-badge')!;
    expect(badge.shadowRoot!.textContent!.replace(/\s+/g, ' ').trim()).toBe('Off');
  });

  it('falls back to the auto badge for unknown intents and hides it via badges.auto=false', async () => {
    const on = await mount({
      hass: hass({ intent: 'mystery' }),
      discovered: discovered(),
      open: true,
    });
    expect(badgeKinds(on)).toEqual(['auto']);

    const off = await mount({
      hass: hass({ intent: 'mystery' }),
      discovered: discovered(),
      open: true,
      badges: { auto: false },
    });
    expect(badgeKinds(off)).toEqual([]);
  });
});

describe('acp-more-info-dialog: forecast strip', () => {
  const forecastToday = [
    { time: '2026-06-01T06:00:00', position: 0, intent: 'default' },
    { time: '2026-06-01T08:00:00', position: 50, intent: 'calculated' },
  ];

  it('renders the strip when forecast_today has change-points', async () => {
    const el = await mount({
      hass: hass({ attrs: { forecast_today: forecastToday } }),
      discovered: discovered(),
      open: true,
    });
    expect(el.shadowRoot!.querySelector('acp-forecast-strip')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('.forecast-label')?.textContent).toContain(
      "Today's forecast",
    );
  });

  it('hides the strip when forecast_today is absent', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('acp-forecast-strip')).toBeNull();
  });

  it('hides the strip when forecast_today is empty', async () => {
    const el = await mount({
      hass: hass({ attrs: { forecast_today: [] } }),
      discovered: discovered(),
      open: true,
    });
    expect(el.shadowRoot!.querySelector('acp-forecast-strip')).toBeNull();
  });
});

describe('acp-more-info-dialog: sky compass', () => {
  it('renders the compass in the advanced section by default when advanced is open', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('.advanced acp-sky-compass')).toBeTruthy();
  });

  it('hides the compass when showCompass=false', async () => {
    const el = await mount({
      hass: hass(),
      discovered: discovered(),
      open: true,
      showCompass: false,
    });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('.advanced acp-sky-compass')).toBeNull();
  });

  it('does not render the compass while advanced is collapsed', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('acp-sky-compass')).toBeNull();
  });
});

describe('acp-more-info-dialog: elevation chart', () => {
  it('renders the elevation chart in the advanced section by default when advanced is open', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    const chart = el.shadowRoot!.querySelector('.advanced acp-elevation-chart') as
      | (HTMLElement & { discoveredList?: unknown[]; updateComplete?: Promise<boolean> })
      | null;
    expect(chart).toBeTruthy();
    // Guard the prop wiring: the chart takes discoveredList; a stale binding
    // would leave it empty → renders nothing.
    expect(chart!.discoveredList?.length).toBe(1);
    await chart!.updateComplete;
    expect(chart!.shadowRoot!.querySelector('.wrap, .placeholder')).toBeTruthy();
  });

  it('hides the elevation chart when showElevationChart=false', async () => {
    const el = await mount({
      hass: hass(),
      discovered: discovered(),
      open: true,
      showElevationChart: false,
    });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('.advanced acp-elevation-chart')).toBeNull();
  });

  it('does not render the elevation chart while advanced is collapsed', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('acp-elevation-chart')).toBeNull();
  });
});

describe('acp-more-info-dialog: Recent moves', () => {
  it('renders last_moves rows in the advanced section', async () => {
    const el = await mount({
      hass: hass({ attrs: { last_moves: { 'cover.left': '10:12 -> 42% (solar)' } } }),
      discovered: discovered(),
      open: true,
    });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    const section = el.shadowRoot!.querySelector('.moves-section')!;
    expect(section).toBeTruthy();
    expect(section.querySelector('.moves-label')?.textContent).toContain('Recent moves');
    const row = section.querySelector('.move-row')!;
    expect(row.querySelector('.move-name')?.textContent).toContain('Left blind');
    expect(row.querySelector('.move-line')?.textContent).toContain('10:12 -> 42% (solar)');
  });

  it('renders blocked rows with the localized gate message', async () => {
    const el = await mount({
      hass: hass({
        attrs: {
          last_moves: {},
          move_blocked_by: { 'cover.left': 'position_delta' },
        },
      }),
      discovered: discovered(),
      open: true,
    });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    const blocked = el.shadowRoot!.querySelector('.move-row.blocked')!;
    expect(blocked).toBeTruthy();
    expect(blocked.querySelector('.move-line')?.textContent?.trim()).toBe(
      'move blocked by position_delta',
    );
  });

  it('hides the section when there are no moves and no blocked gates', async () => {
    const el = await mount({
      hass: hass({ attrs: { last_moves: {} } }),
      discovered: discovered(),
      open: true,
    });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('.moves-section')).toBeNull();
  });
});

describe('acp-more-info-dialog: removed panels stay removed', () => {
  it('renders no solar-calc panel and no slot manager in the advanced section', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    (el.shadowRoot!.querySelector('.advanced-toggle') as HTMLElement).click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('acp-solar-calc')).toBeNull();
    expect(el.shadowRoot!.querySelector('.slots-section')).toBeNull();
    expect(el.shadowRoot!.querySelector('acp-climate-panel')).toBeNull();
  });
});

describe('acp-more-info-dialog: Resume Auto', () => {
  function manualOnHass(callService?: (...args: unknown[]) => unknown): HomeAssistant {
    const h = hass({ intent: 'calculated', callService });
    (h.states as Record<string, { state: string; attributes: Record<string, unknown> }>)[
      'binary_sensor.manual_override'
    ] = { state: 'on', attributes: {} };
    return h;
  }
  const manualDiscovered = (): DiscoveredEntities =>
    discovered({ manual_override_binary: 'binary_sensor.manual_override' });

  it('Resume button calls button.press on reset_override_button', async () => {
    const callService = vi.fn();
    const el = await mount({
      hass: manualOnHass(callService),
      discovered: manualDiscovered(),
      open: true,
    });
    (el.shadowRoot!.querySelector('button.resume') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('button', 'press', { entity_id: 'button.reset' });
  });

  it('Resume button is hidden when no reset_override_button discovered', async () => {
    const d = manualDiscovered();
    delete d.entities.reset_override_button;
    const el = await mount({ hass: manualOnHass(), discovered: d, open: true });
    expect(el.shadowRoot!.querySelector('button.resume')).toBeNull();
  });

  it('Resume button is hidden when no manual override is active', async () => {
    const el = await mount({
      hass: hass({ intent: 'calculated' }),
      discovered: discovered(),
      open: true,
    });
    expect(el.shadowRoot!.querySelector('button.resume')).toBeNull();
  });

  it('Resume button is shown when manual override is active', async () => {
    const el = await mount({ hass: manualOnHass(), discovered: manualDiscovered(), open: true });
    expect(el.shadowRoot!.querySelector('button.resume')).toBeTruthy();
  });
});

describe('acp-more-info-dialog: Controls row', () => {
  type SwitchStates = Partial<{
    automatic: 'on' | 'off';
    climate: 'on' | 'off';
    manual: 'on' | 'off';
  }>;
  function withControls(states: SwitchStates = {}): {
    d: DiscoveredEntities;
    h: HomeAssistant;
    callService: ReturnType<typeof vi.fn>;
  } {
    const d = discovered({
      automatic_control_switch: 'switch.automatic',
      climate_mode_switch: 'switch.climate',
      manual_toggle_switch: 'switch.manual',
    });
    const callService = vi.fn();
    const h = hass({ callService });
    const s = h.states as Record<string, { state: string; attributes: Record<string, unknown> }>;
    s['switch.automatic'] = { state: states.automatic ?? 'on', attributes: {} };
    s['switch.climate'] = { state: states.climate ?? 'on', attributes: {} };
    s['switch.manual'] = { state: states.manual ?? 'on', attributes: {} };
    return { d, h, callService };
  }

  it('renders three chips when all three switches are discovered', async () => {
    const { d, h } = withControls();
    const el = await mount({ hass: h, discovered: d, open: true });
    const chips = el.shadowRoot!.querySelectorAll('.controls-block .ctrl-toggle');
    expect(chips.length).toBe(3);
    const labels = Array.from(chips).map(
      (c) => c.querySelector('.ctrl-label')?.textContent?.trim() ?? '',
    );
    expect(labels).toEqual(['Automatic', 'Climate', 'Manual detection']);
  });

  it('chip state reflects each switch (on/off)', async () => {
    const { d, h } = withControls({ automatic: 'off' });
    const el = await mount({ hass: h, discovered: d, open: true });
    const chips = el.shadowRoot!.querySelectorAll('.controls-block .ctrl-toggle');
    expect(chips[0].classList.contains('off')).toBe(true);
    expect(chips[0].getAttribute('aria-pressed')).toBe('false');
    expect(chips[1].classList.contains('on')).toBe(true);
    expect(chips[1].getAttribute('aria-pressed')).toBe('true');
  });

  it('clicking an on chip calls switch.turn_off with that entity_id', async () => {
    const { d, h, callService } = withControls();
    const el = await mount({ hass: h, discovered: d, open: true });
    const chip = el.shadowRoot!.querySelectorAll('.controls-block .ctrl-toggle')[0] as HTMLElement;
    chip.click();
    expect(callService).toHaveBeenCalledWith('switch', 'turn_off', {
      entity_id: 'switch.automatic',
    });
  });

  it('clicking an off chip calls switch.turn_on with that entity_id', async () => {
    const { d, h, callService } = withControls({ manual: 'off' });
    const el = await mount({ hass: h, discovered: d, open: true });
    const chip = el.shadowRoot!.querySelectorAll('.controls-block .ctrl-toggle')[2] as HTMLElement;
    chip.click();
    expect(callService).toHaveBeenCalledWith('switch', 'turn_on', { entity_id: 'switch.manual' });
  });

  it('renders only the discovered switches (omits chips for missing entities)', async () => {
    const d = discovered({ automatic_control_switch: 'switch.automatic' });
    const h = hass();
    (h.states as Record<string, { state: string; attributes: Record<string, unknown> }>)[
      'switch.automatic'
    ] = { state: 'on', attributes: {} };
    const el = await mount({ hass: h, discovered: d, open: true });
    const chips = el.shadowRoot!.querySelectorAll('.controls-block .ctrl-toggle');
    expect(chips.length).toBe(1);
    expect(chips[0].querySelector('.ctrl-label')?.textContent?.trim()).toBe('Automatic');
  });

  it('hides the Controls block entirely when none of the three switches are discovered', async () => {
    const el = await mount({ hass: hass(), discovered: discovered(), open: true });
    expect(el.shadowRoot!.querySelector('.controls-block')).toBeNull();
  });
});
