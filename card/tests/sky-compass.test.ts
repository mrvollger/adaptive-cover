import { describe, it, expect, vi } from 'vitest';
import '../src/components/sky-compass';
import { SkyCompass } from '../src/components/sky-compass';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities } from '../src/types';
import { coverWedgeOuterRadius, normalizeAzimuth, wedgePath } from '../src/lib/geometry';

// NOTE (adaptive_cover port): the compass now reads all solar geometry from the
// `sun` attribute block on the Cover Position sensor (readSunAttrs) — there is
// no dedicated sun-position sensor, no decision-trace sensor, and:
//  - the Start/End Sun sensors are plain datetimes with NO `azimuth` attribute,
//    so the active-arc clamp (clampActiveArcToFov, #85/#89) never engages and
//    the static FOV envelope path always renders (the whole "active sun arc"
//    describe block was dropped; negative coverage below);
//  - `blind_spot_range` is never emitted, so the blind-spot wedge never draws
//    (bearing-conversion tests dropped; negative coverage below);
//  - `raw_calculated_position` / `actual_positions` attributes are gone — the
//    target is the sensor STATE and per-cover actuals are read live from each
//    managed cover's `current_position` (manual-override divergence via
//    raw_calculated_position tests dropped; the target/held split is covered
//    through live covers in the #158 block);
//  - the sun-dot validity signal is the "Sun Infront" binary sensor;
//  - the extra-crossing `fov-extra` wedges can no longer be disjoint from the
//    full-envelope primary wedge, so the "multiple FOV crossings" block was
//    dropped as unreachable with this integration.

interface SkyCompassLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discovered_list?: DiscoveredEntities[];
  coverColors?: (string | null | undefined)[];
  showLegend?: boolean;
  showStats?: boolean;
  showMoon?: boolean;
  showCardinals?: boolean;
  showBlindSpot?: boolean;
  showSunPath?: boolean;
  showSunriseSunset?: boolean;
  showCoverFill?: boolean;
  showWindowArrow?: boolean;
  northOffsetDeg?: number;
}

function makeDiscovered(
  entryId: string,
  title: string,
  opts: {
    coverType?: DiscoveredEntities['cover_type'];
    managedCovers?: string[];
    withSunInfront?: boolean;
    withOverrideBinary?: boolean;
    withStartEnd?: boolean;
  } = {},
): DiscoveredEntities {
  return {
    entry_id: entryId,
    entry_title: title,
    cover_type: opts.coverType ?? 'cover_blind',
    entities: {
      target_position_sensor: `sensor.pos_${entryId}`,
      ...(opts.withSunInfront ? { sun_infront_binary: `binary_sensor.sun_infront_${entryId}` } : {}),
      ...(opts.withOverrideBinary ? { manual_override_binary: `binary_sensor.mo_${entryId}` } : {}),
      ...(opts.withStartEnd
        ? { start_sensor: `sensor.start_${entryId}`, end_sensor: `sensor.end_${entryId}` }
        : {}),
    },
    managed_covers: opts.managedCovers ?? [],
  };
}

interface HassEntry {
  entryId: string;
  windowAzimuth: number;
  fovLeft?: number;
  fovRight?: number;
  azimuth?: number;
  elevation?: number;
  gamma?: number;
  inFov?: boolean;
  minElevation?: number;
  maxElevation?: number;
  /** Cover Position sensor state (target %). Omitted → 'unknown' (no wedge). */
  coverPos?: number;
  /** Managed cover entities: entity_id → current_position (null = attribute
   *  absent). Keys are also written into `last_moves`, mirroring discovery. */
  covers?: Record<string, number | null>;
  /** Omit the `sun` attribute block entirely (sensor not yet populated). */
  noSun?: boolean;
  sunInfront?: boolean;
  manualOverride?: boolean;
  /** Add Start/End Sun datetime sensors — plain ISO states, NO azimuth attr. */
  withStartEnd?: boolean;
}

function makeHass(entries: HassEntry[], opts: { omitLocation?: boolean } = {}): HomeAssistant {
  const states: Record<string, { state: string; attributes: Record<string, unknown> }> = {};
  for (const e of entries) {
    const covers = e.covers ?? {};
    states[`sensor.pos_${e.entryId}`] = {
      state: e.coverPos !== undefined ? String(e.coverPos) : 'unknown',
      attributes: {
        intent: 'calculated',
        ...(e.noSun
          ? {}
          : {
              sun: {
                azimuth: e.azimuth ?? 180,
                elevation: e.elevation ?? 30,
                gamma: e.gamma ?? 0,
                in_fov: e.inFov ?? true,
                window_azimuth: e.windowAzimuth,
                fov_left: e.fovLeft ?? 45,
                fov_right: e.fovRight ?? 45,
                ...(e.minElevation !== undefined ? { min_elevation: e.minElevation } : {}),
                ...(e.maxElevation !== undefined ? { max_elevation: e.maxElevation } : {}),
              },
            }),
        last_moves: Object.fromEntries(
          Object.keys(covers).map((id) => [id, '10:00 -> 42% (calculated)']),
        ),
        move_blocked_by: {},
      },
    };
    for (const [coverId, pos] of Object.entries(covers)) {
      states[coverId] = {
        state: 'open',
        attributes: {
          friendly_name: coverId,
          ...(pos !== null ? { current_position: pos } : {}),
        },
      };
    }
    states[`binary_sensor.sun_infront_${e.entryId}`] = {
      state: e.sunInfront ? 'on' : 'off',
      attributes: {},
    };
    states[`binary_sensor.mo_${e.entryId}`] = {
      state: e.manualOverride ? 'on' : 'off',
      attributes: {},
    };
    if (e.withStartEnd) {
      states[`sensor.start_${e.entryId}`] = {
        state: '2026-04-29T07:00:00+00:00',
        attributes: {},
      };
      states[`sensor.end_${e.entryId}`] = {
        state: '2026-04-29T19:00:00+00:00',
        attributes: {},
      };
    }
  }
  return {
    states,
    // Pin the zone so the sampled day anchors to the location's midnight (not
    // the test runner's), keeping the sun path deterministic across CI zones.
    config: opts.omitLocation
      ? {}
      : { latitude: 47.6, longitude: -122.3, time_zone: 'America/Los_Angeles' },
  } as unknown as HomeAssistant;
}

