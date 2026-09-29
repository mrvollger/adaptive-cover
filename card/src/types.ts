import type { ActionConfig, HomeAssistant, LovelaceCardConfig } from 'custom-card-helpers';
import type { EntityRole } from './const';

export type { HomeAssistant };

export type CardSection = 'sky' | 'elevation' | 'decision' | 'covers' | 'overrides' | 'climate';

/**
 * Card-owned floating-tooltip configuration. When `enabled === false` the card
 * falls back to native browser `title=` tooltips. `offset` is the [right, down]
 * pixel offset of the bubble from the cursor; `delay` is the open delay (ms).
 */
export interface TooltipsConfig {
  enabled?: boolean;
  offset?: [number, number];
  delay?: number;
}

/** Per-kind badge opt-in flags. Omitted/undefined = on; only `=== false` hides. */
export interface BadgesOptInConfig {
  auto?: boolean;
  solar?: boolean;
  manual?: boolean;
  climate?: boolean;
  glare_zone?: boolean;
  privacy?: boolean;
  sunset?: boolean;
  off_schedule?: boolean;
}

/**
 * How a single-window card names its window. Set one of these; when several
 * are set, `window` wins, then `entry_id`, then `cover`.
 *
 * - `window`: the window key, which the Position sensor exposes as its
 *   `window_key` attribute. Preferred for new configs.
 * - `cover`: the cover entity the window controls. The card finds the window
 *   whose Position sensor lists this cover.
 * - `entry_id`: the legacy key. It still works because a window's key is the
 *   entry_id of the config entry that created it.
 */
export interface WindowBindingConfig {
  window?: string;
  cover?: string;
  entry_id?: string;
}

export interface AdaptiveCoverCardConfig extends LovelaceCardConfig, WindowBindingConfig {
  type: string;
  show_sections?: CardSection[];
  compact?: boolean;
  show_compass_stats?: boolean;
  show_compass_legend?: boolean;
  show_moon?: boolean;
  hide_inactive_handlers?: boolean;
  /** Render a plain-English "Why this position?" sentence above the decision
   *  strip's row grid. Defaults to true. */
  show_decision_summary?: boolean;
  north_offset?: number;
  /** Per-overlay color overrides for the embedded sky compass, indexed by
   *  discovery order. Same shape as `SkyCompassCardConfig.cover_colors`. */
  cover_colors?: (string | null)[];
  controls?: {
    integration_enabled?: boolean;
    automatic_control?: boolean;
    reset_manual_override?: boolean;
  };
  /** Card-owned floating tooltip behavior. Defaults: enabled, offset [12,16],
   *  delay 400ms. Set `enabled: false` to use native browser tooltips. */
  tooltips?: TooltipsConfig;
}

