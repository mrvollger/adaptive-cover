import type { HomeAssistant } from 'custom-card-helpers';

import { t } from './i18n';

/*
 * The recurring settings the house, floor and room sheets show (refactor
 * plan "One-time vs recurring settings"; ADR 0003).
 *
 * The integration's option spec decides which level may store a setting
 * (`custom_components/adaptive_cover/settings/spec.py`: an `Opt`'s `home`
 * plus `overridable_at`; the five former window switches are in
 * `settings/shadow.py` TOGGLE_OPTS). `adaptive_cover.set_profile` accepts
 * exactly those. The card cannot read the spec at runtime, so this table
 * mirrors it:
 *
 * - every recurring setting that a floor or a room may store (the room and
 *   floor sheets list these), and
 * - the house-only settings that have an entity on the house device.
 *
 * `tests/profile-settings.test.ts` parses spec.py and shadow.py and fails
 * when a level here differs from the spec, or when the spec gains a
 * recurring setting that a floor or room may store and this table lacks.
 *
 * The rest of the house-only settings (weather, sensors, quiet hours, move
 * limits) have no house entity yet: `set_profile` with `scope: house`
 * changes them.
 */

export type ProfileLevel = 'house' | 'floor' | 'area';

/** How a setting is shown and edited. `duration` is edited in minutes. */
export type SettingKind = 'bool' | 'number' | 'temperature' | 'duration' | 'time' | 'entity';

export type SettingSection = 'hand' | 'comfort' | 'schedule' | 'positions' | 'glare' | 'privacy';

export const SECTIONS: readonly SettingSection[] = [
  'hand',
  'comfort',
  'schedule',
  'positions',
  'glare',
  'privacy',
];

export interface ProfileSetting {
  /** The option key (`set_profile` field). */
  key: string;
  kind: SettingKind;
  /** Levels `set_profile` may store it at: the spec's home and override
   *  levels, without `window`. */
  levels: readonly ProfileLevel[];
  /** The spec also lets one window override it (window setup, Exceptions). */
  window: boolean;
  section: SettingSection;
  /** Display unit of a number (temperatures use HA's unit). */
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  /** Entity domains an `entity` setting accepts. */
  domains?: readonly string[];
  /** The house device has a switch or number for the house value. */
  hub?: 'switch' | 'number';
  /** The Position sensor attribute with the window's resolved value. */
  attr?: 'default' | 'sunset_default' | 'sunset_offset';
}

const HFA: readonly ProfileLevel[] = ['house', 'floor', 'area'];
const HA_: readonly ProfileLevel[] = ['house', 'area'];
const H: readonly ProfileLevel[] = ['house'];