async function mountCompass(
  discovered_list: DiscoveredEntities[],
  hass: HomeAssistant,
  props: Partial<SkyCompassLike> = {},
): Promise<SkyCompassLike> {
  const el = document.createElement('acp-sky-compass') as SkyCompassLike;
  document.body.appendChild(el);
  el.hass = hass;
  el.discovered_list = discovered_list;
  Object.assign(el, props);
  await el.updateComplete;
  return el;
}

describe('acp-sky-compass (single entry)', () => {
  it('legend contains "Window azimuth" entry by default', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.textContent).toContain('Window azimuth');
  });

  it('legend sun glyph is an SVG circle carrying the live sun-dot class (in-FOV → no glow)', async () => {
    // Default fixture: elevation 30, in_fov true, Sun Infront binary off → the
    // aggregate state is in_fov_not_valid → class "sun in-fov" (gold, NO glow).
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    const glyph = el.shadowRoot!.querySelector('.legend circle.sun') as SVGCircleElement | null;
    expect(glyph).not.toBeNull();
    expect(glyph!.classList.contains('in-fov')).toBe(true);
    expect(glyph!.classList.contains('valid')).toBe(false);
  });

  it('legend sun glyph adopts the no-glow class when the sun is outside the FOV', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, inFov: false }]);
    const el = await mountCompass([d], hass);
    const glyph = el.shadowRoot!.querySelector('.legend circle.sun') as SVGCircleElement | null;
    expect(glyph).not.toBeNull();
    // outside_fov but above horizon → class "sun up" (light yellow, no glow).
    expect(glyph!.classList.contains('up')).toBe(true);
    expect(glyph!.classList.contains('valid')).toBe(false);
  });

  it('legend renders a phased moon glyph (image + instance-unique phase mask) when show_moon is on', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass, { showMoon: true });
    const moonImg = el.shadowRoot!.querySelector(
      '.legend image.moon-img',
    ) as SVGImageElement | null;
    expect(moonImg).not.toBeNull();
    const maskRef = moonImg!.getAttribute('mask') ?? '';
    expect(maskRef).toMatch(/^url\(#acp-legend-moon-\d+\)$/);
    const maskId = maskRef.slice(5, -1);
    const mask = el.shadowRoot!.querySelector(`.legend mask#${maskId}`);
    expect(mask).not.toBeNull();
  });

  it('legend has no moon glyph when show_moon is off', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass, { showMoon: false });
    expect(el.shadowRoot!.querySelector('.legend image.moon-img')).toBeNull();
  });

  it('empty discovered_list shows the no-entries placeholder', async () => {
    const hass = makeHass([]);
    const el = await mountCompass([], hass);
    expect(el.shadowRoot!.textContent).toContain('No Adaptive Cover entries selected');
  });

  it('shows the no-sun placeholder when the Cover Position sensor has no sun block', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, noSun: true }]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.textContent).toContain('Sun sensor not yet populated');
  });

  // The FOV span is integration-supplied (sun.fov_left/fov_right). A wide span
  // (~76°) must render its wedge without clipping — the card does no FOV math.
  it('renders a wide (~76°) FOV wedge without clipping', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, fovLeft: 38, fovRight: 38 }]);
    const el = await mountCompass([d], hass);
    const fov = el.shadowRoot!.querySelector('path.fov') as SVGPathElement | null;
    expect(fov).toBeTruthy();
    const d3 = fov!.getAttribute('d');
    expect(d3).toBeTruthy();
    expect(d3!.length).toBeGreaterThan(0);
    expect(d3).not.toContain('NaN');
  });

  it('above-horizon sun renders a flat circle, not an <image>', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('image.sun-img')).toBeNull();
    const sun = el.shadowRoot!.querySelector('circle.sun') as SVGCircleElement;
    expect(sun).toBeTruthy();
    expect(sun.classList.contains('night')).toBe(false);
  });

  it('below-horizon sun renders the night class on the flat disc', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, elevation: -10 }]);
    const el = await mountCompass([d], hass);
    const sun = el.shadowRoot!.querySelector('circle.sun.night') as SVGCircleElement;
    expect(sun).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.up')).toBeNull();
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeNull();
  });
});

describe('acp-sky-compass sun-dot 3-way state (Sun Infront binary)', () => {
  it('renders "sun valid" (hitting) when the Sun Infront binary is on', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, inFov: true, sunInfront: true },
    ]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.in-fov')).toBeNull();
    expect(el.shadowRoot!.querySelector('circle.sun.up')).toBeNull();
  });

  it('renders "sun in-fov" (no glow) when in FOV but the binary is off', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, inFov: true, sunInfront: false },
    ]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('circle.sun.in-fov')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeNull();
    expect(el.shadowRoot!.querySelector('circle.sun.up')).toBeNull();
  });

  it('renders "sun up" (dim neutral) when outside FOV', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, inFov: false, sunInfront: false },
    ]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('circle.sun.up')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.in-fov')).toBeNull();
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeNull();
  });

  it('falls back to in-fov when the Sun Infront binary is not discovered', async () => {
    // No sun_infront_binary role → directSunValid false → derive from in_fov.
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, inFov: true }]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('circle.sun.in-fov')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeNull();
  });

  it('picks the most-active state across overlapping windows (hitting wins)', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const d2 = makeDiscovered('entry2', 'Office', { withSunInfront: true });
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, inFov: true, sunInfront: false },
      { entryId: 'entry2', windowAzimuth: 180, inFov: true, sunInfront: true },
    ]);
    const el = await mountCompass([d1, d2], hass);
    expect(el.shadowRoot!.querySelector('circle.sun.valid')).toBeTruthy();
    expect(el.shadowRoot!.querySelector('circle.sun.in-fov')).toBeNull();
  });
});

describe('acp-sky-compass (multi-entry overlay)', () => {
  it('renders one FOV wedge per entry', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass);
    const fovs = el.shadowRoot!.querySelectorAll('path.fov');
    expect(fovs.length).toBe(2);
  });

  it('renders one window arrow per entry', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass);
    const arrowBases = el.shadowRoot!.querySelectorAll('circle.window-base');
    expect(arrowBases.length).toBe(2);
  });

  it('multi-entry legend shows each entry title', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Kitchen');
    expect(text).toContain('Living');
  });

  it('skips entries whose Cover Position sensor is missing without throwing', async () => {
    const good = makeDiscovered('entry1', 'Kitchen');
    const missing = makeDiscovered('entry2', 'Living');
    // entry2's sensor is absent from hass.states → readSunAttrs null → skipped.
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([good, missing], hass);
    const fovs = el.shadowRoot!.querySelectorAll('path.fov');
    expect(fovs.length).toBe(1);
  });

  it('multi-entry stats ✓ carries an explanatory tooltip', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass);
    const ticks = el.shadowRoot!.querySelectorAll('.entry-row .status.in-fov');
    expect(ticks.length).toBe(2);
    ticks.forEach((tick) => {
      expect(tick.textContent?.trim()).toBe('✓');
      const title = tick.getAttribute('data-tooltip') ?? '';
      expect(title).toContain('field of view');
    });
  });
});

