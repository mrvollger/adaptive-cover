export const CARD_VERSION = '1.0.0';
export const CARD_NAME = 'adaptive-cover-card';
export const CARD_EDITOR_NAME = 'adaptive-cover-card-editor';
export const SKY_COMPASS_CARD_NAME = 'adaptive-cover-sky-compass-card';
export const SKY_COMPASS_CARD_EDITOR_NAME = 'adaptive-cover-sky-compass-card-editor';
export const TILE_CARD_NAME = 'adaptive-cover-tile-card';
export const TILE_CARD_EDITOR_NAME = 'adaptive-cover-tile-card-editor';
export const DECISION_CARD_NAME = 'adaptive-cover-decision-card';
export const DECISION_CARD_EDITOR_NAME = 'adaptive-cover-decision-card-editor';

export const INTEGRATION_DOMAIN = 'adaptive_cover';

/**
 * The Adaptive Cover engine's `Intent` enum values, in display order.
 * Emitted by the integration as the `intent` attribute on the Cover Position
 * sensor. Keep in lock-step with
 * `custom_components/adaptive_cover/engine/models.py::Intent`.
 *
 * (The upstream card called these "handlers" after the Pro integration's
 * pipeline; the fork keeps the identifier names to limit churn, but the
 * values are Adaptive Cover *intents*.)
 */
export const HANDLER_ORDER = [
  'privacy',
  'climate_open_heat',
  'climate_block_heat',
  'climate_tilt_preset',
  'climate_default',
  'admit_no_glare',
  'shaded_by_overhang',
  'sunset',
  'calculated',
  'default',
] as const;

export type HandlerName = (typeof HANDLER_ORDER)[number];

export const HANDLER_LABELS: Record<HandlerName, string> = {
  privacy: 'Privacy',
  climate_open_heat: 'Climate · warm up',
  climate_block_heat: 'Climate · block heat',
  climate_tilt_preset: 'Climate · tilt preset',
  climate_default: 'Climate · default',
  admit_no_glare: 'Warmth, no glare',
  shaded_by_overhang: 'Shaded by overhang',
  sunset: 'Sunset',
  calculated: 'Sun tracking',
  default: 'Default',
};

/**
 * i18n dotted keys for each intent. Callers with access to `hass` resolve
 * labels via `t(HANDLER_I18N_KEYS[intent], hass)`; callers without `hass`
 * fall back to `HANDLER_LABELS` for the EN string.
 */
export const HANDLER_I18N_KEYS: Record<HandlerName, string> = {
  privacy: 'handler.privacy',
  climate_open_heat: 'handler.climate_open_heat',
  climate_block_heat: 'handler.climate_block_heat',
  climate_tilt_preset: 'handler.climate_tilt_preset',
  climate_default: 'handler.climate_default',
  admit_no_glare: 'handler.admit_no_glare',
  shaded_by_overhang: 'handler.shaded_by_overhang',
  sunset: 'handler.sunset',
  calculated: 'handler.calculated',
  default: 'handler.default',
};

export const COVER_TYPE_ICONS: Record<string, string> = {
  cover_blind: 'mdi:blinds-horizontal',
  cover_awning: 'mdi:awning-outline',
  cover_tilt: 'mdi:blinds',
};

export const COVER_TYPE_ICONS_OPEN: Record<string, string> = {
  cover_blind: 'mdi:blinds-open',
  cover_awning: 'mdi:awning-outline',
  cover_tilt: 'mdi:blinds-open',
};

export const COVER_TYPE_ICONS_CLOSED: Record<string, string> = {
  cover_blind: 'mdi:blinds-horizontal-closed',
  cover_awning: 'mdi:window-closed-variant',
  cover_tilt: 'mdi:blinds',
};

export const COVER_ICON_FALLBACK = 'mdi:window-shutter';
export const COVER_ICON_FALLBACK_OPEN = 'mdi:window-shutter-open';
export const COVER_ICON_FALLBACK_CLOSED = 'mdi:window-shutter';

export const COVER_OPEN_THRESHOLD = 95;
export const COVER_CLOSED_THRESHOLD = 5;

/**
 * Badge kinds rendered on the tile card. Each intent maps to one kind; `auto`
 * is the fallback for unknown / "default" winners; `manual` and `off` are
 * state-driven (manual-override binary / Toggle Control switch).
 */
export type BadgeKind =
  | 'auto'
  | 'manual'
  | 'climate'
  | 'glare_zone'
  | 'privacy'
  | 'sunset'
  | 'solar'
  | 'off'
  | 'off_schedule';

/**
 * Map an intent to its badge kind. Anything not in this table (including
 * `default` and unknown intents) falls through to `auto`.
 */
export const BADGE_KINDS_BY_HANDLER: Partial<Record<HandlerName, BadgeKind>> = {
  calculated: 'solar',
  admit_no_glare: 'glare_zone',
  privacy: 'privacy',
  sunset: 'sunset',
  climate_open_heat: 'climate',
  climate_block_heat: 'climate',
  climate_tilt_preset: 'climate',
  climate_default: 'climate',
};

interface BadgeTokens {
  label: string;
  bg: string;
  fg: string;
}

/**
 * Visual tokens per badge kind. Colors are chosen against the HA dark/light
 * background defaults; they're intentionally hard-coded rather than driven by
 * `var(--*)` so the badge reads the same regardless of theme.
 */
