import { describe, it, expect, vi } from 'vitest';
import { AdaptiveCoverTileCard } from '../src/adaptive-cover-tile-card';
import type { HomeAssistant } from 'custom-card-helpers';
import type { AdaptiveCoverTileCardConfig } from '../src/types';
import type { EntityRegistryEntry } from '../src/lib/entity-registry';

// NOTE (adaptive_cover port): the Pro-only features these tests used to cover
// were removed with the integration swap — tilt bar + adaptive_cover.set_tilt,
// motion indicator/status, floor chip, custom-position slots, cloud/off-schedule
// winner badges, manual-end countdown and the integration_enabled switch role.
// The tile now drives standard `cover.*` services against ALL managed covers,
// reads the winner from the Cover Position sensor's `intent` attribute and the
// managed covers from its `last_moves`/`move_blocked_by` keys.

const TYPE = 'custom:adaptive-cover-tile-card';

interface CardLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  setConfig(config: AdaptiveCoverTileCardConfig): void;
  // Internal — set directly in tests to bypass the websocket registry fetch.
  _registry?: EntityRegistryEntry[] | null;
}

function makeCard(): CardLike {
  return document.createElement('adaptive-cover-tile-card') as CardLike;
}

const ENTRY = 'entry_xyz';

// unique_id suffixes are copied verbatim from the integration (spaces, not
// underscores); the role is resolved from `${platform}:${suffix}`.
const REGISTRY: EntityRegistryEntry[] = [
  {
    entity_id: 'sensor.cover_position',
    unique_id: `${ENTRY}_Cover Position`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
  {
    entity_id: 'binary_sensor.sun_infront',
    unique_id: `${ENTRY}_Sun Infront`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
  {
    entity_id: 'binary_sensor.manual_override',
    unique_id: `${ENTRY}_Manual Override`,
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
  {
    entity_id: 'button.reset_manual_override',
    unique_id: `${ENTRY}_Reset Manual Override`,
    config_entry_id: ENTRY,
    platform: 'adaptive_cover',
    device_id: null,
  },
];

function makeHass(
  overrides: Partial<{
    /** Winning engine intent (Cover Position sensor `intent` attribute). */
    intent: string;
    /** Cover Position sensor state = engine target %. */
    sensorState: string;
    /** Extra attributes merged onto the Cover Position sensor. */
    coverPositionSensorAttrs: Record<string, unknown>;
    manualOverrideOn: boolean;
    /** Toggle Control switch: false → 'off'. */
    automaticControl: boolean;
    callService: (...args: unknown[]) => unknown;
    coverLeftCurrentPosition: number | undefined;
  }> = {},
): HomeAssistant {
  return {
    states: {
      'sensor.cover_position': {
        state: overrides.sensorState ?? '42',
        attributes: {
          intent: overrides.intent ?? 'calculated',
          decision_trace: ['sun in view: tracking (position 42%)'],
          // Managed covers are discovered from the last_moves keys.
          last_moves: {
            'cover.left': '10:00 -> 42% (calculated)',
            'cover.right': '10:00 -> 42% (calculated)',
          },
          move_blocked_by: {},
          ...(overrides.coverPositionSensorAttrs ?? {}),
        },
      },
      'binary_sensor.sun_infront': { state: 'on', attributes: {} },
      'binary_sensor.manual_override': {
        state: overrides.manualOverrideOn ? 'on' : 'off',
        attributes: {},
      },
      'switch.toggle_control': {
        state: overrides.automaticControl === false ? 'off' : 'on',
        attributes: {},
      },
      'cover.left': {
        state: 'open',
        attributes: {
          friendly_name: 'Left blind',
          ...(overrides.coverLeftCurrentPosition !== undefined
            ? { current_position: overrides.coverLeftCurrentPosition }
            : {}),
        },
      },
      'cover.right': { state: 'open', attributes: { friendly_name: 'Right blind' } },
    },
    callService: overrides.callService ?? vi.fn(),
    // Resolve to the same fixture the tests inject directly, so the async
    // background fetch can't race with the test and clobber the registry.
    callWS: vi.fn().mockResolvedValue(REGISTRY),
    connection: { subscribeEvents: vi.fn().mockResolvedValue(() => {}) },
  } as unknown as HomeAssistant;
}

async function mount(
  config: AdaptiveCoverTileCardConfig,
  hass: HomeAssistant,
  registry: EntityRegistryEntry[] = REGISTRY,
): Promise<CardLike> {
  const el = makeCard();
  el.setConfig(config);
  el.hass = hass;
  document.body.appendChild(el);
  el._registry = registry;
  await el.updateComplete;
  return el;
}

const badgeText = (badge: Element): string =>
  badge.shadowRoot!.textContent!.replace(/\s+/g, ' ').trim();

describe('adaptive-cover-tile-card setConfig', () => {
  it('throws when entry_id is missing', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE } as AdaptiveCoverTileCardConfig)).toThrow(/entry_id/);
  });

  it('throws when entry_id is empty', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE, entry_id: '' })).toThrow(/entry_id/);
  });

  it('accepts a valid config', () => {
    const el = makeCard();
    expect(() => el.setConfig({ type: TYPE, entry_id: ENTRY })).not.toThrow();
  });
});