describe('acp-sky-compass cover legend wording (#132 / #158)', () => {
  it('legend shows "Cover target" (retired "Cover position"), not "Cover closed"', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Cover target');
    expect(text).not.toContain('Cover closed');
    expect(text).not.toContain('Cover position');
  });
});

describe('acp-sky-compass cover legend target/held rows (#158, live covers)', () => {
  // windowAzimuth=180, fov ±45 → full FOV wedge. The target is the sensor
  // STATE; the actual/held ring is the mean of the managed covers' live
  // current_position — a manual hold shows up naturally as actual ≠ target.
  const disc = (covers: string[]) =>
    makeDiscovered('leg', 'Kitchen', { managedCovers: covers, withOverrideBinary: true });

  it('renders TWO legend rows (Cover target + Cover position (held)) when the held ring diverges', async () => {
    // Engine target 30 (state), cover held at 70 by the user.
    const hass = makeHass([
      {
        entryId: 'leg',
        windowAzimuth: 180,
        coverPos: 30,
        covers: { 'cover.x': 70 },
        manualOverride: true,
      },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    const fill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    const actual = el.shadowRoot!.querySelector('path.cover-actual') as SVGPathElement | null;
    expect(fill).not.toBeNull();
    expect(actual).not.toBeNull();
    // Target wedge reflects the engine target (30% → outer 77); the held ring
    // reflects the live position (70% → outer 33).
    const targetPath = wedgePath(
      normalizeAzimuth(135),
      normalizeAzimuth(225),
      coverWedgeOuterRadius(30, 'cover_blind', 110, 110),
      0,
      0,
    );
    const heldPath = wedgePath(
      normalizeAzimuth(135),
      normalizeAzimuth(225),
      coverWedgeOuterRadius(70, 'cover_blind', 110, 110),
      0,
      0,
    );
    expect(fill!.getAttribute('d')).toBe(targetPath);
    expect(actual!.getAttribute('d')).toBe(heldPath);
    // Legend: a solid "Cover target" swatch + a dashed "Cover position (held)".
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Cover target');
    expect(text).toContain('Cover position (held)');
    expect(el.shadowRoot!.querySelector('.swatch.cover-actual-swatch')).not.toBeNull();
  });

  it('renders a SINGLE "Cover target" legend row when no live aggregate exists', async () => {
    const hass = makeHass([{ entryId: 'leg', windowAzimuth: 180, coverPos: 40 }]);
    const el = await mountCompass([disc([])], hass);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Cover target');
    expect(text).not.toContain('Cover position (held)');
    expect(el.shadowRoot!.querySelector('.swatch.cover-actual-swatch')).toBeNull();
    expect(text).not.toContain('Cover position');
  });

  it('renders a SINGLE legend row when the live aggregate equals the target', async () => {
    const hass = makeHass([
      { entryId: 'leg', windowAzimuth: 180, coverPos: 40, covers: { 'cover.x': 40 } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Cover target');
    expect(text).not.toContain('Cover position (held)');
    expect(el.shadowRoot!.querySelector('.swatch.cover-actual-swatch')).toBeNull();
  });

  it('defines a dashed .cover-actual-swatch mirroring the dashed held ring', () => {
    const cssText = (SkyCompass as unknown as { styles: { cssText: string } }).styles.cssText;
    const idx = cssText.indexOf('.cover-actual-swatch');
    expect(idx).toBeGreaterThanOrEqual(0);
    const open = cssText.indexOf('{', idx);
    const close = cssText.indexOf('}', open);
    const block = cssText.slice(open + 1, close);
    expect(block).toMatch(/dashed/);
  });
});

describe('acp-sky-compass coverColors', () => {
  const kitchen = () => makeDiscovered('entry1', 'Kitchen');
  const kitchenHass = () => makeHass([{ entryId: 'entry1', windowAzimuth: 180, coverPos: 40 }]);

  it('single-entry override colors both the cover wedge and the FOV', async () => {
    const el = await mountCompass([kitchen()], kitchenHass(), { coverColors: ['#ff3366'] });
    const cover = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement;
    expect(cover.getAttribute('style') ?? '').toContain('#ff3366');
    const fov = el.shadowRoot!.querySelector('path.fov') as SVGPathElement;
    expect(fov.getAttribute('style') ?? '').toContain('#ff3366');
  });

  it('single-entry override colors the legend cover swatch to match the wedge', async () => {
    const el = await mountCompass([kitchen()], kitchenHass(), { coverColors: ['#ff3366'] });
    const swatch = el.shadowRoot!.querySelector('.swatch.cover-fill-swatch') as HTMLElement | null;
    expect(swatch).not.toBeNull();
    expect(swatch!.getAttribute('style') ?? '').toContain('#ff3366');
  });

  it('single-entry override colors the legend FOV swatch to match the wedge', async () => {
    const el = await mountCompass([kitchen()], kitchenHass(), { coverColors: ['#ff3366'] });
    const swatch = el.shadowRoot!.querySelector('.swatch.fov') as HTMLElement | null;
    expect(swatch).not.toBeNull();
    expect(swatch!.getAttribute('style') ?? '').toContain('#ff3366');
  });

  it('single-entry WITHOUT override leaves the FOV on its themed default (no inline color)', async () => {
    const el = await mountCompass([kitchen()], kitchenHass());
    const fov = el.shadowRoot!.querySelector('path.fov') as SVGPathElement;
    expect(fov.getAttribute('style') ?? '').toBe('');
    const swatch = el.shadowRoot!.querySelector('.swatch.fov') as HTMLElement | null;
    expect(swatch).not.toBeNull();
    expect(swatch!.getAttribute('style') ?? '').toBe('');
  });

  it('single-entry override colors the legend window-azimuth glyph to match the line', async () => {
    const el = await mountCompass([kitchen()], kitchenHass(), { coverColors: ['#ff3366'] });
    const line = el.shadowRoot!.querySelector('path.window') as SVGPathElement;
    expect(line.getAttribute('style') ?? '').toContain('#ff3366');
    const glyphLine = el.shadowRoot!.querySelector('.window-glyph line') as SVGLineElement | null;
    expect(glyphLine).not.toBeNull();
    expect(glyphLine!.getAttribute('style') ?? '').toContain('#ff3366');
    const glyphHead = el.shadowRoot!.querySelector(
      '.window-glyph path.window-head',
    ) as SVGPathElement | null;
    expect(glyphHead).not.toBeNull();
    expect(glyphHead!.getAttribute('style') ?? '').toContain('#ff3366');
  });

  it('single-entry WITHOUT override leaves the window-azimuth glyph on its theme default', async () => {
    const el = await mountCompass([kitchen()], kitchenHass());
    const glyphLine = el.shadowRoot!.querySelector('.window-glyph line') as SVGLineElement | null;
    expect(glyphLine).not.toBeNull();
    expect(glyphLine!.getAttribute('style') ?? '').toBe('');
    const glyphHead = el.shadowRoot!.querySelector(
      '.window-glyph path.window-head',
    ) as SVGPathElement | null;
    expect(glyphHead).not.toBeNull();
    expect(glyphHead!.getAttribute('style') ?? '').toBe('');
  });

  it('plotted window line carries an arrowhead at the rim that follows the override color', async () => {
    const el = await mountCompass([kitchen()], kitchenHass(), { coverColors: ['#ff3366'] });
    const head = el.shadowRoot!.querySelector(
      '.arrow-group path.window-head',
    ) as SVGPathElement | null;
    expect(head).not.toBeNull();
    expect(head!.getAttribute('d') ?? '').toMatch(/^M /);
    expect(head!.getAttribute('style') ?? '').toContain('#ff3366');
  });

  it('null slot falls back to palette color in multi-entry compass', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass, { coverColors: ['#ff3366', null] });
    const fovs = el.shadowRoot!.querySelectorAll('path.fov');
    expect(fovs[0].getAttribute('style') ?? '').toContain('#ff3366');
    // slot 1 null → colorForIndex(1) = '#ff7f0e'
    expect(fovs[1].getAttribute('style') ?? '').toContain('#ff7f0e');
  });

  it('shorter coverColors array falls back for missing slots', async () => {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    const el = await mountCompass([d1, d2], hass, { coverColors: ['#ff3366'] });
    const fovs = el.shadowRoot!.querySelectorAll('path.fov');
    expect(fovs[0].getAttribute('style') ?? '').toContain('#ff3366');
    expect(fovs[1].getAttribute('style') ?? '').toContain('#ff7f0e');
  });
});

describe('acp-sky-compass northOffsetDeg', () => {
  // Window azimuth=180. FOV ±45 → fovStart=135, fovEnd=225.
  const d = () => makeDiscovered('entry1', 'Kitchen');
  const hass = () => makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);

  it('northOffsetDeg=0 and northOffsetDeg=90 produce different FOV paths', async () => {
    const el0 = await mountCompass([d()], hass(), { northOffsetDeg: 0 });
    const el90 = await mountCompass([d()], hass(), { northOffsetDeg: 90 });
    const path0 = el0.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
    const path90 = el90.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
    expect(path0).toBeTruthy();
    expect(path90).toBeTruthy();
    expect(path0).not.toBe(path90);
  });

  it('northOffsetDeg=90 FOV path matches northOffsetDeg=0 path shifted by 90°', async () => {
    const expected = wedgePath(normalizeAzimuth(225), normalizeAzimuth(315), 110, 0, 0);
    const el90 = await mountCompass([d()], hass(), { northOffsetDeg: 90 });
    const actual = el90.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
    expect(actual).toBe(expected);
  });
});

// The blind-spot bearing-conversion tests were dropped: the integration never
// emits `blind_spot_range` on the sun block, so the wedge can never draw.
describe('acp-sky-compass blind spot (never rendered by this integration)', () => {
  it('keeps the blind-spot group hidden and empty even with showBlindSpot on (default)', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass, { showBlindSpot: true });
    const group = el.shadowRoot!.querySelector('g.blind-group') as SVGGElement | null;
    expect(group).not.toBeNull();
    expect(group!.getAttribute('style') ?? '').toContain('display: none');
    const blind = el.shadowRoot!.querySelector('path.blind-spot') as SVGPathElement | null;
    expect(blind!.getAttribute('d') ?? '').toBe('');
  });
});

