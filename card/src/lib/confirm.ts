import type { HomeAssistant } from 'custom-card-helpers';

import { t } from './i18n';

/**
 * Ask before resuming automatic control. Pressing the integration's reset
 * button doesn't just clear the manual flag — it physically moves the cover
 * back to its calculated position, which is easy to trigger by accident from
 * the badge/panel right after a manual move.
 */
export function confirmResume(hass?: HomeAssistant, targetPosition?: number | null): boolean {
  const msg =
    targetPosition != null && Number.isFinite(targetPosition)
      ? t('overrides.resume_confirm_pos', hass, { position: String(Math.round(targetPosition)) })
      : t('overrides.resume_confirm', hass);
  return window.confirm(msg);
}

/** Current adaptive target of an entry, from its Cover Position sensor. */
export function resumeTarget(
  hass: HomeAssistant | undefined,
  targetSensorId: string | undefined,
): number | null {
  if (!hass || !targetSensorId) return null;
  const v = parseFloat(hass.states[targetSensorId]?.state ?? '');
  return Number.isNaN(v) ? null : v;
}
