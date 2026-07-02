import { describe, it, expect, vi, afterEach } from 'vitest';
import '../src/components/elevation-chart';
import { ElevationChart } from '../src/components/elevation-chart';
import type { HomeAssistant } from 'custom-card-helpers';
import type { DiscoveredEntities, SunPositionAttributes } from '../src/types';

// NOTE (adaptive_cover port): the chart now reads its solar geometry from the
// `sun` attribute block on the Cover Position sensor (readSunAttrs) and the
// sun-dot validity from the "Sun Infront" binary sensor. The Pro-only
// decision_trace sensor (`sun_state` / `direct_sun_valid`) is gone, and the
// integration never emits `schedule_start` / `schedule_end` on the Control
// Method sensor, so the schedule-overlay describe blocks shrank to negative
// coverage (the overlay machinery is retained for a future attribute).

const VIEWBOX_H = 160;
const PAD_B = 22;

interface ChartLike extends HTMLElement {
  updateComplete: Promise<boolean>;
  hass?: HomeAssistant;
  discoveredList?: DiscoveredEntities[];
  coverColors?: (string | null | undefined)[];
  compact?: boolean;
}

const discovered: DiscoveredEntities = {
  entry_id: 'entry1',
  entry_title: 'Test',
  cover_type: 'cover_blind',
  entities: {
    target_position_sensor: 'sensor.cover_position',
    sun_infront_binary: 'binary_sensor.sun_infront',
  },
  managed_covers: [],
};

/** Base `sun` attribute block on the Cover Position sensor. */
function sunBlock(attrs: Partial<SunPositionAttributes>): SunPositionAttributes {
  return {
    azimuth: 180,
    elevation: 30,
    gamma: 0,
    window_azimuth: 180,
    fov_left: 90,
    fov_right: 90,
    in_fov: true,
    ...attrs,
  };
}

function hass(
  attrs: Partial<SunPositionAttributes>,
  opts: { sunInfront?: boolean } = {},
): HomeAssistant {
  return {
    config: { latitude: 52.0, longitude: 4.0, time_zone: 'UTC' },
    states: {
      'sensor.cover_position': {
        state: '30',
        attributes: { intent: 'calculated', sun: sunBlock(attrs) },
      },
      'binary_sensor.sun_infront': {
        state: opts.sunInfront ? 'on' : 'off',
        attributes: {},
      },
    },
  } as unknown as HomeAssistant;
}