describe('acp-sky-compass legend toggle', () => {
  function makeTwoEntry() {
    const d1 = makeDiscovered('entry1', 'Kitchen');
    const d2 = makeDiscovered('entry2', 'Living');
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180 },
      { entryId: 'entry2', windowAzimuth: 90 },
    ]);
    return { d1, d2, hass };
  }

  it('multi-entry legend rows are toggle buttons with aria-pressed="true" initially', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    const buttons = el.shadowRoot!.querySelectorAll('button.entry-toggle');
    expect(buttons.length).toBe(2);
    buttons.forEach((btn) => expect(btn.getAttribute('aria-pressed')).toBe('true'));
  });

  it('clicking a row hides that entry overlay and sets aria-pressed="false"', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(2);
    const btn = el.shadowRoot!.querySelector('button.entry-toggle') as HTMLButtonElement;
    btn.click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(1);
    expect(btn.getAttribute('aria-pressed')).toBe('false');
  });

  it('clicking a row twice restores the overlay and aria-pressed="true"', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    const btn = el.shadowRoot!.querySelector('button.entry-toggle') as HTMLButtonElement;
    btn.click();
    await el.updateComplete;
    btn.click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(2);
    expect(btn.getAttribute('aria-pressed')).toBe('true');
  });

  it('hidden row still present in legend with .hidden class', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    const btn = el.shadowRoot!.querySelector('button.entry-toggle') as HTMLButtonElement;
    btn.click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('button.entry-toggle').length).toBe(2);
    expect(btn.classList.contains('hidden')).toBe(true);
  });

  it('hiding an entry does not affect stats panel', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    const btn = el.shadowRoot!.querySelector('button.entry-toggle') as HTMLButtonElement;
    btn.click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('button.entry-toggle').length).toBe(2);
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(1);
    expect(btn.classList.contains('hidden')).toBe(true);
  });

  it('hidden state survives unrelated hass updates', async () => {
    const { d1, d2, hass } = makeTwoEntry();
    const el = await mountCompass([d1, d2], hass);
    const btn = el.shadowRoot!.querySelector('button.entry-toggle') as HTMLButtonElement;
    btn.click();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(1);
    (el as SkyCompassLike).hass = { ...hass };
    await el.updateComplete;
    expect(el.shadowRoot!.querySelectorAll('path.fov').length).toBe(1);
  });
});

