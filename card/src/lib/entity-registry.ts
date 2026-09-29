import type { HomeAssistant } from 'custom-card-helpers';
import type { RegistryEventPayload } from './registry-diff';

/**
 * Minimum shape we need from the HA entity registry.
 *
 * Available via websocket `config/entity_registry/list`. These full entries
 * include `unique_id` and `platform`, which the frontend's `hass.entities`
 * *display* registry does not expose. We need unique_id to identify ACP
 * entities deterministically (see `const.ts` → UNIQUE_ID_ROLES).
 *
 * `config_entry_id` / `config_subentry_id` are read only to build the settings
 * link. Discovery never filters on them: once windows are subentries of one
 * house entry, every window shares the same `config_entry_id`.
 */
export interface EntityRegistryEntry {
  entity_id: string;
  unique_id: string;
  platform: string;
  config_entry_id: string | null;
  /** Set when the entity belongs to a config subentry (HA 2025.3+). */
  config_subentry_id?: string | null;
  device_id: string | null;
  /** Non-null when the entity is disabled. */
  disabled_by?: string | null;
  translation_key?: string | null;
}

type HassWithConnection = HomeAssistant & {
  connection: {
    subscribeEvents: (
      callback: (ev: { data: RegistryEventPayload }) => void,
      event: string,
    ) => Promise<() => void>;
  };
};

/** One-shot fetch of the full entity registry. */
export async function fetchEntityRegistry(hass: HomeAssistant): Promise<EntityRegistryEntry[]> {
  return hass.callWS<EntityRegistryEntry[]>({ type: 'config/entity_registry/list' });
}

/**
 * Subscribe to `entity_registry_updated` events. The callback fires on any
 * add/remove/update; the caller should re-fetch the registry.
 *
 * Returns a synchronous teardown function that, when called, unsubscribes
 * once the underlying async subscription resolves. Safe to call before the
 * subscription promise resolves — we'll still unsubscribe when it does.
 */
export function subscribeEntityRegistry(
  hass: HomeAssistant,
  onChange: (payload: RegistryEventPayload) => void,
): () => void {
  const h = hass as HassWithConnection;
  let unsubFn: (() => void) | null = null;
  let cancelled = false;

  h.connection
    .subscribeEvents(
      (ev: { data: RegistryEventPayload }) => onChange(ev.data),
      'entity_registry_updated',
    )
    .then((unsub) => {
      if (cancelled) unsub();
      else unsubFn = unsub;
    })
    .catch(() => {
      // Swallow — subscription failure just means the card won't auto-refresh on
      // entity registry changes. Manual reload still works.
    });

  return () => {
    cancelled = true;
    if (unsubFn) unsubFn();
  };
}