async function mount(props: Partial<ChartLike>): Promise<ChartLike> {
  const el = document.createElement('acp-elevation-chart') as ChartLike;
  Object.assign(el, props);
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

function svgViewBoxHeight(el: ChartLike): number {
  const svg = el.shadowRoot!.querySelector('svg')!;
  const vb = svg.getAttribute('viewBox')!.split(/\s+/).map(Number);
  return vb[3];
}

describe('acp-elevation-chart: single-window (legacy, unchanged)', () => {
  it('draws two limit lines when both min_elevation and max_elevation are set', async () => {
    const el = await mount({
      hass: hass({ min_elevation: 10, max_elevation: 60 }),
      discoveredList: [discovered],
    });
    const lines = el.shadowRoot!.querySelectorAll('line.limit-line');
    expect(lines.length).toBe(2);
  });

  it('draws no limit lines when neither limit is set', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    const lines = el.shadowRoot!.querySelectorAll('line.limit-line');
    expect(lines.length).toBe(0);
  });

  it('draws one limit line when only min_elevation is set', async () => {
    const el = await mount({ hass: hass({ min_elevation: 10 }), discoveredList: [discovered] });
    const lines = el.shadowRoot!.querySelectorAll('line.limit-line');
    expect(lines.length).toBe(1);
  });

  it('clips the FOV band y-extent to the elevation band when limits are present', async () => {
    const clipped = await mount({
      hass: hass({ min_elevation: 10, max_elevation: 60 }),
      discoveredList: [discovered],
    });
    const full = await mount({ hass: hass({}), discoveredList: [discovered] });

    const clippedRect = clipped.shadowRoot!.querySelector('rect.fov-band');
    const fullRect = full.shadowRoot!.querySelector('rect.fov-band');
    expect(clippedRect).toBeTruthy();
    expect(fullRect).toBeTruthy();

    const clippedY = parseFloat(clippedRect!.getAttribute('y')!);
    const clippedH = parseFloat(clippedRect!.getAttribute('height')!);
    const fullY = parseFloat(fullRect!.getAttribute('y')!);
    const fullH = parseFloat(fullRect!.getAttribute('height')!);

    expect(clippedY).toBeGreaterThan(fullY);
    expect(clippedH).toBeLessThan(fullH);
  });

  it('renders full-height FOV bands (unchanged) when no limits are set', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    const rect = el.shadowRoot!.querySelector('rect.fov-band');
    expect(rect).toBeTruthy();
    // PAD_T = 10, VIEWBOX_H = 160, PAD_B = 22 → full height = 128, y = 10.
    expect(parseFloat(rect!.getAttribute('y')!)).toBeCloseTo(10);
    expect(parseFloat(rect!.getAttribute('height')!)).toBeCloseTo(128);
  });

  it('keeps the themed default fill (no inline style) for a single window', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    const rect = el.shadowRoot!.querySelector('rect.fov-band');
    expect(rect).toBeTruthy();
    const style = rect!.getAttribute('style') ?? '';
    expect(style).not.toMatch(/fill\s*:/);
  });

  it('renders NO ribbon bars or tracks for a single window', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    expect(el.shadowRoot!.querySelectorAll('rect.ribbon-bar').length).toBe(0);
    expect(el.shadowRoot!.querySelectorAll('rect.ribbon-track').length).toBe(0);
  });

  it('keeps viewBox height 160 and no inline aspect-ratio for a single window', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    expect(svgViewBoxHeight(el)).toBe(160);
    const style = el.shadowRoot!.querySelector('svg')!.getAttribute('style') ?? '';
    expect(style).not.toMatch(/aspect-ratio/);
  });

  it('now-cursor y2 ends at the plot bottom for a single window', async () => {
    const el = await mount({ hass: hass({}), discoveredList: [discovered] });
    const now = el.shadowRoot!.querySelector('line.now')!;
    expect(parseFloat(now.getAttribute('y2')!)).toBeCloseTo(VIEWBOX_H - PAD_B);
  });

  it('shows the placeholder when the Cover Position sensor has no sun block', async () => {
    const h = {
      config: { latitude: 52.0, longitude: 4.0, time_zone: 'UTC' },
      states: {
        'sensor.cover_position': { state: '30', attributes: { intent: 'default' } },
      },
    } as unknown as HomeAssistant;
    const el = await mount({ hass: h, discoveredList: [discovered] });
    expect(el.shadowRoot!.textContent).toContain('Sun elevation chart unavailable.');
    expect(el.shadowRoot!.querySelector('polyline.curve')).toBeNull();
  });
});

const discoveredSouth: DiscoveredEntities = {
  entry_id: 'south',
  entry_title: 'Living Room',
  cover_type: 'cover_blind',
  entities: { target_position_sensor: 'sensor.pos_south' },
  managed_covers: [],
};
const discoveredWest: DiscoveredEntities = {
  entry_id: 'west',
  entry_title: 'Office',
  cover_type: 'cover_blind',
  entities: { target_position_sensor: 'sensor.pos_west' },
  managed_covers: [],
};
const discoveredEast: DiscoveredEntities = {
  entry_id: 'east',
  entry_title: 'Bedroom',
  cover_type: 'cover_blind',
  entities: { target_position_sensor: 'sensor.pos_east' },
  managed_covers: [],
};

function multiHass(states: Record<string, Partial<SunPositionAttributes>>): HomeAssistant {
  const built: Record<string, unknown> = {};
  for (const [id, attrs] of Object.entries(states)) {
    built[id] = { state: '30', attributes: { sun: sunBlock(attrs) } };
  }
  return {
    config: { latitude: 52.0, longitude: 4.0, time_zone: 'UTC' },
    states: built,
  } as unknown as HomeAssistant;
}

function twoWindowHass(): HomeAssistant {
  return multiHass({
    'sensor.pos_south': { window_azimuth: 180 },
    'sensor.pos_west': { window_azimuth: 270 },
  });
}

function ribbonRanges(el: ChartLike, fill: string) {
  return Array.from(el.shadowRoot!.querySelectorAll('rect.ribbon-bar'))
    .filter((r) => (r.getAttribute('style') ?? '').includes(fill))
    .map((r) => {
      const y = parseFloat(r.getAttribute('y')!);
      const h = parseFloat(r.getAttribute('height')!);
      return { top: y, bottom: y + h };
    });
}

