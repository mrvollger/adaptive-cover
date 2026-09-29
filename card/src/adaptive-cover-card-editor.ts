import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant, LovelaceCardEditor } from 'custom-card-helpers';

import { CARD_EDITOR_NAME } from './const';
import type { ControlFlags } from './const';
import { fetchWindowOptions, type WindowOption } from './lib/window-options';
import { configuredWindowKey, withWindowKey } from './lib/window-binding';
import { renderEditorFooter } from './lib/editor-footer';
import { colorForIndex } from './lib/palette';
import { t } from './lib/i18n';
import type { AdaptiveCoverCardConfig, CardSection } from './types';

interface SectionRow {
  key: CardSection;
  labelKey: string;
  descKey: string;
  /** Whether the section is on when `show_sections` is unset. Defaults to true;
   *  set false for opt-in diagnostic sections so the toggle still lists but
   *  starts unchecked. Must mirror the card's own `DEFAULT_SECTIONS`. */
  enabledByDefault?: boolean;
}

const SECTION_ROWS: SectionRow[] = [
  {
    key: 'sky',
    labelKey: 'editor.main.section_sky_label',
    descKey: 'editor.main.section_sky_desc',
  },
  {
    key: 'elevation',
    labelKey: 'editor.main.section_elevation_label',
    descKey: 'editor.main.section_elevation_desc',
  },
  {
    key: 'decision',
    labelKey: 'editor.main.section_decision_label',
    descKey: 'editor.main.section_decision_desc',
  },
  {
    key: 'covers',
    labelKey: 'editor.main.section_covers_label',
    descKey: 'editor.main.section_covers_desc',
  },
  {
    key: 'overrides',
    labelKey: 'editor.main.section_overrides_label',
    descKey: 'editor.main.section_overrides_desc',
  },
  {
    key: 'climate',
    labelKey: 'editor.main.section_climate_label',
    descKey: 'editor.main.section_climate_desc',
  },
];

// Mirrors the card's own DEFAULT_SECTIONS: opt-in rows (enabledByDefault: false)
// are excluded so an unset `show_sections` omits them.
const DEFAULT_SECTIONS: CardSection[] = SECTION_ROWS.filter(
  (r) => r.enabledByDefault !== false,
).map((r) => r.key);

@customElement(CARD_EDITOR_NAME)
export class AdaptiveCoverCardEditor extends LitElement implements LovelaceCardEditor {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _config?: AdaptiveCoverCardConfig;
  @state() public _windows: WindowOption[] | null = null;
  @state() private _windowsError: string | null = null;
  private _fetchInFlight = false;