describe('adaptive-cover-tile-card render', () => {
  it('renders state and target position by default when covers report no position ("Open · 42%")', async () => {
    // cover.left has no current_position → the label falls back to the Cover
    // Position sensor state (42). formatCoverState capitalizes the raw state.
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    expect(el.shadowRoot!.querySelector('.position')?.textContent?.trim()).toBe('Open · 42%');
  });

  it('displays the live cover current_position, not the calculated sensor value', async () => {
    // Sensor state = 100 (engine target) but the actual cover sits at 16 → 16%.
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ sensorState: '100', coverLeftCurrentPosition: 16 }),
    );
    expect(el.shadowRoot!.querySelector('.position')?.textContent?.trim()).toBe('Open · 16%');
  });

  it('renders only the percentage when show_state is false', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, show_state: false }, makeHass());
    expect(el.shadowRoot!.querySelector('.position')?.textContent?.trim()).toBe('42%');
  });

  it('renders only the state when show_position is false', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, show_position: false }, makeHass());
    expect(el.shadowRoot!.querySelector('.position')?.textContent?.trim()).toBe('Open');
  });

  it('hides the position cell entirely when both toggles are off', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, show_position: false, show_state: false },
      makeHass(),
    );
    expect(el.shadowRoot!.querySelector('.position')).toBeFalsy();
  });

  it('shows the entry-not-found message when the registry has no entities for the entry', async () => {
    const hass = makeHass();
    (hass as unknown as { callWS: unknown }).callWS = vi.fn().mockResolvedValue([]);
    const el = await mount({ type: TYPE, entry_id: ENTRY }, hass, []);
    expect(el.shadowRoot!.textContent).toContain(`Adaptive Cover entry ${ENTRY} not found.`);
  });
});

describe('adaptive-cover-tile-card winner badge (intent-driven)', () => {
  it('renders the Solar tracking badge when the winning intent is calculated', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ intent: 'calculated' }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toBe('Solar tracking');
    expect(badge!.hasAttribute('resumable')).toBe(false);
  });

  it('maps privacy / sunset / climate_block_heat / admit_no_glare intents to their badges', async () => {
    const cases: Array<[string, string]> = [
      ['privacy', 'Privacy'],
      ['sunset', 'Sunset'],
      ['climate_block_heat', 'Climate'],
      ['admit_no_glare', 'No glare'],
    ];
    for (const [intent, label] of cases) {
      const el = await mount(
        { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
        makeHass({ intent }),
      );
      const badge = el.shadowRoot!.querySelector('acp-tile-badge');
      expect(badge, intent).toBeTruthy();
      expect(badgeText(badge!), intent).toBe(label);
    }
  });

  it('falls back to the Auto badge for an unknown intent', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ intent: 'something_new' }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toBe('Auto');
  });

  it('treats a missing intent attribute as the default winner (Auto badge)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ coverPositionSensorAttrs: { intent: undefined } }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toBe('Auto');
  });

  it('hides the solar winner badge when badges.solar is false', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line', badges: { solar: false } },
      makeHass({ intent: 'calculated' }),
    );
    expect(el.shadowRoot!.querySelector('acp-tile-badge')).toBeFalsy();
  });

  it('renders the Off badge when the Toggle Control switch is off', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ automaticControl: false }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toBe('Off');
  });

  it('shows Manual badge when the Manual Override binary is on even if the intent is calculated', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ manualOverrideOn: true, intent: 'calculated' }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toMatch(/manual/i);
  });

  it('makes the badge resumable when manual override is on and a reset button exists', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ manualOverrideOn: true }),
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badge!.hasAttribute('resumable')).toBe(true);
  });

  it('keeps the badge non-resumable when the reset button role is not discovered', async () => {
    const registryNoButton = REGISTRY.filter(
      (e) => e.entity_id !== 'button.reset_manual_override',
    );
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ manualOverrideOn: true }),
      registryNoButton,
    );
    const badge = el.shadowRoot!.querySelector('acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badge!.hasAttribute('resumable')).toBe(false);
  });

  it('keeps the badge non-resumable when no manual override is active', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ manualOverrideOn: false }),
    );
    const badges = Array.from(
      el.shadowRoot!.querySelector('.tile-body')!.querySelectorAll('acp-tile-badge'),
    );
    expect(badges.length).toBeGreaterThan(0);
    for (const b of badges) expect(b.hasAttribute('resumable')).toBe(false);
  });
});