export const BADGE_TOKENS: Record<BadgeKind, BadgeTokens> = {
  auto: { label: 'Auto', bg: 'rgba(76, 175, 80, 0.18)', fg: '#2e7d32' },
  manual: { label: 'Manual', bg: 'rgba(255, 152, 0, 0.22)', fg: '#e65100' },
  climate: { label: 'Climate', bg: 'rgba(0, 150, 136, 0.22)', fg: '#00695c' },
  glare_zone: { label: 'No glare', bg: 'rgba(244, 67, 54, 0.22)', fg: '#b71c1c' },
  privacy: { label: 'Privacy', bg: 'rgba(103, 58, 183, 0.22)', fg: '#4527a0' },
  sunset: { label: 'Sunset', bg: 'rgba(255, 112, 67, 0.22)', fg: '#bf360c' },
  solar: { label: 'Solar tracking', bg: 'rgba(76, 175, 80, 0.22)', fg: '#1b5e20' },
  off: { label: 'Off', bg: 'rgba(97, 97, 97, 0.28)', fg: '#212121' },
  off_schedule: { label: 'Off-schedule', bg: 'rgba(96, 125, 139, 0.22)', fg: '#37474f' },
};

/**
 * i18n dotted keys for each badge kind. Callers with access to `hass`
 * resolve labels via `t(BADGE_I18N_KEYS[kind], hass)`; the EN values in
 * `BADGE_TOKENS[kind].label` are kept as a fallback when `hass` is missing
 * (e.g. unit tests, isolated component renders).
 */
export const BADGE_I18N_KEYS: Record<BadgeKind, string> = {
  auto: 'badge.auto',
  manual: 'badge.manual',
  climate: 'badge.climate',
  glare_zone: 'badge.glare_zone',
  privacy: 'badge.privacy',
  sunset: 'badge.sunset',
  solar: 'badge.solar',
  off: 'badge.off',
  off_schedule: 'badge.off_schedule',
};

/**
 * Leading mdi icon rendered inside each badge.
 */
export const BADGE_ICONS: Record<BadgeKind, string> = {
  auto: 'mdi:autorenew',
  manual: 'mdi:hand-back-right',
  climate: 'mdi:thermostat',
  glare_zone: 'mdi:weather-sunny-alert',
  privacy: 'mdi:shield-home',
  sunset: 'mdi:weather-sunset-down',
  solar: 'mdi:white-balance-sunny',
  off: 'mdi:power',
  off_schedule: 'mdi:clock-alert-outline',
};

/** Logical slots the card binds to. */
export type EntityRole =
  | 'target_position_sensor'
  | 'start_sensor'
  | 'end_sensor'
  | 'control_status_sensor'
  | 'sun_infront_binary'
  | 'manual_override_binary'
  | 'automatic_control_switch'
  | 'manual_toggle_switch'
  | 'climate_mode_switch'
  | 'reset_override_button';

/**
 * Map (platform, unique_id suffix) → card role.
 *
 * Every Adaptive Cover entity's unique_id is `{entry_id}_{suffix}` where the
 * suffix is set by the integration — it is immutable for the lifetime of the
 * entity (not affected by entity_id renames, device renames, or translation
 * changes). This is the authoritative identity field, sourced from the HA
 * entity registry via `config/entity_registry/list` websocket command.
 *
 * Platform must be part of the key: `Manual Override` is used by both the
 * binary sensor (platform `binary_sensor`) and the switch (platform `switch`).
 * Platform disambiguates.
 *
 * Suffixes below are copied verbatim from the integration source:
 *   sensor.py        — "Cover Position", "Start Sun", "End Sun",
 *                      "Control Method", "Next State Change", "Last State Change"
 *   binary_sensor.py — "Sun Infront", "Manual Override"
 *   switch.py        — "Manual Override", "Toggle Control", "Climate Mode",
 *                      "Outside Temperature", "Lux", "Irradiance"
 *   button.py        — "Reset Manual Override"
 *   select.py        — "mode_select"
 *   number.py        — "number_{option_key}"
 */
export type ControlFlags = {
  integration_enabled: boolean;
  automatic_control: boolean;
  reset_manual_override: boolean;
};

export const DEFAULT_CONTROL_FLAGS: ControlFlags = {
  integration_enabled: true,
  automatic_control: true,
  reset_manual_override: true,
};

export function resolveControlFlags(
  cfg: { controls?: Partial<ControlFlags> } | undefined,
): ControlFlags {
  return { ...DEFAULT_CONTROL_FLAGS, ...cfg?.controls };
}

export const UNIQUE_ID_ROLES: Record<string, EntityRole> = {
  // sensor
  'sensor:Cover Position': 'target_position_sensor',
  'sensor:Start Sun': 'start_sensor',
  'sensor:End Sun': 'end_sensor',
  'sensor:Control Method': 'control_status_sensor',

  // binary_sensor
  'binary_sensor:Sun Infront': 'sun_infront_binary',
  'binary_sensor:Manual Override': 'manual_override_binary',

  // switch (note: "Manual Override" also exists as a binary_sensor suffix)
  'switch:Toggle Control': 'automatic_control_switch',
  'switch:Manual Override': 'manual_toggle_switch',
  'switch:Climate Mode': 'climate_mode_switch',

  // button
  'button:Reset Manual Override': 'reset_override_button',
};
