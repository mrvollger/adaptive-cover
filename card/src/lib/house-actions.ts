import type { HomeAssistant } from 'custom-card-helpers';

import { INTEGRATION_DOMAIN } from '../const';
import type { CoverPositionAttributes } from '../types';
import type { GroupMode, HouseHub, HouseWindow, WindowMode } from './house-model';
import { liveCoverPosition } from './trace-adapter';

/*
 * Mode mapping and service calls for the house card.
 *
 * Since the P5 flip each window has a Mode select with the options
 * auto / hold / off, and the house select has auto / hold / off / mixed:
 *
 * - The window's mode is its Mode select's state. A hold's end is the
 *   select's `until` attribute (else the Manual override sensor's).
 * - Off:  select.select_option → off.
 * - Auto: select.select_option → auto. It turns control back on and ends a
 *         hold (the shade goes back to its automatic position).
 * - Hold: adaptive_cover.hold, an entity service on the Mode selects: one
 *         call with every target select, optionally with a `duration`
 *         (default: each window's manual-override time). The house Hold is
 *         the house select's hold option.
 *
 * Older surfaces (before P5) are still read: a "Manual" select option or an
 * Automatic control switch that is off is Off, a latched Manual override is
 * Hold. There Auto selects the window's automatic option ("Sun + climate"
 * when its Climate mode switch is on, else "Sun tracking") for Off windows,
 * then presses Return to auto; there is no Hold.
 *
 * Group actions send one service call per (service, option), with every
 * target entity in one `entity_id` list, never one call per window.
 */

export interface ServiceCall {
  domain: string;
  service: string;
  data: Record<string, unknown>;
}

const OFF_OPTION = /^(manual|off)$/i;
const HOLD_OPTION = /^hold$/i;
const AUTO_OPTION = /^(auto|adaptive)$/i;
const CLIMATE_OPTION = /climate/i;

function stateOf(hass: HomeAssistant, id: string | undefined): string | undefined {
  return id ? hass.states[id]?.state : undefined;
}

/** The options of a select entity (empty when unknown). */
export function selectOptions(hass: HomeAssistant, id: string | undefined): string[] {
  const opts = id ? (hass.states[id]?.attributes?.options as unknown) : undefined;
  return Array.isArray(opts) ? opts.filter((o): o is string => typeof o === 'string') : [];
}

export function offOption(options: string[]): string | undefined {
  return options.find((o) => OFF_OPTION.test(o));
}

export function holdOption(options: string[]): string | undefined {
  return options.find((o) => HOLD_OPTION.test(o));
}

/**
 * The option that turns automatic control on. P5 selects have "auto"; today's
 * select has "Sun tracking" and, for climate windows, "Sun + climate".
 */
export function autoOption(options: string[], preferClimate: boolean): string | undefined {
  const explicit = options.find((o) => AUTO_OPTION.test(o));
  if (explicit) return explicit;
  const automatic = options.filter((o) => !OFF_OPTION.test(o) && !HOLD_OPTION.test(o));
  if (preferClimate) {
    const climate = automatic.find((o) => CLIMATE_OPTION.test(o));
    if (climate) return climate;
  }
  return automatic.find((o) => !CLIMATE_OPTION.test(o)) ?? automatic[0];
}

/** Whether Auto should pick the climate option: the window's Climate mode
 *  switch keeps its value while control is off, so it remembers the choice. */
function prefersClimate(hass: HomeAssistant, w: HouseWindow): boolean {
  const sw = stateOf(hass, w.entities.climateSwitch);
  return sw === undefined ? true : sw === 'on';
}

/** The window's mode (see the module comment). */
export function windowMode(hass: HomeAssistant, w: HouseWindow): WindowMode {
  const sel = stateOf(hass, w.entities.mode);
  if (sel && OFF_OPTION.test(sel)) return 'off';
  if (stateOf(hass, w.entities.controlSwitch) === 'off') return 'off';
  if (sel && HOLD_OPTION.test(sel)) return 'hold';
  if (stateOf(hass, w.entities.manualOverride) === 'on') return 'hold';
  return 'auto';
}

/** One mode when every window agrees, `mixed` otherwise, null when empty. */
export function groupMode(modes: WindowMode[]): GroupMode | null {
  if (modes.length === 0) return null;
  return modes.every((m) => m === modes[0]) ? modes[0] : 'mixed';
}

export interface ModeCounts {
  auto: number;
  hold: number;
  off: number;
}

export function countModes(modes: WindowMode[]): ModeCounts {
  const counts: ModeCounts = { auto: 0, hold: 0, off: 0 };
  for (const m of modes) counts[m] += 1;
  return counts;
}

