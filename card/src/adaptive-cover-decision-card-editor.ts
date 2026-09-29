import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant, LovelaceCardEditor } from 'custom-card-helpers';

import { DECISION_CARD_EDITOR_NAME } from './const';
import { fetchWindowOptions, type WindowOption } from './lib/window-options';
import { configuredWindowKey, withWindowKey } from './lib/window-binding';
import { renderEditorFooter } from './lib/editor-footer';
import { t } from './lib/i18n';
import type { AdaptiveCoverDecisionCardConfig } from './types';

interface ValueChangedEvent extends CustomEvent {
  detail: { value: AdaptiveCoverDecisionCardConfig };
}

interface HaFormSchemaItem {
  name: string;
  required?: boolean;
  selector?: Record<string, unknown>;
}

// Mirror the runtime defaults applied in adaptive-cover-decision-card.ts so
// the editor toggles reflect actual behavior when a key is omitted from YAML.
const FORM_DEFAULTS = {
  compact: false,
  hide_inactive_handlers: false,
  show_decision_summary: true,
} as const;

const LABEL_KEYS: Record<string, string> = {
  window: 'editor.common.window',
  title: 'editor.decision.title',
  compact: 'editor.decision.compact_label',
  hide_inactive_handlers: 'editor.decision.hide_inactive_handlers_label',
  show_decision_summary: 'editor.decision.show_decision_summary_label',
};

const HELPER_KEYS: Record<string, string> = {
  compact: 'editor.decision.compact_desc',
  hide_inactive_handlers: 'editor.decision.hide_inactive_handlers_desc',
  show_decision_summary: 'editor.decision.show_decision_summary_desc',
};

@customElement(DECISION_CARD_EDITOR_NAME)
export class AdaptiveCoverDecisionCardEditor extends LitElement implements LovelaceCardEditor {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: AdaptiveCoverDecisionCardConfig;
  @state() public _windows: WindowOption[] | null = null;
  @state() private _windowsError: string | null = null;

  private _windowsFetchInFlight = false;

  public setConfig(config: AdaptiveCoverDecisionCardConfig): void {
    this._config = { ...config };
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('hass') && this.hass) this._ensureWindows();
  }

  private _ensureWindows(): void {
    if (this._windows || this._windowsFetchInFlight) return;
    this._windowsFetchInFlight = true;
    fetchWindowOptions(this.hass)
      .then((windows) => {
        this._windows = windows;
        this._windowsError = null;
        // A new card with a single window to pick from → select it.
        const bound = this._config?.window || this._config?.entry_id || this._config?.cover;
        if (!bound && windows.length === 1) {
          this._emit(withWindowKey(this._config ?? { type: '' }, windows[0].window_key));
        }
      })
      .catch((err: Error) => {
        this._windowsError = err?.message ?? 'failed to load windows';
      })
      .finally(() => {
        this._windowsFetchInFlight = false;
      });
  }

  private _emit(next: AdaptiveCoverDecisionCardConfig): void {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _computeLabel = (schema: HaFormSchemaItem): string => {
    const key = LABEL_KEYS[schema.name];
    return key ? t(key) : schema.name;
  };

  private _computeHelper = (schema: HaFormSchemaItem): string | undefined => {
    const key = HELPER_KEYS[schema.name];
    return key ? t(key) : undefined;
  };

  private _valueChanged = (e: ValueChangedEvent): void => {
    e.stopPropagation();
    const value = e.detail.value;
    // ha-form passes back the entire form value (including defaults we pre-fill
    // for display). Drop keys that match the default and weren't already in the
    // user's config, so the YAML stays minimal.
    const cleaned: Record<string, unknown> = { ...value };
    for (const [k, def] of Object.entries(FORM_DEFAULTS)) {
      const wasSet = this._config && Object.prototype.hasOwnProperty.call(this._config, k);
      if (!wasSet && cleaned[k] === def) delete cleaned[k];
    }

    // The form shows a legacy `entry_id` under the `window` picker. Leave the
    // saved binding alone unless the user picked a different window; a new
    // pick is saved as `window:` and drops the legacy key.
    const picked = cleaned.window;
    delete cleaned.window;
    let next = {
      ...(this._config ?? { type: '' }),
      ...cleaned,
    } as AdaptiveCoverDecisionCardConfig;
    if (typeof picked === 'string' && picked && picked !== configuredWindowKey(this._config)) {
      next = withWindowKey(next, picked);
    }
    this._emit(next);
  };

  protected render(): TemplateResult | typeof nothing {
    if (!this._config) return nothing;

    if (this._windowsError && !this._windows) {
      // Fall back to a manual window-key text input.
      return html`
        <div class="form">
          <div class="error">${t('editor.common.load_failed', { error: this._windowsError })}</div>
          <label class="field-label" for="entry-id-fallback"
            >${t('editor.common.window_fallback_label')}</label
          >
          <input
            id="entry-id-fallback"
            type="text"
            class="text-input"
            .value=${configuredWindowKey(this._config)}
            placeholder=${t('editor.common.window_manual_placeholder')}
            @change=${(e: Event) =>
              this._emit(
                withWindowKey(this._config ?? { type: '' }, (e.target as HTMLInputElement).value),
              )}
          />
          ${renderEditorFooter()}
        </div>
      `;
    }

    const schema = this._schema();
    // The picker shows the configured window, whether it is saved as `window`
    // or as a legacy `entry_id`.
    const { entry_id: _legacyEntryId, ...rest } = this._config;
    void _legacyEntryId;
    const windowKey = configuredWindowKey(this._config);
    const data = { ...FORM_DEFAULTS, ...rest, ...(windowKey ? { window: windowKey } : {}) };

    return html`
      <div class="form">
        <ha-form
          .hass=${this.hass}
          .data=${data}
          .schema=${schema}
          .computeLabel=${this._computeLabel}
          .computeHelper=${this._computeHelper}
          @value-changed=${this._valueChanged}
        ></ha-form>
        ${renderEditorFooter()}
      </div>
    `;
  }

  private _schema(): HaFormSchemaItem[] {
    const windowOptions = (this._windows ?? []).map((w) => ({
      value: w.window_key,
      label: w.title,
    }));
    const key = configuredWindowKey(this._config);
    if (key && !windowOptions.some((o) => o.value === key)) {
      windowOptions.unshift({
        value: key,
        label: t('editor.common.unknown_entry', { entry: key }),
      });
    }
    return [
      {
        name: 'window',
        required: !this._config?.cover,
        selector: { select: { options: windowOptions, mode: 'dropdown' } },
      },
      { name: 'title', selector: { text: {} } },
      { name: 'compact', selector: { boolean: {} } },
      { name: 'hide_inactive_handlers', selector: { boolean: {} } },
      { name: 'show_decision_summary', selector: { boolean: {} } },
    ];
  }

  public static styles = css`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 8px 0;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color);
      font-size: 0.9rem;
      font-family: inherit;
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .version-footer {
      font-size: 0.7rem;
      text-align: right;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `;
}