describe('acp-sky-compass visual toggles', () => {
  const d = () => makeDiscovered('entry1', 'Kitchen');
  const hass = () => makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);

  it('showLegend=false hides legend block', async () => {
    const el = await mountCompass([d()], hass(), { showLegend: false });
    expect(el.shadowRoot!.querySelector('.legend')).toBeNull();
  });

  it('showStats=false hides stats block', async () => {
    const el = await mountCompass([d()], hass(), { showStats: false });
    expect(el.shadowRoot!.querySelector('.stats')).toBeNull();
  });

  it('showCardinals=false hides cardinal labels', async () => {
    const el = await mountCompass([d()], hass(), { showCardinals: false });
    expect(el.shadowRoot!.querySelector('text.cardinal')).toBeNull();
  });

  it('showWindowArrow=false hides arrow group', async () => {
    const el = await mountCompass([d()], hass(), { showWindowArrow: false });
    const group = el.shadowRoot!.querySelector('g.arrow-group') as SVGGElement | null;
    expect(group).not.toBeNull();
    expect(group!.getAttribute('style') ?? '').toContain('display: none');
  });

  it('showSunPath=false hides the sun path', async () => {
    const el = await mountCompass([d()], hass(), { showSunPath: false });
    expect(el.shadowRoot!.querySelector('polyline.sun-path-line')).toBeNull();
  });

  // The sun path is one polyline per above-horizon run; the gold→grey fade
  // lives in a per-run <linearGradient> referenced by the polyline stroke.
  const sunPathLines = (el: SkyCompassLike): SVGPolylineElement[] =>
    Array.from(el.shadowRoot!.querySelectorAll('polyline.sun-path-line')) as SVGPolylineElement[];
  const linePoints = (l: SVGPolylineElement): Array<{ x: number; y: number }> =>
    (l.getAttribute('points') ?? '')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((pair) => {
        const [x, y] = pair.split(',').map(Number);
        return { x, y };
      });
  const allPathMags = (el: SkyCompassLike): number[] =>
    sunPathLines(el)
      .flatMap(linePoints)
      .map((p) => Math.hypot(p.x, p.y));
  const stopRgb = (s: Element): RegExpMatchArray | null =>
    (s.getAttribute('stop-color') ?? '').match(/rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/);

  it('sun-path masks the below-horizon trajectory (daytime arc only)', async () => {
    const el = await mountCompass([d()], hass());
    expect(sunPathLines(el).length).toBeGreaterThanOrEqual(1);
    const OUTER_R = 110;
    const mags = allPathMags(el);
    expect(mags.length).toBeGreaterThan(0);
    expect(Math.min(...mags)).toBeLessThan(OUTER_R * 0.9);
    for (const m of mags) {
      expect(m).toBeLessThanOrEqual(OUTER_R + 0.5);
    }
    const onRim = mags.filter((m) => Math.abs(m - OUTER_R) < 0.5);
    expect(onRim.length).toBeLessThanOrEqual(4);
  });

  it('showSunriseSunset=true ramps the arc grey (horizon) → gold (zenith) by elevation', async () => {
    const el = await mountCompass([d()], hass(), { showSunriseSunset: true });
    const lines = sunPathLines(el);
    expect(lines.length).toBeGreaterThanOrEqual(1);
    const idMatch = (lines[0].getAttribute('style') ?? '').match(/url\(#(sun-path-grad-\d+)\)/);
    expect(idMatch).not.toBeNull();
    const stops = Array.from(el.shadowRoot!.querySelectorAll(`linearGradient#${idMatch![1]} stop`));
    expect(stops.length).toBeGreaterThanOrEqual(3);
    const goldness = stops.map((s) => {
      const m = stopRgb(s)!;
      return Number(m[1]) - Number(m[3]);
    });
    const maxGold = Math.max(...goldness);
    const maxIdx = goldness.indexOf(maxGold);
    expect(maxIdx).toBeGreaterThan(0);
    expect(maxIdx).toBeLessThan(goldness.length - 1);
    expect(maxGold).toBeGreaterThan(goldness[0]);
    expect(maxGold).toBeGreaterThan(goldness[goldness.length - 1]);
    expect(maxGold).toBeGreaterThan(150);
    expect(Math.abs(goldness[0])).toBeLessThan(80);
    expect(Math.abs(goldness[goldness.length - 1])).toBeLessThan(80);
  });

  it('showSunriseSunset=false draws the arc in a single colour', async () => {
    const el = await mountCompass([d()], hass(), { showSunriseSunset: false });
    const lines = sunPathLines(el);
    expect(lines.length).toBeGreaterThan(0);
    expect(el.shadowRoot!.querySelector('linearGradient[id^="sun-path-grad"]')).toBeNull();
    const strokes = new Set(lines.map((l) => (l.getAttribute('style') ?? '').trim()));
    expect(strokes.size).toBe(1);
    expect([...strokes][0]).toContain('--warning-color');
  });
});

describe('acp-sky-compass FOV elevation limits', () => {
  // windowAzimuth=180, fov_left=45, fov_right=45 → fovStart=135, fovEnd=225
  const d = () => makeDiscovered('entry1', 'Kitchen');

  it('no elevation limits → full pie path (baseline)', async () => {
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d()], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    expect(el.shadowRoot!.querySelector('path.fov')?.getAttribute('d')).toBe(expected);
  });

  it('min_elevation clips outer radius (horizon side)', async () => {
    const { fovBandRadii } = await import('../src/lib/geometry');
    // omitLocation: no sun samples → azimuth gating falls back to the full FOV
    // envelope; this test focuses on the radial clipping behavior only.
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, minElevation: 10 }], {
      omitLocation: true,
    });
    const el = await mountCompass([d()], hass);
    const { outer } = fovBandRadii(10, undefined, 110);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), outer, 0, 0);
    const actual = el.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
    expect(actual).toBe(expected);
    expect(actual).not.toBe(wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0));
  });

  it('max_elevation clips inner radius (donut)', async () => {
    const { fovBandRadii } = await import('../src/lib/geometry');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, maxElevation: 60 }]);
    const el = await mountCompass([d()], hass);
    const { inner } = fovBandRadii(undefined, 60, 110);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, inner, 0);
    const actual = el.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
    expect(actual).toBe(expected);
    expect(actual).not.toMatch(/^M 0 0/);
  });

  it('both limits → annular sector', async () => {
    const { fovBandRadii } = await import('../src/lib/geometry');
    const hass = makeHass(
      [{ entryId: 'entry1', windowAzimuth: 180, minElevation: 10, maxElevation: 60 }],
      { omitLocation: true },
    );
    const el = await mountCompass([d()], hass);
    const { outer, inner } = fovBandRadii(10, 60, 110);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), outer, inner, 0);
    expect(el.shadowRoot!.querySelector('path.fov')?.getAttribute('d')).toBe(expected);
  });

  it('inverted limits (min > max) → full pie fallback', async () => {
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, minElevation: 70, maxElevation: 30 },
    ]);
    const el = await mountCompass([d()], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    expect(el.shadowRoot!.querySelector('path.fov')?.getAttribute('d')).toBe(expected);
  });

  it('cover-fill outer is clamped to fovOuterR when rawCoverR exceeds it', async () => {
    const { fovBandRadii } = await import('../src/lib/geometry');
    const disc = makeDiscovered('entry1', 'Kitchen');
    // coverPos=5 (5% closed) → rawCoverR = 110 * (1 - 5/100) = 104.5
    // minElevation=10 → fovOuterR ≈ 97.78 (104.5 > 97.78, so clamp applies)
    const hass = makeHass(
      [{ entryId: 'entry1', windowAzimuth: 180, minElevation: 10, coverPos: 5 }],
      { omitLocation: true },
    );
    const el = await mountCompass([disc], hass);
    const { outer: fovOuter } = fovBandRadii(10, undefined, 110);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), fovOuter, 0, 0);
    const coverFill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    expect(coverFill).not.toBeNull();
    expect(coverFill!.getAttribute('d')).toBe(expected);
  });

  it('tooltip includes elevation band when at least one limit is set', async () => {
    const hass = makeHass([
      { entryId: 'entry1', windowAzimuth: 180, minElevation: 10, maxElevation: 60 },
    ]);
    const el = await mountCompass([d()], hass);
    const fovGroup = el.shadowRoot!.querySelector('path.fov')?.parentElement;
    const titleText = fovGroup?.getAttribute('data-tooltip') ?? '';
    expect(titleText).toContain('10');
    expect(titleText).toContain('60');
  });

  it('tooltip has no elevation suffix when no limits are set', async () => {
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d()], hass);
    const fovGroup = el.shadowRoot!.querySelector('path.fov')?.parentElement;
    const titleText = fovGroup?.getAttribute('data-tooltip') ?? '';
    expect(titleText).not.toContain('elev');
  });
});