export interface AdaptiveCoverTileCardConfig extends LovelaceCardConfig, WindowBindingConfig {
  type: string;
  /** Override the discovered instance title. */
  name?: string;
  /** Override the auto-resolved cover icon (mdi:*). */
  icon?: string;
  /** The cover the tile acts on. With `window` or `entry_id` set it only
   *  picks the cover for the controls (default: the window's covers). On its
   *  own it also binds the tile to the window that controls this cover. */
  cover?: string;
  /** Render the cover's current position to the right of the title. */
  show_position?: boolean;
  /** Render the cover's localized state ("Open" / "Closed" / "Opening" / …)
   *  in the position slot. Combined with `show_position`, renders as
   *  "Open · 12%". Defaults to true. */
  show_state?: boolean;
  /** Render the plain-English decision-summary sentence under the title. */
  show_decision_summary?: boolean;
  /** Render the ↑■▼ controls row (default true). */
  show_controls?: boolean;
  /** Render the cover device's battery % next to the position (default
   *  true; auto-hidden when the cover has no battery sensor). */
  show_battery?: boolean;
  /** Render the contextual badge (default true). Master switch for the tile
   *  badge — `badges` filters within it. */
  show_badge?: boolean;
  /** Per-kind opt-in for the configurable badge kinds. Omitted/undefined =
   *  on; only `=== false` hides. `off` is a state-fallback and is never
   *  filtered by this. */
  badges?: BadgesOptInConfig;
  /** Render the sky compass inside the more-info dialog's Advanced section
   *  (default true). */
  show_compass?: boolean;
  /** Render the "Sun today" elevation chart inside the more-info dialog's
   *  Advanced section (default true). */
  show_elevation_chart?: boolean;
  /** Tile layout. `detailed` (default) stacks title on row 1, an optional
   *  standalone "Auto" indicator on row 2, and state · position + inline winner
   *  badge on row 3, with the controls floating to the right across the rows.
   *  `one-line` is the compact single-row opt-out (no Auto indicator). */
  layout?: 'one-line' | 'detailed';
  /** Tap behavior. When undefined, opens the card's more-info dialog (default).
   *  Otherwise a standard HA `ActionConfig`. Legacy string values
   *  `'dialog'` / `'none'` are still accepted and normalized in setConfig. */
  tap_action?: ActionConfig | 'dialog' | 'none';
  /** Long-press action. Standard HA `ActionConfig`. */
  hold_action?: ActionConfig;
  /** Double-tap action. Standard HA `ActionConfig`. */
  double_tap_action?: ActionConfig;
  /** Card-owned floating tooltip behavior. Defaults: enabled, offset [12,16],
   *  delay 400ms. Set `enabled: false` to use native browser tooltips. */
  tooltips?: TooltipsConfig;
}

export interface SkyCompassCardConfig extends LovelaceCardConfig {
  type: string;
  /** Window keys, one overlay each. Preferred for new configs. */
  windows?: string[];
  /** Cover entity_ids; each resolves to the window that controls it. */
  covers?: string[];
  /** Legacy window keys (config entry ids). Still accepted. Overlays are
   *  drawn in the order `windows`, `covers`, `entry_ids`. */
  entry_ids?: string[];
  title?: string;
  compact?: boolean;
  show_legend?: boolean;
  show_stats?: boolean;
  show_moon?: boolean;
  show_cardinals?: boolean;
  show_blind_spot?: boolean;
  show_sun_path?: boolean;
  show_sunrise_sunset?: boolean;
  show_cover_fill?: boolean;
  show_window_arrow?: boolean;
  /** Render the "Sun today" elevation-vs-time chart below the compass
   *  (default true). The chart always reflects the integration's elevation
   *  limits when present. */
  show_elevation_chart?: boolean;
  cover_colors?: (string | null)[];
  north_offset?: number;
  /** Card-owned floating tooltip behavior. Defaults: enabled, offset [12,16],
   *  delay 400ms. Set `enabled: false` to use native browser tooltips. */
  tooltips?: TooltipsConfig;
}

export interface AdaptiveCoverDecisionCardConfig extends LovelaceCardConfig, WindowBindingConfig {
  type: string;
  /** Optional header rendered above the strip in the card's `ha-card`. */
  title?: string;
  /** Tighter row layout; also forces `hide_inactive_handlers` on. */
  compact?: boolean;
  /** Show only the final (winning) decision-trace step. */
  hide_inactive_handlers?: boolean;
  /** Render the plain-English "Why this position?" summary above the strip's
   *  row grid. Defaults to true. */
  show_decision_summary?: boolean;
  /** Card-owned floating tooltip behavior. Defaults: enabled, offset [12,16],
   *  delay 400ms. Set `enabled: false` to use native browser tooltips. */
  tooltips?: TooltipsConfig;
}

export interface DiscoveredEntities {
  /** The window's stable key: the Position sensor's `window_key` attribute,
   *  which is also the unique_id prefix of every entity of the window. */
  window_key: string;
  /** Same value as `window_key`. Kept for the components that still read it
   *  (a migrated window's key is its old config entry_id). */
  entry_id: string;
  entry_title: string;
  cover_type: 'cover_blind' | 'cover_awning' | 'cover_tilt' | string;
  entities: Partial<Record<EntityRole, string>>;
  /** Cover entity_ids the window controls: the Position sensor's
   *  `cover_entities` / `cover_entity` attributes, or, for an integration that
   *  does not publish them, the keys of `last_moves` / `move_blocked_by`. */
  managed_covers: string[];
  /** HA device the window's entities are attached to. Used to deep-link
   *  into `/config/devices/device/<id>` from the more-info dialog. */
  device_id?: string;
  /** Config entry that owns the Position sensor (registry `config_entry_id`).
   *  Equal to `window_key` today; the house entry once windows are subentries.
   *  Only used to build the settings link, never to find entities. */
  config_entry_id?: string | null;
  /** Config subentry that owns the Position sensor, when the window is a
   *  subentry of the house entry. Null for a window that is its own entry. */
  config_subentry_id?: string | null;
}