export interface WindowStatus {
  mode: WindowMode;
  /** ISO time the hold ends, when on hold and known. */
  holdUntil: string | null;
  /** The shade's reported position (the primary cover), else the target. */
  position: number | null;
  /** The engine's target position (the Position sensor state). */
  target: number | null;
  /** The sun is on the glass (Sun in front sensor, else the `sun.in_fov` attribute). */
  sunOnGlass: boolean;
  nextMove: { time: string; position: number | null } | null;
  intent: string | null;
  trace: string[];
  /** The direction the window faces, when published. */
  azimuth: number | null;
  /** False when the Position sensor is missing or unavailable. */
  available: boolean;
}

function num(v: unknown): number | null {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''));
  return Number.isFinite(n) ? n : null;
}

/** Everything the card shows about one window, read from `hass`. */
export function windowStatus(hass: HomeAssistant, w: HouseWindow): WindowStatus {
  const posId = w.entities.position;
  const posState = posId ? hass.states[posId] : undefined;
  const attrs = (posState?.attributes ?? {}) as CoverPositionAttributes;
  const mode = windowMode(hass, w);
  const available = !!posState && posState.state !== 'unavailable' && posState.state !== 'unknown';
  const target = available ? num(posState!.state) : null;
  const actual = w.covers.length > 0 ? liveCoverPosition(hass, w.coverType, w.covers[0]) : null;

  let holdUntil: string | null = null;
  if (mode === 'hold') {
    const candidates: unknown[] = [
      w.entities.mode ? hass.states[w.entities.mode]?.attributes?.until : undefined,
      w.entities.manualOverride
        ? hass.states[w.entities.manualOverride]?.attributes?.until
        : undefined,
      attrs.override_until,
    ];
    holdUntil = candidates.find((c): c is string => typeof c === 'string' && c.length > 0) ?? null;
  }

  const sunId = w.entities.sunInFront;
  const sunOnGlass = sunId ? hass.states[sunId]?.state === 'on' : attrs.sun?.in_fov === true;

  const nm = attrs.next_move;
  const nextMove =
    nm && typeof nm.time === 'string' && nm.time
      ? { time: nm.time, position: num(nm.position) }
      : null;

  return {
    mode,
    holdUntil,
    position: actual ?? target,
    target,
    sunOnGlass,
    nextMove,
    intent: typeof attrs.intent === 'string' ? attrs.intent : null,
    trace: Array.isArray(attrs.decision_trace)
      ? attrs.decision_trace.filter((l): l is string => typeof l === 'string')
      : [],
    azimuth: num(attrs.azimuth_window ?? attrs.sun?.window_azimuth),
    available,
  };
}

/** True when a select has the P5 Mode options (an explicit auto and hold). */
function isModeSelect(options: string[]): boolean {
  return !!holdOption(options) && options.some((o) => AUTO_OPTION.test(o));
}

/** True when every window's Mode select can be set to hold (P5 surface). */
export function canHold(hass: HomeAssistant, windows: HouseWindow[]): boolean {
  return (
    windows.length > 0 && windows.every((w) => !!holdOption(selectOptions(hass, w.entities.mode)))
  );
}

/** True when the house select offers a hold option (P5 surface). */
export function hubCanHold(hass: HomeAssistant, hub: HouseHub): boolean {
  return !!holdOption(selectOptions(hass, hub.modeSelect));
}

/** Group entity ids by a key into one call each, in first-seen order. */
function grouped(
  items: Array<{ key: string; id: string }>,
  make: (key: string, ids: string[]) => ServiceCall,
): ServiceCall[] {
  const map = new Map<string, string[]>();
  for (const { key, id } of items) {
    const list = map.get(key) ?? [];
    if (!list.includes(id)) list.push(id);
    map.set(key, list);
  }
  return [...map.entries()].map(([key, ids]) => make(key, ids));
}

const selectCall = (option: string, ids: string[]): ServiceCall => ({
  domain: 'select',
  service: 'select_option',
  data: { entity_id: ids, option },
});

const entityCall = (domain: string, service: string, ids: string[]): ServiceCall => ({
  domain,
  service,
  data: { entity_id: ids },
});

/** Switch control on or off for `windows`: the Mode select where it exists,
 *  else the Automatic control switch. */
function planControl(hass: HomeAssistant, windows: HouseWindow[], on: boolean): ServiceCall[] {
  const selects: Array<{ key: string; id: string }> = [];
  const switches: string[] = [];
  for (const w of windows) {
    const options = selectOptions(hass, w.entities.mode);
    const option = on ? autoOption(options, prefersClimate(hass, w)) : offOption(options);
    if (w.entities.mode && option) selects.push({ key: option, id: w.entities.mode });
    else if (w.entities.controlSwitch) switches.push(w.entities.controlSwitch);
  }
  const calls = grouped(selects, (option, ids) => selectCall(option, ids));
  if (switches.length > 0) calls.push(entityCall('switch', on ? 'turn_on' : 'turn_off', switches));
  return calls;
}

