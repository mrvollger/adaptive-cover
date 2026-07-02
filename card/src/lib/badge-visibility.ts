import { normalizeHandler } from './decision-summary';
import { BADGE_KINDS_BY_HANDLER, type BadgeKind, type HandlerName } from '../const';
import type { AdaptiveCoverTileCardConfig, DecisionStep } from '../types';

/** Per-kind opt-in flags. Omitted/undefined = on; only `=== false` hides. */
export type BadgesConfig = AdaptiveCoverTileCardConfig['badges'];

/** Inputs that decide whether the "Solar tracking" badge shows. */
export interface SolarActiveContext {
  /** The winning intent is `calculated` (the engine is tracking the sun). */
  solarMatched: boolean;
}

/**
 * The `solar` badge ("Solar tracking") shows whenever the engine's winning
 * intent is `calculated`.
 */
export function isSolarActive(ctx: SolarActiveContext): boolean {
  return ctx.solarMatched;
}

/**
 * Filter a list of badge kinds down to those that should render, applying the
 * per-badge opt-in uniformly across the tile winner badge and the dialog's
 * badge list.
 *
 * - `solar` survives only when `isSolarActive(ctx)` AND `config.solar !== false`.
 * - the other configurable kinds (including `auto`) survive unless their flag
 *   is `=== false`.
 * - `off` is a state-fallback and is never filtered.
 */
export function selectVisibleBadges(
  kinds: readonly BadgeKind[],
  config: BadgesConfig | undefined,
  ctx: SolarActiveContext,
): BadgeKind[] {
  return kinds.filter((kind) => {
    if (kind === 'off') return true;
    if (kind === 'solar') return isSolarActive(ctx) && config?.solar !== false;
    return config?.[kind] !== false;
  });
}

/**
 * Derive the badge kind for the tile's single winner badge. `winner` is the
 * engine intent; `integrationEnabled` reflects the Toggle Control switch and
 * `manualActive` the manual-override binary sensor.
 */
export function winnerBadgeKind(opts: {
  winner: string;
  integrationEnabled: boolean;
  manualActive: boolean;
}): BadgeKind {
  if (opts.integrationEnabled === false) return 'off';
  if (opts.manualActive) return 'manual';
  const normalized = normalizeHandler(opts.winner) as HandlerName;
  return BADGE_KINDS_BY_HANDLER[normalized] ?? 'auto';
}

/**
 * Resolve the tile's single winner badge kind. With this integration there is
 * no motion handler, so this is {@link winnerBadgeKind} with the off-schedule
 * layer retained for a future `inTimeWindow` signal (currently never emitted).
 */
export function resolveTileBadgeKind(opts: {
  winner: string;
  integrationEnabled: boolean;
  manualActive: boolean;
  badges: BadgesConfig | undefined;
  /** Schedule window active. `false` → automatic positioning paused. The
   *  integration does not currently expose this; `undefined` disables the
   *  layer. */
  inTimeWindow?: boolean;
}): BadgeKind | null {
  const kind = winnerBadgeKind(opts);
  if (
    opts.inTimeWindow === false &&
    opts.badges?.off_schedule !== false &&
    kind !== 'off' &&
    kind !== 'manual'
  ) {
    return 'off_schedule';
  }
  return kind;
}

/**
 * Whether the cover is under active automatic control — the Toggle Control
 * switch is on and no manual override is active. Drives the standalone "Auto"
 * indicator shown alongside the winner badge.
 */
export function isAutoControlActive(opts: {
  winner: string;
  integrationEnabled: boolean;
  automaticControl: boolean;
  manualActive: boolean;
}): boolean {
  if (!opts.integrationEnabled) return false;
  if (!opts.automaticControl) return false;
  if (opts.manualActive) return false;
  return true;
}

/** Build the {@link SolarActiveContext} from a decision trace + winner intent. */
export function buildSolarActiveContext(
  _trace: readonly DecisionStep[] | undefined,
  winner: string,
): SolarActiveContext {
  return {
    solarMatched: normalizeHandler(winner) === 'calculated',
  };
}
