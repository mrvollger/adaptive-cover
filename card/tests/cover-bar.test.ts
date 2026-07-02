// Rewritten for the Adaptive Cover integration: the target is the Cover
// Position sensor STATE, per-cover actuals come live from the managed cover
// entities' current_position (current_tilt_position for tilt entries), and
// track clicks call the standard cover.set_cover_position /
// cover.set_cover_tilt_position services. Removed with their features: the
// dual-axis acp-tilt-bar rows, the position-mismatch alert badge, and the
// INTEGRATION_DOMAIN custom set_position/set_tilt services.
import { describe, it, expect, vi } from 'vitest';
import '../src/components/cover-bar';
import { CoverBar } from '../src/components/cover-bar';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';
import type { CSSResult } from 'lit';

interface CoverBarLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discovered?: DiscoveredEntities;
  coverColor?: string | null;
}

const baseDiscovered: DiscoveredEntities = {
  entry_id: 'entry1',
  entry_title: 'Test',
  cover_type: 'cover_blind',
  entities: { target_position_sensor: 'sensor.cover_position' },
  managed_covers: [],
};

interface FixtureOpts {
  /** Cover Position sensor state (target %). */
  target?: string;
  /** entity_id → current_position for the managed covers. */
  covers?: Record<string, number>;
  /** entity_id → current_tilt_position (tilt entries). */
  tiltCovers?: Record<string, number>;
  overrideOn?: boolean;
  callService?: ReturnType<typeof vi.fn>;
}

function makeHass(opts: FixtureOpts = {}): HomeAssistant {
  const states: Record<string, unknown> = {
    'sensor.cover_position': { state: opts.target ?? '42', attributes: {} },
  };
  for (const [id, pos] of Object.entries(opts.covers ?? {})) {
    states[id] = {
      state: 'open',
      attributes: { friendly_name: id.split('.')[1], current_position: pos },
    };
  }
  for (const [id, tilt] of Object.entries(opts.tiltCovers ?? {})) {
    states[id] = {
      state: 'open',
      attributes: { friendly_name: id.split('.')[1], current_tilt_position: tilt },
    };
  }
  if (opts.overrideOn !== undefined) {
    states['binary_sensor.manual_override'] = {
      state: opts.overrideOn ? 'on' : 'off',
      attributes: {},
    };
  }
  return { states, callService: opts.callService ?? vi.fn() } as unknown as HomeAssistant;
}

async function mountBar(
  hass: HomeAssistant,
  discovered: DiscoveredEntities,
  coverColor?: string | null,
): Promise<CoverBarLike> {
  const el = document.createElement('acp-cover-bar') as CoverBarLike;
  document.body.appendChild(el);
  el.hass = hass;
  el.discovered = discovered;
  if (coverColor !== undefined) el.coverColor = coverColor;
  await el.updateComplete;
  return el;
}

describe('acp-cover-bar fill style — issue #135', () => {
  it('fill CSS uses color-mix for reduced opacity', () => {
    const styles = (CoverBar as unknown as { styles: CSSResult }).styles.cssText;
    expect(styles).toContain('color-mix');
  });

  it('renders the percent label before the track', async () => {
    const el = await mountBar(makeHass({ target: '31', covers: { 'cover.living_room': 31 } }), {
      ...baseDiscovered,
      managed_covers: ['cover.living_room'],
    });
    const cover = el.shadowRoot!.querySelector('.cover')!;
    const children = Array.from(cover.children);
    const numIdx = children.findIndex((c) => c.classList.contains('num'));
    const trackIdx = children.findIndex((c) => c.classList.contains('track'));
    expect(numIdx).toBeGreaterThanOrEqual(0);
    expect(trackIdx).toBeGreaterThanOrEqual(0);
    expect(numIdx).toBeLessThan(trackIdx);
  });
});