  public setConfig(config: AdaptiveCoverCardConfig): void {
    this._config = config;
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('hass') && this.hass && !this._windows && !this._fetchInFlight) {
      this._fetchInFlight = true;
      fetchWindowOptions(this.hass)
        .then((windows) => {
          this._windows = windows;
          this._windowsError = null;
          const bound = this._config?.window || this._config?.entry_id || this._config?.cover;
          if (!bound && windows.length === 1) {
            // Single window → auto-select.
            this._emit(withWindowKey(this._config ?? { type: '' }, windows[0].window_key));
          }
        })
        .catch((err: Error) => {
          this._windowsError = err?.message ?? 'failed to load windows';
        })
        .finally(() => {
          this._fetchInFlight = false;
        });
    }
  }

  private get _currentSections(): CardSection[] {
    return this._config?.show_sections ?? DEFAULT_SECTIONS;
  }

  private _emit(next: AdaptiveCoverCardConfig): void {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** A picked window is saved as `window:`; a legacy `entry_id` is dropped. */
  private _onWindowChange(e: Event): void {
    const value = (e.target as HTMLSelectElement).value;
    if (value === configuredWindowKey(this._config)) return;
    this._emit(withWindowKey(this._config ?? { type: '' }, value));
  }

  private _onSectionToggle(key: CardSection, enabled: boolean): void {
    const current = new Set(this._currentSections);
    if (enabled) current.add(key);
    else current.delete(key);
    // Preserve SECTION_ROWS ordering for consistency
    const ordered = SECTION_ROWS.map((r) => r.key).filter((k) => current.has(k));
    this._emit({ ...(this._config ?? { type: '' }), show_sections: ordered });
  }

  private _onCompactToggle(enabled: boolean): void {
    this._emit({ ...(this._config ?? { type: '' }), compact: enabled });
  }

  private _onCompassStatsToggle(enabled: boolean): void {
    this._emit({ ...(this._config ?? { type: '' }), show_compass_stats: enabled });
  }

  private _onCompassLegendToggle(enabled: boolean): void {
    this._emit({ ...(this._config ?? { type: '' }), show_compass_legend: enabled });
  }

  private _onMoonToggle(enabled: boolean): void {
    this._emit({ ...(this._config ?? { type: '' }), show_moon: enabled });
  }

  private _onHideInactiveToggle(enabled: boolean): void {
    this._emit({
      ...(this._config ?? { type: '' }),
      hide_inactive_handlers: enabled,
    });
  }

  _onNorthOffsetChange(e: Event): void {
    const raw = parseFloat((e.target as HTMLInputElement).value);
    const value = Number.isFinite(raw) ? raw : 0;
    this._emit({ ...(this._config ?? { type: '' }), north_offset: value });
  }

  private _onControlToggle(key: keyof ControlFlags, enabled: boolean): void {
    const cfg = this._config ?? { type: '' };
    this._emit({ ...cfg, controls: { ...cfg.controls, [key]: enabled } });
  }

  // The main card embeds a single sky-compass overlay, so cover colors are a
  // single slot bound to index 0 of the cover_colors array.
  private _onCoverColorChange(value: string): void {
    const cfg = this._config ?? { type: '' };
    this._emit({ ...cfg, cover_colors: [value] });
  }

  private _onCoverColorReset(): void {
    const cfg = { ...(this._config ?? { type: '' }) };
    delete (cfg as { cover_colors?: unknown }).cover_colors;
    this._emit(cfg);
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this._config) return nothing;
    const activeSections = new Set(this._currentSections);

    return html`
      <div class="form">
        <div class="section">
          <label class="field-label">${t('editor.common.window')}</label>
          ${this._renderWindowPicker()}
        </div>

        <div class="section">
          <label class="field-label">${t('editor.main.sections')}</label>
          <div class="hint">${t('editor.main.sections_hint')}</div>
          ${SECTION_ROWS.map(
            (row) => html`
              <label class="toggle-row">
                <input
                  type="checkbox"
                  .checked=${activeSections.has(row.key)}
                  @change=${(e: Event) =>
                    this._onSectionToggle(row.key, (e.target as HTMLInputElement).checked)}
                />
                <span class="toggle-text">
                  <span class="toggle-label">${t(row.labelKey)}</span>
                  <span class="toggle-desc">${t(row.descKey)}</span>
                </span>
              </label>
            `,
          )}
        </div>

        <div class="section">
          <label class="field-label">${t('editor.main.controls')}</label>
          <div class="hint">${t('editor.main.controls_hint')}</div>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.integration_enabled ?? true}
              @change=${(e: Event) =>
                this._onControlToggle(
                  'integration_enabled',
                  (e.target as HTMLInputElement).checked,
                )}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.integration_pill_label')}</span>
              <span class="toggle-desc">${t('editor.main.integration_pill_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.automatic_control ?? true}
              @change=${(e: Event) =>
                this._onControlToggle('automatic_control', (e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.automatic_pill_label')}</span>
              <span class="toggle-desc">${t('editor.main.automatic_pill_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.controls?.reset_manual_override ?? true}
              @change=${(e: Event) =>
                this._onControlToggle(
                  'reset_manual_override',
                  (e.target as HTMLInputElement).checked,
                )}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.reset_button_label')}</span>
              <span class="toggle-desc">${t('editor.main.reset_button_desc')}</span>
            </span>
          </label>
        </div>

        ${configuredWindowKey(this._config) || this._config.cover
          ? html`
              <div class="section">
                <label class="field-label">${t('editor.compass.cover_colors')}</label>
                <div class="hint">${t('editor.compass.cover_colors_hint')}</div>
                ${(() => {
                  const override = this._config!.cover_colors?.[0] ?? null;
                  const resolved = override ?? colorForIndex(0);
                  return html`
                    <div class="color-row">
                      <input
                        type="color"
                        .value=${resolved}
                        @change=${(e: Event) =>
                          this._onCoverColorChange((e.target as HTMLInputElement).value)}
                      />
                      <span class="toggle-text">
                        <span class="toggle-desc"
                          >${override ? override : t('editor.compass.default_color')}</span
                        >
                      </span>
                      <button
                        type="button"
                        class="reset-btn"
                        ?disabled=${!override}
                        @click=${() => this._onCoverColorReset()}
                      >
                        ${t('editor.common.reset')}
                      </button>
                    </div>
                  `;
                })()}
              </div>
            `
          : nothing}

        <div class="section">
          <label class="field-label">${t('editor.main.display')}</label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.compact ?? false}
              @change=${(e: Event) => this._onCompactToggle((e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.compact_label')}</span>
              <span class="toggle-desc">${t('editor.main.compact_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_compass_stats ?? true}
              @change=${(e: Event) =>
                this._onCompassStatsToggle((e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.show_compass_stats_label')}</span>
              <span class="toggle-desc">${t('editor.main.show_compass_stats_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_compass_legend ?? true}
              @change=${(e: Event) =>
                this._onCompassLegendToggle((e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.show_compass_legend_label')}</span>
              <span class="toggle-desc">${t('editor.main.show_compass_legend_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.show_moon ?? false}
              @change=${(e: Event) => this._onMoonToggle((e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.show_moon_label')}</span>
              <span class="toggle-desc">${t('editor.main.show_moon_desc')}</span>
            </span>
          </label>
          <label class="toggle-row">
            <input
              type="checkbox"
              .checked=${this._config.hide_inactive_handlers ?? false}
              @change=${(e: Event) =>
                this._onHideInactiveToggle((e.target as HTMLInputElement).checked)}
            />
            <span class="toggle-text">
              <span class="toggle-label">${t('editor.main.hide_inactive_label')}</span>
              <span class="toggle-desc">${t('editor.main.hide_inactive_desc')}</span>
            </span>
          </label>
        </div>

        <div class="section">
          <label class="field-label">${t('editor.common.north_offset')}</label>
          <div class="hint">${t('editor.common.north_offset_hint')}</div>
          <input
            type="number"
            class="text-input"
            .value=${String(this._config.north_offset ?? 0)}
            step="1"
            inputmode="numeric"
            @change=${this._onNorthOffsetChange}
          />
        </div>
        ${renderEditorFooter()}
      </div>
    `;
  }

  private _renderWindowPicker(): TemplateResult {
    const current = configuredWindowKey(this._config);
    if (this._windowsError) {
      return html`
        <div class="error">${t('editor.common.load_failed', { error: this._windowsError })}</div>
        <input
          type="text"
          .value=${current}
          placeholder=${t('editor.common.window_manual_placeholder')}
          @change=${this._onWindowChange}
          class="text-input"
        />
      `;
    }
    if (!this._windows) {
      return html`<div class="hint">${t('editor.common.loading_entries')}</div>`;
    }
    if (this._windows.length === 0) {
      return html`
        <div class="error">
          ${t('editor.common.no_entries')}
          <code>${t('editor.common.no_entries_path')}</code>${t('editor.common.no_entries_then')}
        </div>
      `;
    }
    return html`
      <select class="select" .value=${current} @change=${this._onWindowChange}>
        ${current && !this._windows.some((w) => w.window_key === current)
          ? html`<option value=${current}>
              ${t('editor.common.unknown_entry', { entry: current })}
            </option>`
          : nothing}
        ${this._windows.map(
          (w) => html`
            <option value=${w.window_key} ?selected=${w.window_key === current}>${w.title}</option>
          `,
        )}
      </select>
    `;
  }

  public static styles = css`
    :host {
      display: block;
    }
    .form {
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 8px 0;
    }
    .section {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field-label {
      font-weight: 500;
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .hint {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .error {
      font-size: 0.82rem;
      color: var(--error-color, crimson);
    }
    .select,
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
    .select:focus,
    .text-input:focus {
      outline: none;
      border-color: var(--primary-color);
    }
    .toggle-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 6px 0;
      cursor: pointer;
    }
    .toggle-row input[type='checkbox'] {
      margin-top: 3px;
      accent-color: var(--primary-color);
      width: 16px;
      height: 16px;
    }
    .toggle-text {
      display: flex;
      flex-direction: column;
    }
    .toggle-label {
      font-size: 0.88rem;
      color: var(--primary-text-color);
    }
    .toggle-desc {
      font-size: 0.74rem;
      color: var(--secondary-text-color);
    }
    .color-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 0;
    }
    .color-row input[type='color'] {
      width: 32px;
      height: 32px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 2px;
      background: none;
      cursor: pointer;
      flex-shrink: 0;
    }
    .color-row .toggle-text {
      flex: 1;
    }
    .reset-btn {
      background: none;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      cursor: pointer;
      flex-shrink: 0;
    }
    .reset-btn:disabled {
      opacity: 0.35;
      cursor: default;
    }
    code {
      background: var(--code-editor-background-color, rgba(0, 0, 0, 0.08));
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 0.85em;
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