describe('adaptive-cover-tile-card service calls', () => {
  it('↑ calls cover.set_cover_position(100) against ALL managed covers in one call', async () => {
    const callService = vi.fn();
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass({ callService }));
    (el.shadowRoot!.querySelector('button.up') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: ['cover.left', 'cover.right'],
      position: 100,
    });
  });

  it('■ calls cover.stop_cover on all managed covers', async () => {
    const callService = vi.fn();
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass({ callService }));
    (el.shadowRoot!.querySelector('button.stop') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'stop_cover', {
      entity_id: ['cover.left', 'cover.right'],
    });
  });

  it('↓ calls cover.set_cover_position(0)', async () => {
    const callService = vi.fn();
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass({ callService }));
    (el.shadowRoot!.querySelector('button.down') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: ['cover.left', 'cover.right'],
      position: 0,
    });
  });

  it('uses config.cover override (single-element array) when provided', async () => {
    const callService = vi.fn();
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, cover: 'cover.right' },
      makeHass({ callService }),
    );
    (el.shadowRoot!.querySelector('button.up') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: ['cover.right'],
      position: 100,
    });
  });

  it('drives the tilt axis (set_cover_tilt_position) for a tilt-only entry', async () => {
    // Discovery infers cover_tilt only when EVERY managed cover reports
    // current_tilt_position and NO current_position.
    const callService = vi.fn();
    const hass = makeHass({ callService });
    (hass.states['cover.left'].attributes as Record<string, unknown>).current_tilt_position = 35;
    (hass.states['cover.right'].attributes as Record<string, unknown>).current_tilt_position = 50;
    const el = await mount({ type: TYPE, entry_id: ENTRY }, hass);
    (el.shadowRoot!.querySelector('button.up') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_tilt_position', {
      entity_id: ['cover.left', 'cover.right'],
      tilt_position: 100,
    });
  });

  it('keeps the position axis when any managed cover reports current_position', async () => {
    const callService = vi.fn();
    const hass = makeHass({ callService, coverLeftCurrentPosition: 40 });
    (hass.states['cover.left'].attributes as Record<string, unknown>).current_tilt_position = 35;
    const el = await mount({ type: TYPE, entry_id: ENTRY }, hass);
    (el.shadowRoot!.querySelector('button.up') as HTMLElement).click();
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: ['cover.left', 'cover.right'],
      position: 100,
    });
  });

  it('disables all controls when the integration has recorded no managed covers', async () => {
    const hass = makeHass({ coverPositionSensorAttrs: { last_moves: {}, move_blocked_by: {} } });
    const el = await mount({ type: TYPE, entry_id: ENTRY }, hass);
    expect((el.shadowRoot!.querySelector('button.up') as HTMLButtonElement).disabled).toBe(true);
    expect((el.shadowRoot!.querySelector('button.stop') as HTMLButtonElement).disabled).toBe(true);
    expect((el.shadowRoot!.querySelector('button.down') as HTMLButtonElement).disabled).toBe(true);
  });

  it('badge acp-resume event calls button.press on the reset override button', async () => {
    const callService = vi.fn();
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ manualOverrideOn: true, callService }),
    );
    el.shadowRoot!.querySelector('acp-tile-badge')!.dispatchEvent(
      new CustomEvent('acp-resume', { bubbles: true, composed: true }),
    );
    expect(callService).toHaveBeenCalledWith('button', 'press', {
      entity_id: 'button.reset_manual_override',
    });
  });
});

