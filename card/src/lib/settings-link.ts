import { INTEGRATION_DOMAIN } from '../const';
import type { DiscoveredEntities } from '../types';

/**
 * Where a window's settings live.
 *
 * - `entry`: the window is its own config entry (today). Its settings are that
 *   entry's options flow.
 * - `subentry`: the window is a subentry of the house entry (after the
 *   consolidation). Its settings are that subentry's reconfigure flow.
 */
export type WindowSettingsTarget =
  | { kind: 'entry'; entry_id: string }
  | { kind: 'subentry'; entry_id: string; subentry_id: string };

/** The settings target of a discovered window. */
export function windowSettingsTarget(
  d: Pick<DiscoveredEntities, 'window_key' | 'config_entry_id' | 'config_subentry_id'>,
): WindowSettingsTarget {
  const entryId = d.config_entry_id || d.window_key;
  if (d.config_subentry_id) {
    return { kind: 'subentry', entry_id: entryId, subentry_id: d.config_subentry_id };
  }
  return { kind: 'entry', entry_id: entryId };
}

/**
 * The frontend path that opens a window's settings.
 *
 * HA's integration page reads `#config_entry=<id>`, scrolls to that entry and
 * highlights it; the entry's Configure button opens its options flow. The
 * frontend has no route that opens an options flow or a subentry reconfigure
 * flow directly, so a subentry window links to its house entry (where the
 * subentry is listed) for now. When such a route exists, change only the
 * `subentry` case.
 */
export function windowSettingsPath(target: WindowSettingsTarget): string {
  const page = `/config/integrations/integration/${INTEGRATION_DOMAIN}`;
  switch (target.kind) {
    case 'subentry':
      return `${page}#config_entry=${encodeURIComponent(target.entry_id)}`;
    case 'entry':
      return `${page}#config_entry=${encodeURIComponent(target.entry_id)}`;
  }
}
