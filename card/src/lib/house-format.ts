import type { HomeAssistant } from 'custom-card-helpers';

import { HANDLER_ORDER } from '../const';
import type { WindowStatus } from './house-actions';
import { t } from './i18n';

/*
 * Text for the house card. Times use the viewer's HA locale settings
 * (language, 12/24 h, local or server time zone).
 */

interface LocaleLike {
  language?: string;
  time_format?: string;
  time_zone?: string;
}

function localeOf(hass: HomeAssistant): LocaleLike {
  return ((hass as unknown as { locale?: LocaleLike }).locale ?? {}) as LocaleLike;
}

function timeZoneOf(hass: HomeAssistant): string | undefined {
  if (localeOf(hass).time_zone === 'local') return undefined;
  const tz = (hass as unknown as { config?: { time_zone?: string } }).config?.time_zone;
  return tz || undefined;
}

/** "11:05 AM" (or "11:05" on a 24 h locale). Empty for an invalid time. */
export function formatTimeOfDay(hass: HomeAssistant, iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const loc = localeOf(hass);
  const hour12 = loc.time_format === '12' ? true : loc.time_format === '24' ? false : undefined;
  const opts: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit', hour12 };
  const lang = loc.language || (hass as unknown as { language?: string }).language || 'en';
  try {
    return d.toLocaleTimeString(lang, { ...opts, timeZone: timeZoneOf(hass) });
  } catch {
    return d.toLocaleTimeString(undefined, opts);
  }
}

/** Time left until `iso`: "1h 12m", "45m", "under 1m". Null when unknown. */
export function formatLeft(iso: string | null | undefined, nowMs: number): string | null {
  if (!iso) return null;
  const end = Date.parse(iso);
  if (Number.isNaN(end)) return null;
  const mins = Math.ceil((end - nowMs) / 60_000);
  if (mins < 1) return t('house.left_under_minute');
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const POINTS = [
  'N',
  'NNE',
  'NE',
  'ENE',
  'E',
  'ESE',
  'SE',
  'SSE',
  'S',
  'SSW',
  'SW',
  'WSW',
  'W',
  'WNW',
  'NW',
  'NNW',
];

/** 16-point compass name of a bearing: 100 → "E", 240 → "WSW". */
export function compassPoint(deg: number): string {
  const i = Math.round((((deg % 360) + 360) % 360) / 22.5) % 16;
  return POINTS[i];
}

/** "1 window", "15 windows" (also room / floor). */
export function countLabel(kind: 'window' | 'room' | 'floor', n: number): string {
  return t(`house.count.${kind}_${n === 1 ? 'one' : 'other'}`, { n });
}

function pct(v: number | null): string {
  return v === null ? '—' : `${Math.round(v)}%`;
}

/** Position as the row shows it. */
export function positionText(s: WindowStatus): string {
  return pct(s.position);
}

/** The short line under a window's name. */
export function nextText(hass: HomeAssistant, s: WindowStatus, nowMs: number): string {
  if (!s.available) return t('house.next.unavailable');
  if (s.mode === 'off') return t('house.next.off');
  if (s.mode === 'hold') {
    const left = formatLeft(s.holdUntil, nowMs);
    return left ? t('house.next.hold', { left }) : t('house.next.hold_unknown');
  }
  if (s.nextMove) {
    const time = formatTimeOfDay(hass, s.nextMove.time);
    if (time && s.nextMove.position !== null) {
      return t('house.next.move', { position: pct(s.nextMove.position), time });
    }
    if (time) return t('house.next.change', { time });
  }
  return t('house.next.none');
}

/** The mode chip: "Auto", "Hold · 1h 12m", "Off". */
export function chipText(s: WindowStatus, nowMs: number): string {
  if (s.mode === 'hold') {
    const left = formatLeft(s.holdUntil, nowMs);
    return left ? t('house.chip_hold_left', { left }) : t('house.mode.hold');
  }
  return t(`house.mode.${s.mode}`);
}

/** The intent's label ("Sun tracking"), or the raw intent when unknown. */
export function intentLabel(intent: string | null): string | null {
  if (!intent) return null;
  return (HANDLER_ORDER as readonly string[]).includes(intent) ? t(`handler.${intent}`) : intent;
}

/** "Why this position": the hold / off reason, else the engine's intent and
 *  its final trace line. */
export function whyText(hass: HomeAssistant, s: WindowStatus): string {
  if (s.mode === 'off') return t('house.why.off');
  if (s.mode === 'hold') {
    const time = formatTimeOfDay(hass, s.holdUntil);
    return time ? t('house.why.hold', { time }) : t('house.why.hold_unknown');
  }
  const label = intentLabel(s.intent);
  const reason = s.trace.length > 0 ? s.trace[s.trace.length - 1] : '';
  if (label && reason) return `${label}: ${reason}`;
  return label || reason || t('house.why.none');
}

/** "Faces 100° E", or null when the window's direction is unknown. */
export function facesText(s: WindowStatus): string | null {
  if (s.azimuth === null) return null;
  return t('house.sheet.faces', { deg: Math.round(s.azimuth), dir: compassPoint(s.azimuth) });
}

/** The header's sun pill from `sun.sun`, or null without it. */
export function sunText(hass: HomeAssistant, short = false): string | null {
  const sun = hass.states['sun.sun'];
  if (!sun) return null;
  const a = sun.attributes as {
    azimuth?: number;
    elevation?: number;
    next_setting?: string;
    next_rising?: string;
  };
  if (sun.state === 'above_horizon' && typeof a.elevation === 'number') {
    const time = formatTimeOfDay(hass, a.next_setting);
    const params = {
      azimuth: Math.round(a.azimuth ?? 0),
      elevation: Math.round(a.elevation),
      time,
    };
    return t(short ? 'house.sun_up_short' : 'house.sun_up', params);
  }
  const time = formatTimeOfDay(hass, a.next_rising);
  return time ? t('house.sun_down', { time }) : t('house.sun_down_plain');
}