/**
 * Service calls that put `windows` in `target` mode, in the order they must
 * run. Windows already in that mode are left alone.
 */
export function planWindowsMode(
  hass: HomeAssistant,
  windows: HouseWindow[],
  target: WindowMode,
): ServiceCall[] {
  const modes = new Map(windows.map((w) => [w, windowMode(hass, w)]));
  const todo = windows.filter((w) => modes.get(w) !== target);
  if (todo.length === 0) return [];

  if (target === 'off') return planControl(hass, todo, false);

  if (target === 'hold') return planHold(hass, todo);

  // Auto on a P5 Mode select: one select_option; it also ends a hold.
  const p5 = todo.filter((w) => isModeSelect(selectOptions(hass, w.entities.mode)));
  const calls = grouped(
    p5.map((w) => ({
      key: autoOption(selectOptions(hass, w.entities.mode), false)!,
      id: w.entities.mode!,
    })),
    (option, ids) => selectCall(option, ids),
  );
  // Older surfaces: control back on where it is off, then return to auto.
  const legacy = todo.filter((w) => !p5.includes(w));
  calls.push(
    ...planControl(
      hass,
      legacy.filter((w) => modes.get(w) === 'off'),
      true,
    ),
  );
  const buttons = legacy.map((w) => w.entities.returnButton).filter((b): b is string => !!b);
  if (buttons.length > 0) calls.push(entityCall('button', 'press', buttons));
  return calls;
}