describe('adaptive-cover-tile-card control disabling at travel limits', () => {
  const upBtn = (el: CardLike) => el.shadowRoot!.querySelector('button.up') as HTMLButtonElement;
  const stopBtn = (el: CardLike) =>
    el.shadowRoot!.querySelector('button.stop') as HTMLButtonElement;
  const downBtn = (el: CardLike) =>
    el.shadowRoot!.querySelector('button.down') as HTMLButtonElement;

  it('disables ↑ (open) but not ↓ (close) when the first cover reports fully open (100)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ coverLeftCurrentPosition: 100 }),
    );
    expect(upBtn(el).disabled).toBe(true);
    expect(downBtn(el).disabled).toBe(false);
    expect(stopBtn(el).disabled).toBe(false);
  });

  it('disables ↓ (close) but not ↑ (open) when the first cover reports fully closed (0)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ coverLeftCurrentPosition: 0 }),
    );
    expect(downBtn(el).disabled).toBe(true);
    expect(upBtn(el).disabled).toBe(false);
    expect(stopBtn(el).disabled).toBe(false);
  });

  it('leaves both ↑ and ↓ enabled at a mid position (40)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY },
      makeHass({ coverLeftCurrentPosition: 40 }),
    );
    expect(upBtn(el).disabled).toBe(false);
    expect(downBtn(el).disabled).toBe(false);
    expect(stopBtn(el).disabled).toBe(false);
  });

  it('leaves both enabled when the cover does not report a position', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    expect(upBtn(el).disabled).toBe(false);
    expect(downBtn(el).disabled).toBe(false);
    expect(stopBtn(el).disabled).toBe(false);
  });
});

describe('adaptive-cover-tile-card tap action', () => {
  it('fires acp-tile-tap event on tile body click when tap_action is default (dialog)', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    const listener = vi.fn();
    el.addEventListener('acp-tile-tap', listener);
    (el.shadowRoot!.querySelector('.tile-body') as HTMLElement).click();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('does not fire acp-tile-tap when tap_action is none (legacy string normalized)', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, tap_action: 'none' }, makeHass());
    const listener = vi.fn();
    el.addEventListener('acp-tile-tap', listener);
    (el.shadowRoot!.querySelector('.tile-body') as HTMLElement).click();
    expect(listener).not.toHaveBeenCalled();
  });

  it('does not fire acp-tile-tap when tap_action is {action: none}', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, tap_action: { action: 'none' } },
      makeHass(),
    );
    const listener = vi.fn();
    el.addEventListener('acp-tile-tap', listener);
    (el.shadowRoot!.querySelector('.tile-body') as HTMLElement).click();
    expect(listener).not.toHaveBeenCalled();
  });

  it('treats legacy tap_action "dialog" as the default (still opens the dialog)', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, tap_action: 'dialog' }, makeHass());
    const listener = vi.fn();
    el.addEventListener('acp-tile-tap', listener);
    (el.shadowRoot!.querySelector('.tile-body') as HTMLElement).click();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('does not fire acp-tile-tap when ↑■↓ buttons are clicked (stopPropagation)', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    const listener = vi.fn();
    el.addEventListener('acp-tile-tap', listener);
    (el.shadowRoot!.querySelector('button.up') as HTMLElement).click();
    (el.shadowRoot!.querySelector('button.stop') as HTMLElement).click();
    (el.shadowRoot!.querySelector('button.down') as HTMLElement).click();
    expect(listener).not.toHaveBeenCalled();
  });

  it('threads show_elevation_chart=false into the dialog as showElevationChart=false', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, show_elevation_chart: false },
      makeHass(),
    );
    const dialog = el.shadowRoot!.querySelector('acp-more-info-dialog') as HTMLElement & {
      showElevationChart?: boolean;
    };
    expect(dialog).toBeTruthy();
    expect(dialog.showElevationChart).toBe(false);
  });

  it('defaults showElevationChart to true on the dialog when the key is omitted', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    const dialog = el.shadowRoot!.querySelector('acp-more-info-dialog') as HTMLElement & {
      showElevationChart?: boolean;
    };
    expect(dialog.showElevationChart).toBe(true);
  });

  it('forwards the badges opt-in config to the dialog', async () => {
    const badges = { solar: false };
    const el = await mount({ type: TYPE, entry_id: ENTRY, badges }, makeHass());
    const dialog = el.shadowRoot!.querySelector('acp-more-info-dialog') as HTMLElement & {
      badges?: unknown;
    };
    expect(dialog.badges).toEqual(badges);
  });

  it('opens the more-info dialog on tile body click and closes via dialog close event', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    const dialog = el.shadowRoot!.querySelector('acp-more-info-dialog') as HTMLElement & {
      open?: boolean;
      updateComplete: Promise<boolean>;
    };
    expect(dialog).toBeTruthy();
    expect(dialog.open).toBe(false);

    (el.shadowRoot!.querySelector('.tile-body') as HTMLElement).click();
    await el.updateComplete;
    await dialog.updateComplete;
    expect(dialog.open).toBe(true);

    dialog.dispatchEvent(new CustomEvent('acp-dialog-close', { bubbles: true, composed: true }));
    await el.updateComplete;
    await dialog.updateComplete;
    expect(dialog.open).toBe(false);
  });
});

