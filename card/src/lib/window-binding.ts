import type { SkyCompassCardConfig, WindowBindingConfig } from '../types';

/**
 * How a card names the window it shows.
 *
 * - `window`: the window key (the Position sensor's `window_key` attribute and
 *   the unique_id prefix of every entity of the window).
 * - `cover`: a cover entity; it resolves to the window that controls it.
 * - `entry`: a legacy `entry_id:` config. A migrated window's key is its old
 *   config entry_id, so this resolves exactly like `window`.
 */
export type WindowRef =
  | { kind: 'window'; key: string }
  | { kind: 'cover'; entity_id: string }
  | { kind: 'entry'; key: string };

function nonEmpty(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

/**
 * The window a single-window card config binds to, or null when it names none.
 *
 * Precedence: `window`, then `entry_id`, then `cover`. A tile that sets
 * `entry_id` (or `window`) together with `cover` stays bound to that window and
 * uses `cover` only to pick the cover its controls act on.
 */
export function windowRefFromConfig(cfg: WindowBindingConfig | null | undefined): WindowRef | null {
  if (!cfg) return null;
  if (nonEmpty(cfg.window)) return { kind: 'window', key: cfg.window };
  if (nonEmpty(cfg.entry_id)) return { kind: 'entry', key: cfg.entry_id };
  if (nonEmpty(cfg.cover)) return { kind: 'cover', entity_id: cfg.cover };
  return null;
}

/**
 * The windows a multi-window card (sky compass) shows, in overlay order:
 * `windows`, then `covers`, then legacy `entry_ids`. Empty strings are skipped.
 */
export function windowRefsFromConfig(
  cfg: Pick<SkyCompassCardConfig, 'windows' | 'covers' | 'entry_ids'> | null | undefined,
): WindowRef[] {
  if (!cfg) return [];
  const refs: WindowRef[] = [];
  for (const key of cfg.windows ?? []) if (nonEmpty(key)) refs.push({ kind: 'window', key });
  for (const id of cfg.covers ?? []) if (nonEmpty(id)) refs.push({ kind: 'cover', entity_id: id });
  for (const key of cfg.entry_ids ?? []) if (nonEmpty(key)) refs.push({ kind: 'entry', key });
  return refs;
}

/**
 * A string id for a ref, for memo and cache keys. `window` and `entry` refs to
 * the same key share one id, because they name the same window.
 */
export function windowRefId(ref: WindowRef): string {
  return ref.kind === 'cover' ? `cover:${ref.entity_id}` : ref.key;
}

/** The text a "not found" message shows for a ref (the key or the cover id). */
export function windowRefLabel(ref: WindowRef): string {
  return ref.kind === 'cover' ? ref.entity_id : ref.key;
}

/**
 * The config with its window binding replaced by `window: key`. Used by the
 * editors when the user picks a window: a legacy `entry_id` is dropped so the
 * config names its window once. `cover` is kept, because on a tile it also
 * picks the cover the controls act on.
 */
export function withWindowKey<T extends WindowBindingConfig>(cfg: T, key: string): T {
  const next = { ...cfg, window: key } as T;
  delete next.entry_id;
  return next;
}

/** The window key a config shows in an editor picker (`window`, else legacy `entry_id`). */
export function configuredWindowKey(cfg: WindowBindingConfig | null | undefined): string {
  if (!cfg) return '';
  if (nonEmpty(cfg.window)) return cfg.window;
  if (nonEmpty(cfg.entry_id)) return cfg.entry_id;
  return '';
}