/** One rendered decision-strip row, synthesized from the integration's
 *  `decision_trace` string list (see `lib/trace-adapter.ts`). */
export interface DecisionStep {
  /** The raw trace line. */
  handler: string;
  /** True for the final line — the step that produced the winning position. */
  matched: boolean;
  reason: string;
  position: number | null;
}

/**
 * Normalized decision context, synthesized from the Cover Position sensor's
 * attributes by `readTraceAttrs()` (lib/trace-adapter.ts). `winner` is the
 * integration's `intent`; `trace` is its `decision_trace` string list mapped
 * to steps.
 */
export interface DecisionTraceAttributes {
  trace: DecisionStep[];
  /** Final trace line — the immediate reason for the current position. */
  reason: string;
  /** The engine intent (calculated | default | sunset | privacy | …). */
  winner: string;
  sun_azimuth?: number;
  sun_elevation?: number;
  gamma?: number;
  in_field_of_view?: boolean;
  default_position?: number;
  sunset_position?: number;
}

export interface ForecastSample {
  t: string;
  position: number;
  /** The engine intent active at this sample. */
  handler: string;
}

export interface ForecastEvent {
  t: string;
  /** Intent that begins at this boundary. */
  kind: string;
  label: string;
}

export interface PositionForecastAttributes {
  forecast: ForecastSample[];
  events: ForecastEvent[];
}

/**
 * The `sun` attribute block on the Cover Position sensor — solar geometry for
 * the sky compass / elevation chart.
 */
export interface SunPositionAttributes {
  azimuth: number;
  elevation: number;
  gamma: number;
  in_fov: boolean;
  window_azimuth: number;
  fov_left: number;
  fov_right: number;
  min_elevation?: number;
  max_elevation?: number;
  /** Not exposed by the integration (blind-spot is azimuth-relative config);
   *  kept optional so the compass code path stays. */
  blind_spot_range?: [number, number];
}

/**
 * Raw attributes on the integration's Cover Position sensor. The sensor STATE
 * is the target position (0–100 %).
 */
export interface CoverPositionAttributes {
  /** The window's stable key (== the unique_id prefix of its entities). */
  window_key?: string;
  /** The cover entity the window controls. */
  cover_entity?: string | null;
  /** Every cover the window controls, when it controls more than one. */
  cover_entities?: string[] | null;
  /** The window's blind type: cover_blind | cover_awning | cover_tilt. */
  cover_type?: string | null;
  /** When the active manual override expires (ISO), or null. */
  override_until?: string | null;
  /** The next scheduled move, or null. */
  next_move?: { time: string; position: number } | null;
  /** Engine intent: calculated | default | sunset | privacy | admit_no_glare |
   *  shaded_by_overhang | climate_* */
  intent?: string | null;
  /** Human-readable trace lines; the last line is the winning step. */
  decision_trace?: string[] | null;
  /** Change-points for today: [{time: ISO local, position, intent}, ...]. */
  forecast_today?: Array<{ time: string; position: number; intent: string }> | null;
  /** Map cover entity_id → gate name currently blocking a move. */
  move_blocked_by?: Record<string, string>;
  /** Map cover entity_id → formatted "HH:MM -> 37% (source: reason)" line. */
  last_moves?: Record<string, string>;
  default?: number;
  sunset_default?: number;
  sunset_offset?: number;
  azimuth_window?: number;
  field_of_view?: [number, number];
  blind_spot?: number | null;
  sun?: SunPositionAttributes;
}