/** The `duration` of a hold call ({hours, minutes, seconds}) for `ms`. */
export function holdDuration(ms: number): { hours: number; minutes: number; seconds: number } {
  const total = Math.max(0, Math.round(ms / 1000));
  return {
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}

/** Milliseconds from `nowMs` to the coming local midnight ("until tonight"). */
export function msUntilTonight(nowMs: number): number {
  const end = new Date(nowMs);
  end.setHours(24, 0, 0, 0);
  return end.getTime() - nowMs;
}

/**
 * Hold `windows` (adaptive_cover.hold): one call with every Mode select that
 * offers hold. `durationMs` omitted: each window's manual-override time.
 * Windows already on hold are held again from now.
 */
export function planHold(
  hass: HomeAssistant,
  windows: HouseWindow[],
  durationMs?: number,
): ServiceCall[] {
  const ids = windows
    .filter((w) => !!holdOption(selectOptions(hass, w.entities.mode)))
    .map((w) => w.entities.mode!);
  if (ids.length === 0) return [];
  const data: Record<string, unknown> = { entity_id: [...new Set(ids)] };
  if (durationMs !== undefined) data.duration = holdDuration(durationMs);
  return [{ domain: INTEGRATION_DOMAIN, service: 'hold', data }];
}

export interface HouseScope {
  hub: HouseHub;
  /** Every window the house controls act on. */
  windows: HouseWindow[];
  /** Use the house device's entities. False when the card shows only some
   *  floors or rooms: then the house controls act on those windows only. */
  useHub: boolean;
}

/** House Auto / Hold / Off: the house select where it can, else group calls. */
export function planHouseMode(
  hass: HomeAssistant,
  scope: HouseScope,
  target: WindowMode,
): ServiceCall[] {
  const { hub, windows, useHub } = scope;
  if (!useHub || !hub.modeSelect) return planWindowsMode(hass, windows, target);
  const modes = windows.map((w) => windowMode(hass, w));
  if (modes.length > 0 && modes.every((m) => m === target)) return [];
  const options = selectOptions(hass, hub.modeSelect);

  if (target === 'off') {
    const option = offOption(options);
    return option ? [selectCall(option, [hub.modeSelect])] : planWindowsMode(hass, windows, 'off');
  }
  if (target === 'hold') {
    const option = holdOption(options);
    return option ? [selectCall(option, [hub.modeSelect])] : planWindowsMode(hass, windows, 'hold');
  }
  return planReturnAll(hass, scope);
}

/**
 * "Return all to auto": control on everywhere it is off (the house select's
 * automatic option), then the house Return button, which ends every hold
 * and moves every shade back to its automatic position.
 */
export function planReturnAll(hass: HomeAssistant, scope: HouseScope): ServiceCall[] {
  const { hub, windows, useHub } = scope;
  if (!useHub) return planWindowsMode(hass, windows, 'auto');
  // P5 house select: Auto sets every window's Mode to auto (holds end).
  const hubOptions = selectOptions(hass, hub.modeSelect);
  if (hub.modeSelect && isModeSelect(hubOptions)) {
    return [selectCall(autoOption(hubOptions, false)!, [hub.modeSelect])];
  }
  const calls: ServiceCall[] = [];
  const anyOff = windows.some((w) => windowMode(hass, w) === 'off');
  if (anyOff) {
    const option = hub.modeSelect
      ? autoOption(selectOptions(hass, hub.modeSelect), false)
      : undefined;
    if (hub.modeSelect && option) calls.push(selectCall(option, [hub.modeSelect]));
    else
      calls.push(
        ...planControl(
          hass,
          windows.filter((w) => windowMode(hass, w) === 'off'),
          true,
        ),
      );
  }
  if (hub.returnButton) {
    calls.push(entityCall('button', 'press', [hub.returnButton]));
  } else {
    const buttons = windows.map((w) => w.entities.returnButton).filter((b): b is string => !!b);
    if (buttons.length > 0) calls.push(entityCall('button', 'press', buttons));
  }
  return calls;
}

export type CoverCommand = 'open' | 'close' | 'stop';

const COVER_SERVICES: Record<CoverCommand, [string, string]> = {
  open: ['open_cover', 'open_cover_tilt'],
  close: ['close_cover', 'close_cover_tilt'],
  stop: ['stop_cover', 'stop_cover_tilt'],
};

/** Open / close / stop the physical covers of `windows` (tilt windows use
 *  the tilt services). One call per service. */
export function planCovers(windows: HouseWindow[], command: CoverCommand): ServiceCall[] {
  const [lift, tilt] = COVER_SERVICES[command];
  const items = windows.flatMap((w) =>
    w.covers.map((id) => ({ key: w.coverType === 'cover_tilt' ? tilt : lift, id })),
  );
  return grouped(items, (service, ids) => entityCall('cover', service, ids));
}

/** Open all / Close all: the house cover where it can, else every cover. */
export function planHouseCovers(scope: HouseScope, command: 'open' | 'close'): ServiceCall[] {
  if (scope.useHub && scope.hub.cover) {
    return [entityCall('cover', COVER_SERVICES[command][0], [scope.hub.cover])];
  }
  return planCovers(scope.windows, command);
}

export type ClimateState = 'on' | 'off' | 'mixed';

/** The house's Climate switch (P5 flip: the house `climate_on` setting), when
 *  the house controls act through the hub. */
function hubClimate(hass: HomeAssistant, scope: HouseScope | undefined): string | null {
  const id = scope?.useHub ? scope.hub.climateSwitch : undefined;
  const st = stateOf(hass, id);
  return id && (st === 'on' || st === 'off') ? id : null;
}

/** The Climate control's state: the house's Climate switch, else the Climate
 *  mode switches across `windows`; null when there is none. */
export function climateState(
  hass: HomeAssistant,
  windows: HouseWindow[],
  scope?: HouseScope,
): ClimateState | null {
  const house = hubClimate(hass, scope);
  if (house) return stateOf(hass, house) === 'on' ? 'on' : 'off';
  const states = windows
    .map((w) => stateOf(hass, w.entities.climateSwitch))
    .filter((s): s is string => s === 'on' || s === 'off');
  if (states.length === 0) return null;
  if (states.every((s) => s === 'on')) return 'on';
  if (states.every((s) => s === 'off')) return 'off';
  return 'mixed';
}

/** Climate on or off: the house's Climate switch, else every window's Climate
 *  mode switch, in one call. */
export function planClimate(
  windows: HouseWindow[],
  on: boolean,
  hass?: HomeAssistant,
  scope?: HouseScope,
): ServiceCall[] {
  const house = hass ? hubClimate(hass, scope) : null;
  if (house) return [entityCall('switch', on ? 'turn_on' : 'turn_off', [house])];
  const ids = windows.map((w) => w.entities.climateSwitch).filter((s): s is string => !!s);
  return ids.length > 0 ? [entityCall('switch', on ? 'turn_on' : 'turn_off', ids)] : [];
}

/** The most common Control method (winter / summer / intermediate) among
 *  windows whose climate mode is on, or null. */
export function dominantClimateMethod(hass: HomeAssistant, windows: HouseWindow[]): string | null {
  const counts = new Map<string, number>();
  for (const w of windows) {
    if (stateOf(hass, w.entities.climateSwitch) !== 'on') continue;
    const m = stateOf(hass, w.entities.controlMethod);
    if (m === 'winter' || m === 'summer' || m === 'intermediate') {
      counts.set(m, (counts.get(m) ?? 0) + 1);
    }
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [m, n] of counts) {
    if (n > bestN) {
      best = m;
      bestN = n;
    }
  }
  return best;
}

/** Run calls one after another (a select must land before the press that
 *  follows it). */
export async function runCalls(hass: HomeAssistant, calls: ServiceCall[]): Promise<void> {
  for (const c of calls) {
    await hass.callService(c.domain, c.service, c.data);
  }
}
