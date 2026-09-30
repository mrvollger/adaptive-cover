import type { HomeAssistant } from 'custom-card-helpers';

import { t } from './i18n';

/*
 * The recurring settings the house, floor and room sheets show (refactor
 * plan "One-time vs recurring settings"; ADR 0003: every recurring key can
 * be reached from a house, floor or room sheet).
 *
 * The integration's option spec decides which level may store a setting
 * (`custom_components/adaptive_cover/settings/spec.py`: an `Opt`'s `home`
 * plus `overridable_at`; the five former window switches are in
 * `settings/shadow.py` TOGGLE_OPTS). `adaptive_cover.set_profile` accepts
 * exactly those. The card cannot read the spec at runtime, so this table
 * mirrors every recurring setting. `tests/profile-settings.test.ts` parses
 * spec.py, shadow.py and house_settings.py and fails when a key, a level or
 * a house entity here differs from them.
 *
 * `hub` names the house device's entity for the house value (a switch,
 * number or time; `house_settings.py`); the house sheet edits those through
 * the entity and everything else with `set_profile` for the house.
 */

export type ProfileLevel = 'house' | 'floor' | 'area';

/** How a setting is shown and edited. `duration` is edited in minutes;
 *  `list` picks any of `options`. */
export type SettingKind =
  | 'bool'
  | 'number'
  | 'temperature'
  | 'duration'
  | 'time'
  | 'entity'
  | 'list';

export type SettingSection =
  | 'hand'
  | 'climate'
  | 'schedule'
  | 'positions'
  | 'glare'
  | 'privacy'
  | 'movement'
  | 'sensors';

export const SECTIONS: readonly SettingSection[] = [
  'hand',
  'climate',
  'schedule',
  'positions',
  'glare',
  'privacy',
  'movement',
  'sensors',
];

/** Sections the house sheet folds away (rarely changed). */
export const FOLDED_SECTIONS: ReadonlySet<SettingSection> = new Set(['movement', 'sensors']);

/** Weather conditions (spec `WEATHER_CONDITIONS`). */
export const WEATHER_CONDITIONS: readonly string[] = [
  'clear-night',
  'clear',
  'cloudy',
  'fog',
  'hail',
  'lightning',
  'lightning-rainy',
  'partlycloudy',
  'pouring',
  'rainy',
  'snowy',
  'snowy-rainy',
  'sunny',
  'windy',
  'windy-variant',
  'exceptional',
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
  /** Choices of a `list` setting. */
  options?: readonly string[];
  /** The house may store "none" for it (optional entities, quiet hours,
   *  limits): the house sheet offers Clear. */
  clearable?: boolean;
  /** The house device's entity for the house value. */
  hub?: 'switch' | 'number' | 'time';
  /** The Position sensor attribute with the window's resolved value. */
  attr?: 'default' | 'sunset_default' | 'sunset_offset';
}

const HFA: readonly ProfileLevel[] = ['house', 'floor', 'area'];
const HA_: readonly ProfileLevel[] = ['house', 'area'];
const H: readonly ProfileLevel[] = ['house'];
const SENSOR = ['sensor'] as const;
const TIME_ENTITY = ['sensor', 'input_datetime'] as const;

type Row = Omit<ProfileSetting, 'key' | 'window' | 'section'> & { window?: boolean };

function rows(section: SettingSection, table: Record<string, Row>): ProfileSetting[] {
  return Object.entries(table).map(([key, r]) => ({
    ...r,
    key,
    window: r.window ?? false,
    section,
  }));
}