describe('acp-elevation-chart: multi-window ribbon', () => {
  it('renders a ribbon (bars) and NO in-plot fov-band rects', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const bars = el.shadowRoot!.querySelectorAll('rect.ribbon-bar');
    expect(bars.length).toBeGreaterThanOrEqual(2);
    expect(el.shadowRoot!.querySelectorAll('rect.fov-band').length).toBe(0);
  });

  it('color-keys each window bar with an inline fill', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const fills = Array.from(el.shadowRoot!.querySelectorAll('rect.ribbon-bar')).map(
      (r) => r.getAttribute('style') ?? '',
    );
    expect(fills.some((s) => s.includes('#ff7043'))).toBe(true);
    expect(fills.some((s) => s.includes('#7e57c2'))).toBe(true);
  });

  it('draws no per-window limit-lines in the plot for multi-window', async () => {
    const el = await mount({
      hass: multiHass({
        'sensor.pos_south': { window_azimuth: 180, min_elevation: 10, max_elevation: 60 },
        'sensor.pos_west': { window_azimuth: 270 },
      }),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    expect(el.shadowRoot!.querySelectorAll('line.limit-line').length).toBe(0);
  });

  it('renders a background track per window even when it has no FOV runs today', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    expect(el.shadowRoot!.querySelectorAll('rect.ribbon-track').length).toBe(2);
  });

  it('gives each ribbon bar a data-tooltip with the window name and FOV time range', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const bars = el.shadowRoot!.querySelectorAll('rect.ribbon-bar');
    expect(bars.length).toBeGreaterThan(0);
    const titles = Array.from(bars).map((b) => b.getAttribute('data-tooltip') ?? '');
    expect(titles.every((tx) => tx.length > 0)).toBe(true);
    expect(titles.some((tx) => tx.includes('Living Room') && tx.includes('→'))).toBe(true);
    expect(titles.some((tx) => tx.includes('Office') && tx.includes('→'))).toBe(true);
  });

  it('labels each ribbon track with its window name for empty-row identification', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const trackTitles = Array.from(el.shadowRoot!.querySelectorAll('rect.ribbon-track')).map(
      (r) => r.getAttribute('data-tooltip') ?? '',
    );
    expect(trackTitles.some((tx) => tx.includes('Living Room'))).toBe(true);
    expect(trackTitles.some((tx) => tx.includes('Office'))).toBe(true);
  });

  it('stacks window rows disjoint and ordered, inside the plot grid', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const south = ribbonRanges(el, '#ff7043');
    const west = ribbonRanges(el, '#7e57c2');
    expect(south.length).toBeGreaterThan(0);
    expect(west.length).toBeGreaterThan(0);
    const southBottom = Math.max(...south.map((r) => r.bottom));
    const westTop = Math.min(...west.map((r) => r.top));
    expect(southBottom).toBeLessThanOrEqual(westTop + 0.01);
    const axisY = VIEWBOX_H - PAD_B;
    const allTops = [...south, ...west].map((r) => r.top);
    const allBottoms = [...south, ...west].map((r) => r.bottom);
    expect(Math.max(...allBottoms)).toBeLessThanOrEqual(axisY + 0.01);
    expect(Math.min(...allTops)).toBeGreaterThan(axisY / 2);
  });

  it('keeps the viewBox height fixed at 160 with no inline aspect-ratio, any window count', async () => {
    const two = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const three = await mount({
      hass: multiHass({
        'sensor.pos_south': { window_azimuth: 180 },
        'sensor.pos_west': { window_azimuth: 270 },
        'sensor.pos_east': { window_azimuth: 90 },
      }),
      discoveredList: [discoveredSouth, discoveredWest, discoveredEast],
      coverColors: ['#ff7043', '#7e57c2', '#26a69a'],
    });
    expect(svgViewBoxHeight(two)).toBe(160);
    expect(svgViewBoxHeight(three)).toBe(160);
    const style = two.shadowRoot!.querySelector('svg')!.getAttribute('style') ?? '';
    expect(style).not.toMatch(/aspect-ratio/);
  });

  it('ends the now-cursor at the time axis in multi mode (ribbon is in-plot)', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const now = el.shadowRoot!.querySelector('line.now')!;
    expect(parseFloat(now.getAttribute('y2')!)).toBeCloseTo(VIEWBOX_H - PAD_B);
  });

  it('renders NO per-window legend in the head (the compass legend covers it)', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    const head = el.shadowRoot!.querySelector('.head')!;
    expect(head.querySelector('.fov-list')).toBeNull();
    expect(head.querySelector('.swatch')).toBeNull();
    expect(head.textContent ?? '').not.toContain('Living Room');
    expect(head.textContent ?? '').not.toContain('Office');
  });

  it('anchors the ribbon band to the bottom of the plot, just above the time axis', async () => {
    const el = await mount({
      hass: twoWindowHass(),
      discoveredList: [discoveredSouth, discoveredWest],
      coverColors: ['#ff7043', '#7e57c2'],
    });
    expect(svgViewBoxHeight(el)).toBe(160);
    const axisY = VIEWBOX_H - PAD_B;
    const trackBottoms = Array.from(el.shadowRoot!.querySelectorAll('rect.ribbon-track')).map(
      (r) => parseFloat(r.getAttribute('y')!) + parseFloat(r.getAttribute('height')!),
    );
    const lowest = Math.max(...trackBottoms);
    expect(lowest).toBeLessThanOrEqual(axisY + 0.01);
    expect(axisY - lowest).toBeLessThanOrEqual(8);
  });
});

