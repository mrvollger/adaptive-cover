import type { HomeAssistant } from 'custom-card-helpers';
import { INTEGRATION_DOMAIN } from '../const';
import { listWindows, type WindowOption } from './entity-discovery';
import { loadEntityRegistry } from './registry-store';

export type { WindowOption };

interface RawConfigEntry {
  entry_id: string;
  title: string;
  domain: string;
}

/**
 * Config entry titles by entry_id, used only as a fallback window title when
 * the window has no device name. Best effort: resolves to `{}` on failure.
 */
async function fetchEntryTitles(hass: HomeAssistant): Promise<Record<string, string>> {
  try {
    const entries = await hass.callWS<RawConfigEntry[]>({
      type: 'config_entries/get',
      domain: INTEGRATION_DOMAIN,
    });
    const titles: Record<string, string> = {};
    for (const e of Array.isArray(entries) ? entries : []) {
      if (e?.domain === INTEGRATION_DOMAIN && e.entry_id && e.title) titles[e.entry_id] = e.title;
    }
    return titles;
  } catch {
    return {};
  }
}

/**
 * The windows the card editors and card-picker stubs offer, from the entity
 * registry: one per enabled adaptive_cover Position sensor, keyed by window
 * key (not by config entry, so it keeps working when windows become
 * subentries of one house entry). Rejects when the registry fetch fails.
 */
export async function fetchWindowOptions(hass: HomeAssistant): Promise<WindowOption[]> {
  const [registry, titles] = await Promise.all([loadEntityRegistry(hass), fetchEntryTitles(hass)]);
  return listWindows(hass, Array.isArray(registry) ? registry : [], titles);
}