describe('adaptive-cover-tile-card new options', () => {
  it('show_controls: false hides the ↑■▼ row', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, show_controls: false }, makeHass());
    expect(el.shadowRoot!.querySelector('.controls')).toBeFalsy();
  });

  it('show_badge: false hides the contextual badge (and the Auto line)', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, show_badge: false }, makeHass());
    const body = el.shadowRoot!.querySelector('.tile-body')!;
    expect(body.querySelector('acp-tile-badge')).toBeFalsy();
    expect(body.querySelector('.auto-line')).toBeFalsy();
  });

  it('icon overrides the cover_type default', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY, icon: 'mdi:test-icon' }, makeHass());
    const icon = el.shadowRoot!.querySelector('ha-icon.cover-icon') as HTMLElement;
    expect(icon.getAttribute('icon')).toBe('mdi:test-icon');
  });

  it('show_decision_summary renders "<label> <pct>% — <last trace line>"', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, show_decision_summary: true },
      makeHass({
        intent: 'calculated',
        coverPositionSensorAttrs: {
          decision_trace: ['gates passed', 'sun in view: tracking'],
        },
      }),
    );
    const summary = el.shadowRoot!.querySelector('.summary');
    expect(summary).toBeTruthy();
    expect(summary!.textContent?.trim()).toBe('Sun tracking 42% — sun in view: tracking');
  });

  it('omits the summary line when show_decision_summary is unset', async () => {
    const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass());
    expect(el.shadowRoot!.querySelector('.summary')).toBeFalsy();
  });

  it('one-line layout keeps the summary nested inside .label', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, show_decision_summary: true, layout: 'one-line' },
      makeHass(),
    );
    const summary = el.shadowRoot!.querySelector('.summary');
    expect(summary).toBeTruthy();
    expect(summary!.parentElement?.classList.contains('label')).toBe(true);
    expect(el.shadowRoot!.querySelector('.tile-body.has-summary')).toBeFalsy();
  });

  it('detailed layout shows the summary inline with the title, right-justified', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, show_decision_summary: true, layout: 'detailed' },
      makeHass(),
    );
    const summary = el.shadowRoot!.querySelector('.summary');
    expect(summary).toBeTruthy();
    expect(summary!.classList.contains('inline-summary')).toBe(true);
    expect(summary!.parentElement?.classList.contains('label')).toBe(true);
    expect(el.shadowRoot!.querySelector('.tile-body.detailed.has-summary')).toBeTruthy();
  });

  it('detailed layout renders the winner badge inline on the state line', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ intent: 'calculated' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed');
    expect(body).toBeTruthy();
    const badge = el.shadowRoot!.querySelector('.detail-line acp-tile-badge');
    expect(badge).toBeTruthy();
  });

  it('detailed layout renders no tile badge when show_badge is false', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed', show_badge: false },
      makeHass(),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed');
    expect(body).toBeTruthy();
    // Scope to the tile body — the more-info dialog has its own badges, and
    // happy-dom's querySelector pierces shadow roots.
    expect(body!.querySelector('acp-tile-badge')).toBeFalsy();
  });
});