// NOTE: the positive schedule-overlay tests (issue #128: off-schedule zones,
// start/end bars, tick labels, head summary, edge anchoring) were dropped —
// the Adaptive Cover integration never emits `schedule_start`/`schedule_end`
// on the Control Method sensor, so the overlay can never render. The negative
// coverage below locks that in.
describe('acp-elevation-chart: schedule overlay (never rendered by this integration)', () => {
  const discoveredWithControl: DiscoveredEntities = {
    entry_id: 'entry1',
    entry_title: 'Test',
    cover_type: 'cover_blind',
    entities: {
      target_position_sensor: 'sensor.cover_position',
      control_status_sensor: 'sensor.control_method',
    },
    managed_covers: [],
  };

  function controlHass(controlAttrs: Record<string, unknown> | null): HomeAssistant {
    const h = hass({});
    if (controlAttrs !== null) {
      (h.states as Record<string, unknown>)['sensor.control_method'] = {
        state: 'summer',
        attributes: controlAttrs,
      };
    }
    return h;
  }

  it('renders nothing schedule-related when the Control Method sensor is absent', async () => {
    const el = await mount({
      hass: controlHass(null),
      discoveredList: [discovered], // no control_status_sensor on this entry
    });
    expect(el.shadowRoot!.querySelectorAll('rect.off-schedule-zone').length).toBe(0);
    expect(el.shadowRoot!.querySelectorAll('line.schedule-bar').length).toBe(0);
    expect(el.shadowRoot!.querySelector('polyline.curve')).toBeTruthy();
  });

  it('renders nothing schedule-related for the integration-shaped sensor (no schedule attrs)', async () => {
    // The real Control Method sensor carries no schedule_start/schedule_end.
    const el = await mount({
      hass: controlHass({}),
      discoveredList: [discoveredWithControl],
    });
    expect(el.shadowRoot!.querySelectorAll('rect.off-schedule-zone').length).toBe(0);
    expect(el.shadowRoot!.querySelectorAll('line.schedule-bar').length).toBe(0);
    expect(el.shadowRoot!.querySelector('.head')!.textContent ?? '').not.toContain('Schedule');
    expect(el.shadowRoot!.querySelector('polyline.curve')).toBeTruthy();
  });

  it('renders nothing schedule-related when both bounds are explicitly null', async () => {
    const el = await mount({
      hass: controlHass({ schedule_start: null, schedule_end: null }),
      discoveredList: [discoveredWithControl],
    });
    expect(el.shadowRoot!.querySelectorAll('rect.off-schedule-zone').length).toBe(0);
    expect(el.shadowRoot!.querySelectorAll('line.schedule-bar').length).toBe(0);
    expect(el.shadowRoot!.querySelector('polyline.curve')).toBeTruthy();
  });
});

