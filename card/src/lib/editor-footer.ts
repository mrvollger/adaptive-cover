import { html, type TemplateResult } from 'lit';
import type { HomeAssistant } from 'custom-card-helpers';

import { CARD_VERSION } from '../const';
import { t } from './i18n';

/**
 * Shared editor footer: card version only. No third-party links or badges —
 * the editor makes zero external network calls.
 * Relies on each editor's existing `.version-footer` / `.dim` style rules for
 * the version text.
 */
export function renderEditorFooter(hass: HomeAssistant): TemplateResult {
  return html`
    <div
      class="editor-footer"
      style="display:flex;align-items:center;justify-content:flex-end;gap:8px;"
    >
      <span class="version-footer dim">
        ${t('root.footer_version', hass, { version: CARD_VERSION })}
      </span>
    </div>
  `;
}