// Order within a section is the order the sheets show.
export const PROFILE_SETTINGS: readonly ProfileSetting[] = [
  // Hand moves
  {
    key: 'manual_override_duration',
    kind: 'duration',
    levels: HA_,
    window: false,
    section: 'hand',
    unit: 'min',
    min: 1,
    max: 24 * 60,
    step: 1,
    hub: 'number',
  },
  { key: 'manual_override_reset', kind: 'bool', levels: HA_, window: false, section: 'hand' },
  {
    key: 'manual_detection',
    kind: 'bool',
    levels: HA_,
    window: false,
    section: 'hand',
    hub: 'switch',
  },
  {
    key: 'manual_ignore_intermediate',
    kind: 'bool',
    levels: HA_,
    window: false,
    section: 'hand',
  },
  {
    key: 'manual_threshold',
    kind: 'number',
    levels: HA_,
    window: false,
    section: 'hand',
    unit: '%',
    min: 0,
    max: 99,
    step: 1,
  },
  // Comfort
  {
    key: 'climate_on',
    kind: 'bool',
    levels: HA_,
    window: false,
    section: 'comfort',
    hub: 'switch',
  },
  { key: 'climate_mode', kind: 'bool', levels: HA_, window: false, section: 'comfort' },
  {
    key: 'temp_low',
    kind: 'temperature',
    levels: HFA,
    window: false,
    section: 'comfort',
    hub: 'number',
  },
  {
    key: 'temp_high',
    kind: 'temperature',
    levels: HFA,
    window: false,
    section: 'comfort',
    hub: 'number',
  },
  {
    key: 'temp_entity',
    kind: 'entity',
    levels: ['floor', 'area'],
    window: false,
    section: 'comfort',
    domains: ['climate', 'sensor'],
  },
  {
    key: 'use_outside_temp',
    kind: 'bool',
    levels: H,
    window: false,
    section: 'comfort',
    hub: 'switch',
  },
  { key: 'use_lux', kind: 'bool', levels: H, window: false, section: 'comfort', hub: 'switch' },
  {
    key: 'use_irradiance',
    kind: 'bool',
    levels: H,
    window: false,
    section: 'comfort',
    hub: 'switch',
  },
  // Daily schedule
  { key: 'start_time', kind: 'time', levels: HA_, window: false, section: 'schedule' },
  {
    key: 'start_entity',
    kind: 'entity',
    levels: HA_,
    window: false,
    section: 'schedule',
    domains: ['sensor', 'input_datetime'],
  },
  {
    key: 'sunrise_offset',
    kind: 'number',
    levels: HA_,
    window: false,
    section: 'schedule',
    unit: 'min',
    step: 1,
  },
  { key: 'end_time', kind: 'time', levels: HA_, window: false, section: 'schedule' },
  {
    key: 'end_entity',
    kind: 'entity',
    levels: HA_,
    window: false,
    section: 'schedule',
    domains: ['sensor', 'input_datetime'],
  },
  {
    key: 'sunset_offset',
    kind: 'number',
    levels: HA_,
    window: false,
    section: 'schedule',
    unit: 'min',
    step: 1,
    attr: 'sunset_offset',
  },
  { key: 'return_sunset', kind: 'bool', levels: HA_, window: false, section: 'schedule' },
  // Positions
  {
    key: 'default_percentage',
    kind: 'number',
    levels: HA_,
    window: true,
    section: 'positions',
    unit: '%',
    min: 0,
    max: 100,
    step: 1,
    attr: 'default',
  },
  {
    key: 'sunset_position',
    kind: 'number',
    levels: HA_,
    window: true,
    section: 'positions',
    unit: '%',
    min: 0,
    max: 100,
    step: 1,
    attr: 'sunset_default',
  },
  // Glare
  {
    key: 'eye_height',
    kind: 'number',
    levels: HA_,
    window: true,
    section: 'glare',
    unit: 'm',
    min: 0.1,
    max: 3,
    step: 0.01,
    hub: 'number',
  },
  {
    key: 'occupied_distance',
    kind: 'number',
    levels: HA_,
    window: true,
    section: 'glare',
    unit: 'm',
    min: 0.1,
    max: 10,
    step: 0.1,
    hub: 'number',
  },
  // Privacy
  {
    key: 'privacy_offset',
    kind: 'number',
    levels: HA_,
    window: false,
    section: 'privacy',
    unit: 'min',
    min: 0,
    max: 180,
    step: 5,
    hub: 'number',
  },
  {
    key: 'privacy_position',
    kind: 'number',
    levels: HA_,
    window: false,
    section: 'privacy',
    unit: '%',
    min: 0,
    max: 100,
    step: 1,
  },
];

export const SETTINGS_BY_KEY: ReadonlyMap<string, ProfileSetting> = new Map(
  PROFILE_SETTINGS.map((s) => [s.key, s]),
);

/** The house settings the house sheet edits through the house device (the
 *  everyday ones); the rest are on the house device page. */
export const HOUSE_SHEET_KEYS: readonly string[] = [
  'climate_on',
  'temp_low',
  'temp_high',
  'manual_override_duration',
  'eye_height',
  'occupied_distance',
];

/** Settings a sheet at `level` shows, in section order. */
export function settingsAt(level: ProfileLevel): ProfileSetting[] {
  if (level === 'house') {
    return HOUSE_SHEET_KEYS.map((k) => SETTINGS_BY_KEY.get(k)!);
  }
  return SECTIONS.flatMap((section) =>
    PROFILE_SETTINGS.filter((s) => s.section === section && s.levels.includes(level)),
  );
}

// ------------------------------------------------------------ units

/** HA's temperature unit ("°F" / "°C"). */
export function temperatureUnit(hass: HomeAssistant | undefined): string {
  const unit = (hass?.config as { unit_system?: { temperature?: string } } | undefined)?.unit_system
    ?.temperature;
  return typeof unit === 'string' && unit ? unit : '°C';
}

/** Range and step of a temperature threshold in HA's unit (spec: `_TEMP_LOW`
 *  and `_TEMP_HIGH`, stored and compared in HA's unit). */
export function temperatureShape(
  key: string,
  unit: string,
): { min: number; max: number; step: number } {
  const f = unit === '°F';
  if (key === 'temp_high')
    return f ? { min: 50, max: 100, step: 0.5 } : { min: 10, max: 40, step: 0.5 };
  return f ? { min: 40, max: 90, step: 0.5 } : { min: 5, max: 30, step: 0.5 };
}

/** The editor's number range for `setting` (temperatures in HA's unit). */
export function numberShape(
  hass: HomeAssistant | undefined,
  setting: ProfileSetting,
): { min?: number; max?: number; step?: number; unit?: string } {
  if (setting.kind === 'temperature') {
    const unit = temperatureUnit(hass);
    return { ...temperatureShape(setting.key, unit), unit };
  }
  return { min: setting.min, max: setting.max, step: setting.step, unit: setting.unit };
}

