// Rewritten for the Adaptive Cover integration: the badge now derives its kind
// from the engine intent (winner) via winnerBadgeKind, with manual/off state
// layers and an explicit kindOverride. The Pro-era slot/pct/minimumMode/
// safetyActive/manualEndIso props were removed along with their tests.
import { describe, it, expect } from 'vitest';
import '../src/components/tile-badge';
import type { BadgeKind } from '../src/const';

interface BadgeLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  winner?: string;
  compact?: boolean;
  integrationEnabled?: boolean;
  manualActive?: boolean;
  kindOverride?: BadgeKind;
  resumable?: boolean;
}

async function mountBadge(props: Partial<BadgeLike>): Promise<BadgeLike> {
  const el = document.createElement('acp-tile-badge') as BadgeLike;
  Object.assign(el, props);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

function text(el: BadgeLike): string {
  return el.shadowRoot!.textContent!.replace(/\s+/g, ' ').trim();
}

function kind(el: BadgeLike): string {
  const badge = el.shadowRoot!.querySelector('.badge') as HTMLElement;
  return Array.from(badge.classList)
    .filter((c) => c.startsWith('kind-'))
    .map((c) => c.slice('kind-'.length))[0];
}

describe('acp-tile-badge: intent → kind mapping', () => {
  it('renders Auto when winner is default', async () => {
    const el = await mountBadge({ winner: 'default' });
    expect(text(el)).toBe('Auto');
    expect(kind(el)).toBe('auto');
  });

  it('renders Auto when winner is an unknown intent', async () => {
    const el = await mountBadge({ winner: 'mystery_intent' });
    expect(text(el)).toBe('Auto');
    expect(kind(el)).toBe('auto');
  });

  it('renders Solar tracking for the calculated intent', async () => {
    const el = await mountBadge({ winner: 'calculated' });
    expect(text(el)).toBe('Solar tracking');
    expect(kind(el)).toBe('solar');
  });

  it('renders a leading ha-icon for the solar badge', async () => {
    const el = await mountBadge({ winner: 'calculated' });
    const icon = el.shadowRoot!.querySelector('ha-icon');
    expect(icon).toBeTruthy();
    expect(icon!.getAttribute('icon')).toBe('mdi:white-balance-sunny');
  });

  it('renders No glare for the admit_no_glare intent', async () => {
    const el = await mountBadge({ winner: 'admit_no_glare' });
    expect(text(el)).toBe('No glare');
    expect(kind(el)).toBe('glare_zone');
  });

  it('renders Privacy for the privacy intent', async () => {
    const el = await mountBadge({ winner: 'privacy' });
    expect(text(el)).toBe('Privacy');
    expect(kind(el)).toBe('privacy');
  });

  it('renders Sunset for the sunset intent', async () => {
    const el = await mountBadge({ winner: 'sunset' });
    expect(text(el)).toBe('Sunset');
    expect(kind(el)).toBe('sunset');
  });

  it.each(['climate_open_heat', 'climate_block_heat', 'climate_tilt_preset', 'climate_default'])(
    'renders Climate for the %s intent',
    async (intent) => {
      const el = await mountBadge({ winner: intent });
      expect(text(el)).toBe('Climate');
      expect(kind(el)).toBe('climate');
    },
  );

  it('renders Auto for shaded_by_overhang (no dedicated badge kind)', async () => {
    const el = await mountBadge({ winner: 'shaded_by_overhang' });
    expect(text(el)).toBe('Auto');
    expect(kind(el)).toBe('auto');
  });

  it('normalizes upper/mixed-case intent strings from older builds', async () => {
    const el = await mountBadge({ winner: '  Calculated ' });
    expect(text(el)).toBe('Solar tracking');
    expect(kind(el)).toBe('solar');
  });
});

describe('acp-tile-badge: state layers', () => {
  it('renders Off when integrationEnabled is false, regardless of winner', async () => {
    const el = await mountBadge({ winner: 'calculated', integrationEnabled: false });
    expect(text(el)).toBe('Off');
    expect(kind(el)).toBe('off');
  });

  it('Off wins over manualActive', async () => {
    const el = await mountBadge({
      winner: 'calculated',
      integrationEnabled: false,
      manualActive: true,
    });
    expect(kind(el)).toBe('off');
  });

  it('renders Manual when manualActive is true, regardless of winner', async () => {
    const el = await mountBadge({ winner: 'calculated', manualActive: true });
    expect(text(el)).toBe('Manual');
    expect(kind(el)).toBe('manual');
  });

  it('falls back to intent-driven kind when both layers are inactive (defaults)', async () => {
    const el = await mountBadge({ winner: 'default' });
    expect(text(el)).toBe('Auto');
    expect(kind(el)).toBe('auto');
  });

  it('kindOverride wins over the winner-derived kind', async () => {
    const el = await mountBadge({ winner: 'calculated', kindOverride: 'privacy' });
    expect(text(el)).toBe('Privacy');
    expect(kind(el)).toBe('privacy');
  });

  it('kindOverride wins even over the manual state layer', async () => {
    const el = await mountBadge({
      winner: 'calculated',
      manualActive: true,
      kindOverride: 'sunset',
    });
    expect(kind(el)).toBe('sunset');
  });
});

describe('acp-tile-badge: resumable affordance', () => {
  it('renders a plain span (not a button) when not resumable', async () => {
    const el = await mountBadge({ winner: 'default', manualActive: true });
    expect(el.shadowRoot!.querySelector('button.badge')).toBeFalsy();
    expect(el.shadowRoot!.querySelector('span.badge')).toBeTruthy();
  });

  it('renders a tappable button and emits acp-resume when resumable', async () => {
    const el = await mountBadge({ winner: 'default', manualActive: true, resumable: true });
    const button = el.shadowRoot!.querySelector('button.badge') as HTMLButtonElement;
    expect(button).toBeTruthy();
    let fired = false;
    el.addEventListener('acp-resume', () => {
      fired = true;
    });
    button.click();
    expect(fired).toBe(true);
  });

  it('adds a trailing restore icon on the resumable badge', async () => {
    const el = await mountBadge({ winner: 'default', manualActive: true, resumable: true });
    const restore = el.shadowRoot!.querySelector('ha-icon.resume-icon');
    expect(restore).toBeTruthy();
    expect(restore!.getAttribute('icon')).toBe('mdi:restore');
  });
});

describe('acp-tile-badge: compact', () => {
  it('reflects compact to the host attribute', async () => {
    const el = await mountBadge({ winner: 'default', compact: true });
    expect(el.hasAttribute('compact')).toBe(true);
  });
});