describe('acp-elevation-chart: sun-dot 3-way state (Sun Infront binary)', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  // Pin `now` to local noon at the equator so the interpolated sun sample is
  // reliably above the horizon and the sun-dot renders deterministically.
  function dayHass(opts: { sunInfront?: boolean; inFov?: boolean }): HomeAssistant {
    const now = new Date();
    vi.setSystemTime(
      new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 12, 0, 0)),
    );
    return {
      config: { latitude: 0, longitude: 0, time_zone: 'UTC' },
      states: {
        'sensor.cover_position': {
          state: '80',
          attributes: {
            sun: sunBlock({ elevation: 80, in_fov: opts.inFov ?? true }),
          },
        },
        'binary_sensor.sun_infront': {
          state: opts.sunInfront ? 'on' : 'off',
          attributes: {},
        },
      },
    } as unknown as HomeAssistant;
  }

  it('renders sun-dot "valid" when the Sun Infront binary is on', async () => {
    const el = await mount({
      hass: dayHass({ sunInfront: true, inFov: true }),
      discoveredList: [discovered],
    });
    const dot = el.shadowRoot!.querySelector('circle.sun-dot') as SVGCircleElement;
    expect(dot).toBeTruthy();
    expect(dot.classList.contains('valid')).toBe(true);
    expect(dot.classList.contains('in-fov')).toBe(false);
  });

  it('renders sun-dot "in-fov" when in FOV but the binary is off', async () => {
    const el = await mount({
      hass: dayHass({ sunInfront: false, inFov: true }),
      discoveredList: [discovered],
    });
    const dot = el.shadowRoot!.querySelector('circle.sun-dot') as SVGCircleElement;
    expect(dot).toBeTruthy();
    expect(dot.classList.contains('in-fov')).toBe(true);
    expect(dot.classList.contains('valid')).toBe(false);
    expect(dot.classList.contains('up')).toBe(false);
  });

  it('renders sun-dot "up" when outside FOV', async () => {
    const el = await mount({
      hass: dayHass({ sunInfront: false, inFov: false }),
      discoveredList: [discovered],
    });
    const dot = el.shadowRoot!.querySelector('circle.sun-dot') as SVGCircleElement;
    expect(dot).toBeTruthy();
    expect(dot.classList.contains('up')).toBe(true);
    expect(dot.classList.contains('in-fov')).toBe(false);
  });

  it('treats a missing Sun Infront binary as not-valid (falls back to in-fov)', async () => {
    const h = dayHass({ inFov: true });
    delete (h.states as Record<string, unknown>)['binary_sensor.sun_infront'];
    const el = await mount({ hass: h, discoveredList: [discovered] });
    const dot = el.shadowRoot!.querySelector('circle.sun-dot') as SVGCircleElement;
    expect(dot).toBeTruthy();
    expect(dot.classList.contains('in-fov')).toBe(true);
    expect(dot.classList.contains('valid')).toBe(false);
  });

  it('exposes a .sun-dot.in-fov gold CSS rule', () => {
    const cssText = (ElevationChart as unknown as { styles: { cssText: string } }).styles.cssText;
    const idx = cssText.indexOf('.sun-dot.in-fov');
    expect(idx).toBeGreaterThan(-1);
    const block = cssText.slice(cssText.indexOf('{', idx), cssText.indexOf('}', idx));
    expect(block).toContain('var(--warning-color, gold)');
  });
});

describe('acp-elevation-chart: width-respect styles (issue #146)', () => {
  const cssText = (ElevationChart as unknown as { styles: { cssText: string } }).styles.cssText;

  function cssBlock(selector: string): string {
    const idx = cssText.indexOf(selector);
    if (idx < 0) throw new Error(`Selector not found in styles: ${selector}`);
    const open = cssText.indexOf('{', idx);
    const close = cssText.indexOf('}', open);
    if (open < 0 || close < 0) throw new Error(`Malformed block for ${selector}`);
    return cssText.slice(open + 1, close);
  }

  it('lets the flex wrap shrink to the card width (min-width: 0)', () => {
    expect(cssBlock('.wrap')).toMatch(/min-width:\s*0/);
  });

  it('makes :host full-width and shrinkable so the chart cannot push past the card', () => {
    const host = cssBlock(':host');
    expect(host).toMatch(/width:\s*100%/);
    expect(host).toMatch(/min-width:\s*0/);
  });
});

describe('acp-elevation-chart: now-line minute timer', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('requests a re-render every minute while connected and stops on disconnect', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-13T10:00:00.000Z')); // on a boundary → first tick at +60s
    const el = document.createElement('acp-elevation-chart') as ChartLike;
    Object.assign(el, { hass: hass({}), discoveredList: [discovered] });
    document.body.appendChild(el);

    const spy = vi.spyOn(el as unknown as { requestUpdate: () => void }, 'requestUpdate');
    vi.advanceTimersByTime(60_000);
    expect(spy).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(120_000);
    expect(spy).toHaveBeenCalledTimes(3);

    el.remove();
    spy.mockClear();
    vi.advanceTimersByTime(180_000);
    expect(spy).not.toHaveBeenCalled(); // interval cleared on disconnect
  });
});