// ------------------------------------------------------------ values

/** A stored duration ({hours, minutes, seconds}) in minutes, else null. */
export function durationMinutes(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    // The house number's state: minutes.
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : null;
  }
  if (!value || typeof value !== 'object') return null;
  const d = value as Record<string, unknown>;
  const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0);
  return n(d.hours) * 60 + n(d.minutes) + n(d.seconds) / 60;
}

/** The stored duration for `minutes` (whole seconds), as set_profile takes it. */
export function minutesDuration(minutes: number): {
  hours: number;
  minutes: number;
  seconds: number;
} {
  const total = Math.max(0, Math.round(minutes * 60));
  return {
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}

/**
 * A setting's value in the card's own form: booleans, numbers (durations in
 * minutes), times as "HH:MM:SS", entity ids. Anything else (unset, empty,
 * malformed) is null.
 */
export function normalizeValue(setting: ProfileSetting, raw: unknown): unknown {
  if (raw === null || raw === undefined || raw === '') return null;
  switch (setting.kind) {
    case 'bool':
      if (typeof raw === 'boolean') return raw;
      if (raw === 'on' || raw === 'true') return true;
      if (raw === 'off' || raw === 'false') return false;
      return null;
    case 'duration':
      return durationMinutes(raw);
    case 'number':
    case 'temperature': {
      const n = typeof raw === 'number' ? raw : parseFloat(String(raw));
      return Number.isFinite(n) ? n : null;
    }
    case 'time': {
      const m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(String(raw));
      if (!m) return null;
      return `${m[1].padStart(2, '0')}:${m[2]}:${m[3] ?? '00'}`;
    }
    case 'entity':
      return typeof raw === 'string' ? raw : null;
  }
}

/** The value `set_profile` stores for a card value (see `normalizeValue`). */
export function storedValue(setting: ProfileSetting, value: unknown): unknown {
  if (value === null) return null;
  if (setting.kind === 'duration' && typeof value === 'number') return minutesDuration(value);
  if (setting.kind === 'time') return normalizeValue(setting, value);
  return value;
}

/** Two card values are the same setting value. */
export function sameValue(a: unknown, b: unknown): boolean {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-9;
  return a === b;
}

function trimNumber(n: number): string {
  return String(Math.round(n * 100) / 100);
}

function durationText(minutes: number): string {
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h > 0 && m > 0) return t('settings.value.hours_minutes', { h, m });
  if (h > 0) return t('settings.value.hours', { h });
  return t('settings.value.minutes', { m });
}

function offsetText(minutes: number, key: string): string {
  const event = key === 'sunrise_offset' ? 'sunrise' : 'sunset';
  if (minutes === 0) return t(`settings.value.at_${event}`);
  const n = trimNumber(Math.abs(minutes));
  return t(minutes < 0 ? `settings.value.before_${event}` : `settings.value.after_${event}`, {
    n,
  });
}

/** A setting value for display ("72 °F", "2 h", "45 min after sunrise"). */
export function formatValue(
  hass: HomeAssistant | undefined,
  setting: ProfileSetting,
  value: unknown,
): string {
  if (value === null || value === undefined) {
    return setting.kind === 'entity' || setting.kind === 'time'
      ? t('settings.value.none')
      : t('settings.value.unset');
  }
  switch (setting.kind) {
    case 'bool':
      return value ? t('settings.value.on') : t('settings.value.off');
    case 'duration':
      return typeof value === 'number' ? durationText(value) : String(value);
    case 'temperature':
      return typeof value === 'number'
        ? `${trimNumber(value)} ${temperatureUnit(hass)}`
        : String(value);
    case 'number': {
      if (typeof value !== 'number') return String(value);
      if (setting.key === 'sunrise_offset' || setting.key === 'sunset_offset') {
        return offsetText(value, setting.key);
      }
      if (setting.unit === '%') return `${trimNumber(value)}%`;
      if (setting.unit === 'min') return t('settings.value.minutes', { m: trimNumber(value) });
      return setting.unit ? `${trimNumber(value)} ${setting.unit}` : trimNumber(value);
    }
    case 'time': {
      const s = String(value);
      return s === '00:00:00' ? t('settings.value.midnight') : s.slice(0, 5);
    }
    case 'entity': {
      const id = String(value);
      const name = hass?.states?.[id]?.attributes?.friendly_name;
      return typeof name === 'string' && name ? name : id;
    }
  }
}

/** The label of any recurring option key (unknown keys are spelled out). */
export function settingLabel(key: string): string {
  const label = t(`settings.label.${key}`);
  if (label !== `settings.label.${key}`) return label;
  const words = key.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A setting's one-line hint, or null. */
export function settingHint(key: string): string | null {
  const hint = t(`settings.hint.${key}`);
  return hint === `settings.hint.${key}` ? null : hint;
}