describe('adaptive-cover-tile-card Auto indicator', () => {
  it('detailed: solar wins under automatic control → BOTH the Solar winner badge and a separate Auto badge', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ intent: 'calculated' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    const badges = body.querySelectorAll('acp-tile-badge');
    expect(badges.length).toBe(2);

    const detailLineBadge = body.querySelector('.detail-line acp-tile-badge');
    expect(detailLineBadge).toBeTruthy();
    expect(badgeText(detailLineBadge!)).toBe('Solar tracking');

    const autoLine = body.querySelector('.auto-line');
    expect(autoLine).toBeTruthy();
    const autoBadge = autoLine!.querySelector('acp-tile-badge');
    expect(autoBadge).toBeTruthy();
    expect(badgeText(autoBadge!)).toBe('Auto');
  });

  it('detailed: .auto-line appears in DOM order BEFORE .detail-line', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ intent: 'calculated' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    const rows = Array.from(body.children);
    const autoIdx = rows.findIndex((n) => (n as Element).classList.contains('auto-line'));
    const detailIdx = rows.findIndex((n) => (n as Element).classList.contains('detail-line'));
    expect(autoIdx).toBeGreaterThanOrEqual(0);
    expect(detailIdx).toBeGreaterThanOrEqual(0);
    expect(autoIdx).toBeLessThan(detailIdx);
  });

  it('detailed: default winner (auto kind) renders the Auto line only — no duplicate inline Auto badge', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ intent: 'default' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    const badges = body.querySelectorAll('acp-tile-badge');
    expect(badges.length).toBe(1);
    expect(body.querySelector('.auto-line acp-tile-badge')).toBeTruthy();
    expect(body.querySelector('.detail-line acp-tile-badge')).toBeFalsy();
  });

  it('detailed: manual override active → no Auto badge', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ manualOverrideOn: true }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    expect(body.querySelector('.auto-line')).toBeFalsy();
  });

  it('detailed: Toggle Control off → no Auto badge (Off winner badge remains)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed' },
      makeHass({ automaticControl: false }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    expect(body.querySelector('.auto-line')).toBeFalsy();
    const badge = body.querySelector('.detail-line acp-tile-badge');
    expect(badge).toBeTruthy();
    expect(badgeText(badge!)).toBe('Off');
  });

  it('detailed: badges.auto false hides the Auto badge but keeps the winner badge', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed', badges: { auto: false } },
      makeHass({ intent: 'calculated' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body.detailed')!;
    expect(body.querySelector('.auto-line')).toBeFalsy();
    expect(body.querySelector('.detail-line acp-tile-badge')).toBeTruthy();
  });

  it('one-line: solar winner → no .auto-line, exactly one badge', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'one-line' },
      makeHass({ intent: 'calculated' }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body')!;
    expect(body.querySelector('.auto-line')).toBeFalsy();
    expect(body.querySelectorAll('acp-tile-badge').length).toBe(1);
  });
});