describe('acp-cover-bar two-tone fill — issue #135 follow-up', () => {
  it('both segments derive from the cover colour — open pale, closed solid', () => {
    const styles = (CoverBar as unknown as { styles: CSSResult }).styles.cssText;
    expect(styles).toMatch(/\.fill\s*{[^}]*--acp-cover-color,\s*var\(--primary-color\)\)\s*18%/);
    expect(styles).toMatch(
      /\.fill-closed\s*{[^}]*--acp-cover-color,\s*var\(--primary-color\)\)\s*50%/,
    );
    expect(styles).not.toMatch(/\.fill[^}]*--warning-color/);
  });

  it('splits the track into open + closed widths summing to 100%', async () => {
    const el = await mountBar(makeHass({ target: '69', covers: { 'cover.gauche': 69 } }), {
      ...baseDiscovered,
      managed_covers: ['cover.gauche'],
    });
    const open = el.shadowRoot!.querySelector('.fill') as HTMLElement;
    const closed = el.shadowRoot!.querySelector('.fill-closed') as HTMLElement;
    expect(open.style.width).toBe('69%');
    expect(closed.style.width).toBe('31%');
  });

  it('closed segment falls back to --primary-color when no cover colour is set', () => {
    const styles = (CoverBar as unknown as { styles: CSSResult }).styles.cssText;
    expect(styles).toMatch(/\.fill-closed\s*{[^}]*--acp-cover-color,\s*var\(--primary-color\)/);
  });

  it('applies the user-selected cover colour as the --acp-cover-color var', async () => {
    const el = await mountBar(
      makeHass({ target: '69', covers: { 'cover.gauche': 69 } }),
      { ...baseDiscovered, managed_covers: ['cover.gauche'] },
      '#ff7043',
    );
    const wrap = el.shadowRoot!.querySelector('.wrap') as HTMLElement;
    expect(wrap.style.getPropertyValue('--acp-cover-color')).toBe('#ff7043');
  });
});

describe('acp-cover-bar manual-override divergence', () => {
  // Cover held at 44% by the user while the engine target stays 60%: the
  // sensor state is the target and the cover entity reports the held actual.
  const overrideDiscovered: DiscoveredEntities = {
    ...baseDiscovered,
    entities: {
      target_position_sensor: 'sensor.cover_position',
      manual_override_binary: 'binary_sensor.manual_override',
    },
    managed_covers: ['cover.a'],
  };

  function divergentHass(overrideOn: boolean): HomeAssistant {
    return makeHass({ target: '60', covers: { 'cover.a': 44 }, overrideOn });
  }

  it('labels the COVERS header with the engine target (60%), not the held 44%', async () => {
    const el = await mountBar(divergentHass(true), overrideDiscovered);
    const target = el.shadowRoot!.querySelector('.head .target')!.textContent!;
    expect(target).toContain('60');
    expect(target).not.toContain('44');
  });

  it('draws the target marker at the engine target while fill/num stay at the held value', async () => {
    const el = await mountBar(divergentHass(true), overrideDiscovered);
    const marker = el.shadowRoot!.querySelector('.marker') as HTMLElement;
    const open = el.shadowRoot!.querySelector('.fill') as HTMLElement;
    const num = el.shadowRoot!.querySelector('.num')!.textContent!;
    // (happy-dom drops clamp() from style.left, so read the rendered attribute.)
    expect(marker.getAttribute('style')).toContain('left:clamp(1px, 60%, calc(100% - 1px))');
    expect(open.style.width).toBe('44%');
    expect(num).toContain('44');
  });

  it('relabels the COVERS header to "Solar target" during a diverging override', async () => {
    const el = await mountBar(divergentHass(true), overrideDiscovered);
    const target = el.shadowRoot!.querySelector('.head .target')!.textContent!;
    expect(target).toContain('Solar target');
    expect(target).toContain('60');
  });

  it('uses the override-specific marker tooltip during a diverging override', async () => {
    const el = await mountBar(divergentHass(true), overrideDiscovered);
    const marker = el.shadowRoot!.querySelector('.marker') as HTMLElement;
    const tip = marker.getAttribute('data-tooltip') ?? '';
    expect(tip).toContain('Would-be solar target');
    expect(tip).toContain('60');
    expect(tip).toContain('held by manual override');
  });

  it('keeps the plain "Target" header label and base tooltip without a divergence', async () => {
    const el = await mountBar(divergentHass(false), overrideDiscovered);
    const target = el.shadowRoot!.querySelector('.head .target')!.textContent!;
    expect(target).toContain('Target');
    expect(target).not.toContain('Solar target');
    const marker = el.shadowRoot!.querySelector('.marker') as HTMLElement;
    const tip = marker.getAttribute('data-tooltip') ?? '';
    expect(tip).not.toContain('Would-be solar target');
  });

  it('renders no mismatch alert badge (feature removed with this integration)', async () => {
    const el = await mountBar(divergentHass(false), overrideDiscovered);
    expect(el.shadowRoot!.querySelector('.cover ha-icon.warn')).toBeNull();
  });

  it('reserves a fixed badge column so the track does not reflow', () => {
    const styles = (CoverBar as unknown as { styles: CSSResult }).styles.cssText;
    expect(styles).toMatch(/grid-template-columns:[^;]*3fr\s+16px/);
    expect(styles).not.toMatch(/grid-template-columns:[^;]*3fr\s+auto/);
  });
});