describe('acp-sky-compass static FOV envelope (start/end sensors carry no azimuth)', () => {
  // The integration's Start/End Sun sensors are plain datetimes. Without an
  // `azimuth` attribute the active-arc clamp never engages, so the wedge is
  // always the configured windowAzi ± fov envelope and the dimmed static
  // underlay (drawn only beneath a clipped active arc) never renders.
  it('renders the full configured envelope when start/end sensors are present', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withStartEnd: true });
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, withStartEnd: true }]);
    const el = await mountCompass([d], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    expect(el.shadowRoot!.querySelector('path.fov')?.getAttribute('d')).toBe(expected);
  });

  it('never renders the static-FOV underlay', async () => {
    const d = makeDiscovered('entry1', 'Kitchen', { withStartEnd: true });
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, withStartEnd: true }]);
    const el = await mountCompass([d], hass);
    expect(el.shadowRoot!.querySelector('path.fov.fov-static')).toBeNull();
  });

  it('narrows the static wedge azimuths to the elevation-cleared sun path when min_elevation is set', async () => {
    // With a location + min_elevation the static path is azimuth-gated by
    // today's sampled sun track (elevationGatedFovBounds). Pin the clock so the
    // sampled day is deterministic, then replicate the component's math.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-21T18:00:00Z'));
    try {
      const { elevationGatedFovBounds, fovBandRadii } = await import('../src/lib/geometry');
      const { sampleDay, startOfDayInZone } = await import('../src/lib/sun-model');
      const d = makeDiscovered('entry1', 'Kitchen');
      const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180, minElevation: 10 }]);
      const el = await mountCompass([d], hass);
      const samples = sampleDay(47.6, -122.3, startOfDayInZone('America/Los_Angeles'));
      const gated = elevationGatedFovBounds(samples, 180, 45, 45, 10);
      expect(gated).not.toBeNull();
      const { outer } = fovBandRadii(10, undefined, 110);
      const expected = wedgePath(
        normalizeAzimuth(gated!.wedgeStart),
        normalizeAzimuth(gated!.wedgeEnd),
        outer,
        0,
        0,
      );
      const actual = el.shadowRoot!.querySelector('path.fov')?.getAttribute('d') ?? '';
      expect(actual).toBe(expected);
      // And it genuinely differs from the ungated full envelope.
      expect(actual).not.toBe(wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), outer, 0, 0));
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('acp-sky-compass cover-fill polarity by cover_type', () => {
  // windowAzimuth=180, fov ±45 → full FOV wedge = wedgePath(135, 225, 110, 0, 0)

  it('cover_awning at position=100 fills the full FOV wedge', async () => {
    const disc = makeDiscovered('awning1', 'Awning', { coverType: 'cover_awning' });
    const hass = makeHass([{ entryId: 'awning1', windowAzimuth: 180, coverPos: 100 }]);
    const el = await mountCompass([disc], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    const coverFill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    const coverGroup = el.shadowRoot!.querySelector('g.cover-group') as SVGGElement | null;
    expect(coverFill).not.toBeNull();
    expect(coverFill!.getAttribute('d')).toBe(expected);
    expect(coverGroup!.getAttribute('style') ?? '').not.toContain('display: none');
  });

  it('cover_awning at position=0 hides cover-fill', async () => {
    const disc = makeDiscovered('awning2', 'Awning', { coverType: 'cover_awning' });
    const hass = makeHass([{ entryId: 'awning2', windowAzimuth: 180, coverPos: 0 }]);
    const el = await mountCompass([disc], hass);
    const coverGroup = el.shadowRoot!.querySelector('g.cover-group') as SVGGElement | null;
    expect(coverGroup!.getAttribute('style') ?? '').toContain('display: none');
  });

  it('cover_awning at 50 and cover_blind at 50 produce the same cover-fill path', async () => {
    const discAwning = makeDiscovered('awning3', 'Awning', { coverType: 'cover_awning' });
    const elAwning = await mountCompass(
      [discAwning],
      makeHass([{ entryId: 'awning3', windowAzimuth: 180, coverPos: 50 }]),
    );

    const discBlind = makeDiscovered('blind3', 'Blind', { coverType: 'cover_blind' });
    const elBlind = await mountCompass(
      [discBlind],
      makeHass([{ entryId: 'blind3', windowAzimuth: 180, coverPos: 50 }]),
    );

    // Both use coverFraction=0.5 → rawCoverR = 55 → wedgePath(135, 225, 55, 0, 0)
    const expectedD = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 55, 0, 0);
    const awningD = elAwning.shadowRoot!.querySelector('path.cover-fill')?.getAttribute('d') ?? '';
    const blindD = elBlind.shadowRoot!.querySelector('path.cover-fill')?.getAttribute('d') ?? '';
    expect(awningD).toBe(expectedD);
    expect(blindD).toBe(expectedD);
  });

  it('cover_blind at position=0 fills the full FOV wedge (regression)', async () => {
    const disc = makeDiscovered('blind4', 'Blind', { coverType: 'cover_blind' });
    const hass = makeHass([{ entryId: 'blind4', windowAzimuth: 180, coverPos: 0 }]);
    const el = await mountCompass([disc], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    const coverFill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    const coverGroup = el.shadowRoot!.querySelector('g.cover-group') as SVGGElement | null;
    expect(coverFill).not.toBeNull();
    expect(coverFill!.getAttribute('d')).toBe(expected);
    expect(coverGroup!.getAttribute('style') ?? '').not.toContain('display: none');
  });

  it('cover_blind at position=100 hides cover-fill (regression)', async () => {
    const disc = makeDiscovered('blind5', 'Blind', { coverType: 'cover_blind' });
    const hass = makeHass([{ entryId: 'blind5', windowAzimuth: 180, coverPos: 100 }]);
    const el = await mountCompass([disc], hass);
    const coverGroup = el.shadowRoot!.querySelector('g.cover-group') as SVGGElement | null;
    expect(coverGroup!.getAttribute('style') ?? '').toContain('display: none');
  });

  it('cover_tilt at position=0 fills the full FOV wedge (same semantics as blind)', async () => {
    const disc = makeDiscovered('tilt6', 'Tilt', { coverType: 'cover_tilt' });
    const hass = makeHass([{ entryId: 'tilt6', windowAzimuth: 180, coverPos: 0 }]);
    const el = await mountCompass([disc], hass);
    const expected = wedgePath(normalizeAzimuth(135), normalizeAzimuth(225), 110, 0, 0);
    const coverFill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    expect(coverFill).not.toBeNull();
    expect(coverFill!.getAttribute('d')).toBe(expected);
  });

  it('tooltip: cover_awning target line uses "extended", cover_blind uses plain target', async () => {
    const discAwning = makeDiscovered('awning7', 'Awning', { coverType: 'cover_awning' });
    const elAwning = await mountCompass(
      [discAwning],
      makeHass([{ entryId: 'awning7', windowAzimuth: 180, coverPos: 75 }]),
    );
    const awningTitle =
      elAwning.shadowRoot!.querySelector('g.cover-group')?.getAttribute('data-tooltip') ?? '';
    expect(awningTitle).toContain('Target (extended): 75%');

    const discBlind = makeDiscovered('blind7', 'Blind', { coverType: 'cover_blind' });
    const elBlind = await mountCompass(
      [discBlind],
      makeHass([{ entryId: 'blind7', windowAzimuth: 180, coverPos: 75 }]),
    );
    const blindTitle =
      elBlind.shadowRoot!.querySelector('g.cover-group')?.getAttribute('data-tooltip') ?? '';
    expect(blindTitle).toContain('Target: 75%');
    expect(blindTitle).not.toContain('extended');
  });
});

describe('acp-sky-compass cover tooltip target + actual lines (#132, live covers)', () => {
  const disc = (covers: string[]) => makeDiscovered('tt', 'Kitchen', { managedCovers: covers });

  it('appends an Actual line when a live cover aggregate exists', async () => {
    const hass = makeHass([
      { entryId: 'tt', windowAzimuth: 180, coverPos: 30, covers: { 'cover.x': 80 } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    const tt = el.shadowRoot!.querySelector('g.cover-group')?.getAttribute('data-tooltip') ?? '';
    expect(tt).toContain('Target: 30%');
    expect(tt).toContain('Actual: 80%');
  });

  it('shows only the target line when no managed cover reports a position', async () => {
    const hass = makeHass([{ entryId: 'tt', windowAzimuth: 180, coverPos: 30 }]);
    const el = await mountCompass([disc([])], hass);
    const tt = el.shadowRoot!.querySelector('g.cover-group')?.getAttribute('data-tooltip') ?? '';
    expect(tt).toContain('Target: 30%');
    expect(tt).not.toContain('Actual');
  });

  it('averages multiple managed covers into the Actual line', async () => {
    const hass = makeHass([
      {
        entryId: 'tt',
        windowAzimuth: 180,
        coverPos: 30,
        covers: { 'cover.a': 60, 'cover.b': 80 },
      },
    ]);
    const el = await mountCompass([disc(['cover.a', 'cover.b'])], hass);
    const tt = el.shadowRoot!.querySelector('g.cover-group')?.getAttribute('data-tooltip') ?? '';
    expect(tt).toContain('Actual: 70%');
  });
});

describe('acp-sky-compass actual-vs-target dual wedge (#132, live covers)', () => {
  // windowAzimuth=180, fov ±45 → full FOV wedge. Target = sensor state; the
  // actual ring is read live from the managed covers' current_position.
  const disc = (covers: string[]) => makeDiscovered('dual', 'Kitchen', { managedCovers: covers });

  it('renders both cover-fill (target) and cover-actual when they diverge', async () => {
    const hass = makeHass([
      { entryId: 'dual', windowAzimuth: 180, coverPos: 30, covers: { 'cover.x': 80 } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    const fill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    const actual = el.shadowRoot!.querySelector('path.cover-actual') as SVGPathElement | null;
    expect(fill).not.toBeNull();
    expect(actual).not.toBeNull();
    expect(fill!.getAttribute('d')).not.toBe(actual!.getAttribute('d'));
  });

  it('cover-actual equals cover-fill when actual mean == target', async () => {
    const hass = makeHass([
      { entryId: 'dual', windowAzimuth: 180, coverPos: 30, covers: { 'cover.x': 30 } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    const fill = el.shadowRoot!.querySelector('path.cover-fill') as SVGPathElement | null;
    const actual = el.shadowRoot!.querySelector('path.cover-actual') as SVGPathElement | null;
    expect(actual).not.toBeNull();
    expect(actual!.getAttribute('d')).toBe(fill!.getAttribute('d'));
  });

  it('omits cover-actual when the entry has no managed covers', async () => {
    const hass = makeHass([{ entryId: 'dual', windowAzimuth: 180, coverPos: 30 }]);
    const el = await mountCompass([disc([])], hass);
    expect(el.shadowRoot!.querySelector('path.cover-actual')).toBeNull();
    expect(el.shadowRoot!.querySelector('path.cover-fill')).not.toBeNull();
  });

  it('omits cover-actual when no managed cover reports current_position', async () => {
    const hass = makeHass([
      { entryId: 'dual', windowAzimuth: 180, coverPos: 30, covers: { 'cover.x': null } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass);
    expect(el.shadowRoot!.querySelector('path.cover-actual')).toBeNull();
    expect(el.shadowRoot!.querySelector('path.cover-fill')).not.toBeNull();
  });

  it('does not render cover-actual when showCoverFill is off', async () => {
    const hass = makeHass([
      { entryId: 'dual', windowAzimuth: 180, coverPos: 30, covers: { 'cover.x': 80 } },
    ]);
    const el = await mountCompass([disc(['cover.x'])], hass, { showCoverFill: false });
    expect(el.shadowRoot!.querySelector('path.cover-actual')).toBeNull();
  });
});

describe('acp-sky-compass legend completeness & theme tokens', () => {
  // SkyCompass.styles is a Lit CSSResult; .cssText is plain text we can grep.
  const cssText = (SkyCompass as unknown as { styles: { cssText: string } }).styles.cssText;

  function cssBlock(selector: string): string {
    const idx = cssText.indexOf(selector);
    if (idx < 0) throw new Error(`Selector not found in styles: ${selector}`);
    const open = cssText.indexOf('{', idx);
    const close = cssText.indexOf('}', open);
    if (open < 0 || close < 0) throw new Error(`Malformed block for ${selector}`);
    return cssText.slice(open + 1, close);
  }

  it('legend renders a single Sun glyph carrying the live sun-dot class', async () => {
    // Default fixture (in_fov true, Sun Infront off) → in_fov_not_valid →
    // class "sun in-fov" (gold, no glow). Exactly one glyph circle.
    const d = makeDiscovered('entry1', 'Kitchen', { withSunInfront: true });
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    const dots = Array.from(el.shadowRoot!.querySelectorAll('.legend circle.sun'));
    expect(dots.length).toBe(1);
    expect(dots[0].classList.contains('in-fov')).toBe(true);
    expect(dots[0].classList.contains('valid')).toBe(false);
  });

  it('legend labels the single sun swatch "Sun"', async () => {
    const d = makeDiscovered('entry1', 'Kitchen');
    const hass = makeHass([{ entryId: 'entry1', windowAzimuth: 180 }]);
    const el = await mountCompass([d], hass);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Sun');
    expect(text).not.toContain('Sun (hitting window)');
    expect(text).not.toContain('Sun (below horizon)');
  });

  it('the FOV wedge default is the primary-color shade (off gold, so the sun dot reads)', () => {
    const fov = cssBlock('.fov,');
    expect(fov).toMatch(/var\(--primary-color/);
  });

  it('cover swatch opacity matches the FOV+cover composite the plot shows', () => {
    const swatch = cssBlock('.swatch.cover-fill-swatch ');
    expect(swatch).toMatch(/opacity:\s*0\.45/);
  });

  it('the legend sun glyph reuses the plot .sun.valid token + glow', () => {
    const circleValid = cssBlock('.sun.valid ');
    expect(circleValid).toMatch(/var\(--warning-color/);
    expect(circleValid).toMatch(/drop-shadow/);
  });

  it('the plot .sun.up token (inherited by the no-glow legend glyph) is a light neutral', () => {
    const sunUp = cssBlock('.sun.up ');
    expect(sunUp).toMatch(/#ffe680/);
  });

  it('plot-sizing rules are scoped to the direct-child plot svg, not every svg', () => {
    expect(cssText).toContain('.compass > svg {');
    const plot = cssBlock('.compass > svg ');
    expect(plot).toMatch(/width:\s*100%/);
    expect(cssText).not.toMatch(/(?:^|[\n;}])\s*svg\s*\{/m);
  });

  it('legend glyph SVGs neutralise any inherited svg sizing', () => {
    const glyph = cssBlock('.glyph svg ');
    expect(glyph).toMatch(/min-width:\s*0/);
    expect(glyph).toMatch(/max-width:\s*none/);
    expect(glyph).toMatch(/display:\s*block/);
  });

  it('does not pin a percentage max-height on the side-column legend (issue #146)', () => {
    const sideColumn = cssBlock('.compass .legend');
    expect(sideColumn).not.toMatch(/max-height:\s*100%/);
    expect(sideColumn).not.toMatch(/overflow-y:\s*auto/);
  });
});

describe('acp-sky-compass tooltip cursor lifecycle', () => {
  const cssText = (SkyCompass as unknown as { styles: { cssText: string } }).styles.cssText;

  it('hover shows a help cursor on tooltip carriers', () => {
    expect(cssText).toMatch(/\[data-tooltip\]:hover\s*{\s*cursor:\s*help/);
  });

  it('the shown state reverts the cursor to default', () => {
    expect(cssText).toMatch(/\[data-tooltip\]\[acp-tt-shown\]\s*{\s*cursor:\s*default/);
  });
});