describe('adaptive-cover-tile-card hold / double-tap actions', () => {
  it('hold_action fires via handleAction when pointer is held', async () => {
    vi.useFakeTimers();
    try {
      const callService = vi.fn();
      const el = await mount(
        {
          type: TYPE,
          entry_id: ENTRY,
          hold_action: {
            action: 'call-service',
            service: 'cover.open_cover',
            service_data: { entity_id: 'cover.left' },
          },
        },
        makeHass({ callService }),
      );
      const body = el.shadowRoot!.querySelector('.tile-body') as HTMLElement;
      body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      vi.advanceTimersByTime(600);
      expect(callService).toHaveBeenCalledWith(
        'cover',
        'open_cover',
        { entity_id: 'cover.left' },
        undefined,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not fire hold_action when none is configured', async () => {
    vi.useFakeTimers();
    try {
      const callService = vi.fn();
      const el = await mount({ type: TYPE, entry_id: ENTRY }, makeHass({ callService }));
      const body = el.shadowRoot!.querySelector('.tile-body') as HTMLElement;
      body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      vi.advanceTimersByTime(600);
      expect(callService).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('double_tap_action fires on a quick double-click', async () => {
    const callService = vi.fn();
    const el = await mount(
      {
        type: TYPE,
        entry_id: ENTRY,
        double_tap_action: {
          action: 'call-service',
          service: 'cover.close_cover',
          service_data: { entity_id: 'cover.left' },
        },
      },
      makeHass({ callService }),
    );
    const body = el.shadowRoot!.querySelector('.tile-body') as HTMLElement;
    body.click();
    body.click();
    expect(callService).toHaveBeenCalledWith(
      'cover',
      'close_cover',
      { entity_id: 'cover.left' },
      undefined,
    );
  });

  it('single click still opens the dialog when double_tap_action is configured (after timeout)', async () => {
    vi.useFakeTimers();
    try {
      const el = await mount(
        {
          type: TYPE,
          entry_id: ENTRY,
          double_tap_action: { action: 'call-service', service: 'cover.close_cover' },
        },
        makeHass(),
      );
      const listener = vi.fn();
      el.addEventListener('acp-tile-tap', listener);
      const body = el.shadowRoot!.querySelector('.tile-body') as HTMLElement;
      body.click();
      vi.advanceTimersByTime(300);
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('adaptive-cover-tile-card narrow-column responsiveness (#136)', () => {
  it('keeps all three controls and the full title in detailed layout (regression guard)', async () => {
    const el = await mount(
      { type: TYPE, entry_id: ENTRY, layout: 'detailed', name: 'Centre Gauche' },
      makeHass(),
    );
    expect(el.shadowRoot!.querySelectorAll('.controls button').length).toBe(3);
    const title = el.shadowRoot!.querySelector('.title');
    expect(title).toBeTruthy();
    expect(title!.textContent?.trim()).toBe('Centre Gauche');
  });

  it('declares an inline-size container so the column width drives the layout', () => {
    const css = (AdaptiveCoverTileCard.styles as { cssText: string }).cssText;
    expect(css).toContain('container-type: inline-size');
  });

  it('reflows the detailed controls onto their own full-width row at a narrow breakpoint', () => {
    const css = (AdaptiveCoverTileCard.styles as { cssText: string }).cssText;
    expect(css).toContain('@container');
    expect(css).toContain('controls controls controls');
  });

  it('reflows phone tiles via a viewport gate, not tile width alone (#154)', () => {
    const css = (AdaptiveCoverTileCard.styles as { cssText: string }).cssText;
    expect(css).toContain('@media (max-width: 500px)');
    expect(css).toContain('max-width: 480px');
  });

  it('still reflows a genuinely narrow desktop column via the container query (#136)', () => {
    const css = (AdaptiveCoverTileCard.styles as { cssText: string }).cssText;
    expect(css).toContain('@container (max-width: 340px)');
  });
});

interface GridOptions {
  columns: number | string;
  rows: number | string;
  min_columns: number;
  min_rows: number;
}
interface GridTileLike extends CardLike {
  getGridOptions(): GridOptions;
}

describe('AdaptiveCoverTileCard.getGridOptions', () => {
  it('defaults to full section width and content-driven (auto) height', () => {
    const card = makeCard() as GridTileLike;
    card.setConfig({ type: TYPE, entry_id: ENTRY });
    const opts = card.getGridOptions();
    expect(opts.columns).toBe('full');
    expect(opts.rows).toBe('auto');
    expect(opts.min_columns).toBe(3);
  });

  it('floors detailed (default) layout at 2 rows so controls never clip', () => {
    const card = makeCard() as GridTileLike;
    card.setConfig({ type: TYPE, entry_id: ENTRY });
    expect(card.getGridOptions().min_rows).toBe(2);
  });

  it('lets the one-line layout shrink to a single row', () => {
    const card = makeCard() as GridTileLike;
    card.setConfig({ type: TYPE, entry_id: ENTRY, layout: 'one-line' });
    expect(card.getGridOptions().min_rows).toBe(1);
  });

  it('keeps the auto-height default regardless of layout mode', () => {
    const card = makeCard() as GridTileLike;
    card.setConfig({ type: TYPE, entry_id: ENTRY, layout: 'one-line' });
    expect(card.getGridOptions().rows).toBe('auto');
  });
});