describe('acp-cover-bar target marker clamp at extremes', () => {
  async function mountAtTarget(target: number, held: number): Promise<CoverBarLike> {
    return mountBar(
      makeHass({ target: String(target), covers: { 'cover.a': held }, overrideOn: true }),
      {
        ...baseDiscovered,
        entities: {
          target_position_sensor: 'sensor.cover_position',
          manual_override_binary: 'binary_sensor.manual_override',
        },
        managed_covers: ['cover.a'],
      },
    );
  }

  it('centres the marker on its value via translateX(-50%)', () => {
    const styles = (CoverBar as unknown as { styles: CSSResult }).styles.cssText;
    expect(styles).toMatch(/\.marker\s*{[^}]*translateX\(-50%\)/);
  });

  it('clamps the marker inside the rail at the 100% extreme', async () => {
    const el = await mountAtTarget(100, 70);
    const marker = el.shadowRoot!.querySelector('.marker') as HTMLElement;
    expect(marker.getAttribute('style')).toContain('left:clamp(1px, 100%, calc(100% - 1px))');
  });

  it('clamps the marker inside the rail at the 0% extreme', async () => {
    const el = await mountAtTarget(0, 30);
    const marker = el.shadowRoot!.querySelector('.marker') as HTMLElement;
    expect(marker.getAttribute('style')).toContain('left:clamp(1px, 0%, calc(100% - 1px))');
  });
});

describe('acp-cover-bar tilt entries (cover_type=cover_tilt)', () => {
  const tiltDiscovered: DiscoveredEntities = {
    ...baseDiscovered,
    cover_type: 'cover_tilt',
    managed_covers: ['cover.a'],
  };

  it('reads the live value from current_tilt_position for tilt covers', async () => {
    const el = await mountBar(
      makeHass({ target: '70', tiltCovers: { 'cover.a': 35 } }),
      tiltDiscovered,
    );
    expect(el.shadowRoot!.querySelector('.num')!.textContent).toContain('35');
    const open = el.shadowRoot!.querySelector('.fill') as HTMLElement;
    expect(open.style.width).toBe('35%');
  });

  it('calls cover.set_cover_tilt_position when the track is clicked', async () => {
    const callService = vi.fn();
    const el = await mountBar(
      makeHass({ target: '70', tiltCovers: { 'cover.a': 35 }, callService }),
      tiltDiscovered,
    );
    const track = el.shadowRoot!.querySelector('.track') as HTMLElement;
    Object.defineProperty(track, 'getBoundingClientRect', {
      value: () => ({ left: 0, width: 100, top: 0, bottom: 10, right: 100, height: 10 }),
      configurable: true,
    });
    track.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 80 }));
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_tilt_position', {
      entity_id: 'cover.a',
      tilt_position: 80,
    });
  });
});

describe('acp-cover-bar track-click → cover.set_cover_position', () => {
  it('calls cover.set_cover_position with the clicked percentage', async () => {
    const callService = vi.fn();
    const el = await mountBar(makeHass({ target: '40', covers: { 'cover.left': 40 }, callService }), {
      ...baseDiscovered,
      managed_covers: ['cover.left'],
    });
    const track = el.shadowRoot!.querySelector('.track') as HTMLElement;
    // Simulate a click at 50% of the track.
    Object.defineProperty(track, 'getBoundingClientRect', {
      value: () => ({ left: 0, width: 100, top: 0, bottom: 10, right: 100, height: 10 }),
      configurable: true,
    });
    track.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 50 }));
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: 'cover.left',
      position: 50,
    });
  });

  it('clamps clicks past the track edges into 0..100', async () => {
    const callService = vi.fn();
    const el = await mountBar(makeHass({ target: '40', covers: { 'cover.left': 40 }, callService }), {
      ...baseDiscovered,
      managed_covers: ['cover.left'],
    });
    const track = el.shadowRoot!.querySelector('.track') as HTMLElement;
    Object.defineProperty(track, 'getBoundingClientRect', {
      value: () => ({ left: 10, width: 100, top: 0, bottom: 10, right: 110, height: 10 }),
      configurable: true,
    });
    track.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 0 }));
    expect(callService).toHaveBeenCalledWith('cover', 'set_cover_position', {
      entity_id: 'cover.left',
      position: 0,
    });
  });
});