// Order within a section is the order the sheets show.
export const PROFILE_SETTINGS: readonly ProfileSetting[] = [
  ...rows('hand', {
    manual_override_duration: {
      kind: 'duration',
      levels: HA_,
      unit: 'min',
      min: 1,
      max: 24 * 60,
      step: 1,
      hub: 'number',
    },
    manual_override_reset: { kind: 'bool', levels: HA_ },
    manual_detection: { kind: 'bool', levels: HA_, hub: 'switch' },
    manual_ignore_intermediate: { kind: 'bool', levels: HA_ },
    manual_threshold: {
      kind: 'number',
      levels: HA_,
      unit: '%',
      min: 0,
      max: 99,
      step: 1,
      clearable: true,
    },
  }),
  ...rows('climate', {
    // The one Climate switch (house 3.2: climate_mode is gone; a window
    // opts out with its one-time ignore_climate, set on the window).
    climate_on: { kind: 'bool', levels: HA_, hub: 'switch' },
    temp_low: { kind: 'temperature', levels: HFA, hub: 'number' },
    temp_high: { kind: 'temperature', levels: HFA, hub: 'number' },
    temp_hysteresis: { kind: 'temperature', levels: HA_, hub: 'number' },
    temp_entity: {
      kind: 'entity',
      levels: ['floor', 'area'],
      domains: ['climate', 'sensor'],
    },
    presence_entity: {
      kind: 'entity',
      levels: H,
      domains: ['device_tracker', 'zone', 'binary_sensor', 'input_boolean'],
      clearable: true,
    },
    use_outside_temp: { kind: 'bool', levels: H, hub: 'switch' },
    outside_temp: {
      kind: 'entity',
      levels: H,
      domains: SENSOR,
      clearable: true,
    },
    outside_threshold: {
      kind: 'number',
      levels: H,
      min: 0,
      max: 100,
      step: 1,
    },
  }),
  ...rows('schedule', {
    start_time: { kind: 'time', levels: HA_ },
    start_entity: {
      kind: 'entity',
      levels: HA_,
      domains: TIME_ENTITY,
      clearable: true,
    },
    sunrise_offset: { kind: 'number', levels: HA_, unit: 'min', step: 1 },
    end_time: { kind: 'time', levels: HA_, hub: 'time' },
    end_entity: {
      kind: 'entity',
      levels: HA_,
      domains: TIME_ENTITY,
      clearable: true,
    },
    sunset_offset: {
      kind: 'number',
      levels: HA_,
      unit: 'min',
      step: 1,
      attr: 'sunset_offset',
    },
    return_sunset: { kind: 'bool', levels: HA_ },
  }),
  ...rows('positions', {
    default_percentage: {
      kind: 'number',
      levels: HA_,
      window: true,
      unit: '%',
      min: 0,
      max: 100,
      step: 1,
      attr: 'default',
    },
    sunset_position: {
      kind: 'number',
      levels: HA_,
      window: true,
      unit: '%',
      min: 0,
      max: 100,
      step: 1,
      attr: 'sunset_default',
    },
  }),
  ...rows('glare', {
    eye_height: {
      kind: 'number',
      levels: HA_,
      window: true,
      unit: 'm',
      min: 0.1,
      max: 3,
      step: 0.01,
      hub: 'number',
    },
    occupied_distance: {
      kind: 'number',
      levels: HA_,
      window: true,
      unit: 'm',
      min: 0.1,
      max: 10,
      step: 0.1,
      hub: 'number',
    },
  }),
  ...rows('privacy', {
    privacy_offset: {
      kind: 'number',
      levels: HA_,
      unit: 'min',
      min: 0,
      max: 180,
      step: 5,
      hub: 'number',
    },
    privacy_position: {
      kind: 'number',
      levels: HA_,
      unit: '%',
      min: 0,
      max: 100,
      step: 1,
    },
  }),
  ...rows('movement', {
    delta_position: {
      kind: 'number',
      levels: H,
      unit: '%',
      min: 1,
      max: 90,
      step: 1,
    },
    delta_time: { kind: 'number', levels: H, unit: 'min', min: 0, step: 1 },
    max_moves_hour: {
      kind: 'number',
      levels: H,
      min: 1,
      max: 60,
      step: 1,
      clearable: true,
    },
    quiet_start: { kind: 'time', levels: H, hub: 'time', clearable: true },
    quiet_end: { kind: 'time', levels: H, hub: 'time', clearable: true },
  }),
  ...rows('sensors', {
    weather_entity: {
      kind: 'entity',
      levels: H,
      domains: ['weather'],
      clearable: true,
    },
    weather_state: { kind: 'list', levels: H, options: WEATHER_CONDITIONS },
    use_lux: { kind: 'bool', levels: H, hub: 'switch' },
    lux_entity: {
      kind: 'entity',
      levels: H,
      domains: SENSOR,
      clearable: true,
    },
    lux_threshold: { kind: 'number', levels: H, unit: 'lx', step: 1 },
    use_irradiance: { kind: 'bool', levels: H, hub: 'switch' },
    irradiance_entity: {
      kind: 'entity',
      levels: H,
      domains: SENSOR,
      clearable: true,
    },
    irradiance_threshold: {
      kind: 'number',
      levels: H,
      unit: 'W/m²',
      step: 1,
    },
  }),
];

export const SETTINGS_BY_KEY: ReadonlyMap<string, ProfileSetting> = new Map(
  PROFILE_SETTINGS.map((s) => [s.key, s]),
);

/** Settings a sheet at `level` shows, in section order. */
export function settingsAt(level: ProfileLevel): ProfileSetting[] {
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

/** Range and step of a temperature threshold, or of the thresholds'
 *  hysteresis, in HA's unit (spec: `_TEMP_LOW`, `_TEMP_HIGH` and
 *  `_TEMP_HYSTERESIS`, stored and compared in HA's unit). */
export function temperatureShape(
  key: string,
  unit: string,
): { min: number; max: number; step: number } {
  const f = unit === '°F';
  if (key === 'temp_hysteresis')
    return f ? { min: 0, max: 5, step: 0.1 } : { min: 0, max: 3, step: 0.5 };
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
 * minutes), times as "HH:MM:SS", entity ids, lists of strings. Anything else
 * (unset, empty, malformed) is null.
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
    case 'list':
      return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string') : null;
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
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && [...a].sort().join('|') === [...b].sort().join('|');
  }
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

/** The label of a `list` option (a weather condition). */
export function optionLabel(option: string): string {
  const key = `settings.weather.${option}`;
  const label = t(key);
  return label === key ? option : label;
}

/** A setting value for display ("72 °F", "2 h", "45 min after sunrise"). */
export function formatValue(
  hass: HomeAssistant | undefined,
  setting: ProfileSetting,
  value: unknown,
): string {
  if (value === null || value === undefined) {
    return setting.kind === 'entity' || setting.kind === 'time' || setting.kind === 'list'
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
    case 'list':
      return Array.isArray(value) && value.length > 0
        ? value.map((v) => optionLabel(String(v))).join(', ')
        : t('settings.value.none');
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
