import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant, LovelaceCardEditor } from 'custom-card-helpers';

import { SKY_COMPASS_CARD_EDITOR_NAME, SKY_COMPASS_CARD_NAME } from './const';
import { fetchWindowOptions, type WindowOption } from './lib/window-options';
import {
  windowRefId,
  windowRefLabel,
  windowRefsFromConfig,
  type WindowRef,
} from './lib/window-binding';
import { renderEditorFooter } from './lib/editor-footer';
import { colorForIndex } from './lib/palette';
import { t } from './lib/i18n';
import type { SkyCompassCardConfig } from './types';

type ToggleKey =
  | 'compact'
  | 'show_legend'
  | 'show_stats'
  | 'show_moon'
  | 'show_cardinals'
  | 'show_blind_spot'
  | 'show_sun_path'
  | 'show_sunrise_sunset'
  | 'show_cover_fill'
  | 'show_window_arrow'
  | 'show_elevation_chart';

interface ToggleRow {
  key: ToggleKey;
  labelKey: string;
  descKey: string;
  defaultOn: boolean;
}

const TOGGLE_ROWS: ToggleRow[] = [
  {
    key: 'compact',
    labelKey: 'editor.compass.toggle_compact_label',
    descKey: 'editor.compass.toggle_compact_desc',
    defaultOn: false,
  },
  {
    key: 'show_legend',
    labelKey: 'editor.compass.toggle_legend_label',
    descKey: 'editor.compass.toggle_legend_desc',
    defaultOn: true,
  },
  {
    key: 'show_stats',
    labelKey: 'editor.compass.toggle_stats_label',
    descKey: 'editor.compass.toggle_stats_desc',
    defaultOn: true,
  },
  {
    key: 'show_moon',
    labelKey: 'editor.compass.toggle_moon_label',
    descKey: 'editor.compass.toggle_moon_desc',
    defaultOn: false,
  },
  {
    key: 'show_cardinals',
    labelKey: 'editor.compass.toggle_cardinals_label',
    descKey: 'editor.compass.toggle_cardinals_desc',
    defaultOn: true,
  },
  {
    key: 'show_blind_spot',
    labelKey: 'editor.compass.toggle_blind_spot_label',
    descKey: 'editor.compass.toggle_blind_spot_desc',
    defaultOn: true,
  },
  {
    key: 'show_sun_path',
    labelKey: 'editor.compass.toggle_sun_path_label',
    descKey: 'editor.compass.toggle_sun_path_desc',
    defaultOn: true,
  },
  {
    key: 'show_sunrise_sunset',
    labelKey: 'editor.compass.toggle_sunrise_sunset_label',
    descKey: 'editor.compass.toggle_sunrise_sunset_desc',
    defaultOn: true,
  },
  {
    key: 'show_cover_fill',
    labelKey: 'editor.compass.toggle_cover_fill_label',
    descKey: 'editor.compass.toggle_cover_fill_desc',
    defaultOn: true,
  },
  {
    key: 'show_window_arrow',
    labelKey: 'editor.compass.toggle_window_arrow_label',
    descKey: 'editor.compass.toggle_window_arrow_desc',
    defaultOn: true,
  },
  {
    key: 'show_elevation_chart',
    labelKey: 'editor.compass.toggle_elevation_chart_label',
    descKey: 'editor.compass.toggle_elevation_chart_desc',
    defaultOn: true,
  },
];

@customElement(SKY_COMPASS_CARD_EDITOR_NAME)
export class AdaptiveCoverSkyCompassCardEditor extends LitElement implements LovelaceCardEditor {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @state() private _config?: SkyCompassCardConfig;
  @state() public _windows: WindowOption[] | null = null;
  @state() private _windowsError: string | null = null;
  private _fetchInFlight = false;

  public setConfig(config: SkyCompassCardConfig): void {
    this._config = config;
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('hass') && this.hass && !this._windows && !this._fetchInFlight) {
      this._fetchInFlight = true;
      fetchWindowOptions(this.hass)
        .then((windows) => {
          this._windows = windows;
          this._windowsError = null;
        })
        .catch((err: Error) => {
          this._windowsError = err?.message ?? 'failed to load windows';
        })
        .finally(() => {
          this._fetchInFlight = false;
        });
    }
  }

  private _emit(next: SkyCompassCardConfig): void {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _baseConfig(): SkyCompassCardConfig {
    return this._config ?? { type: `custom:${SKY_COMPASS_CARD_NAME}`, windows: [] };
  }

  private _trimColors(arr: (string | null)[]): (string | null)[] | undefined {
    let last = -1;
    for (let i = 0; i < arr.length; i++) if (arr[i]) last = i;
    if (last < 0) return undefined;
    return arr.slice(0, last + 1);
  }

  private _emitWithColors(
    base: SkyCompassCardConfig,
    colors: (string | null)[],
    overrides?: Partial<SkyCompassCardConfig>,
  ): void {
    const trimmed = this._trimColors(colors);
    const { cover_colors: _cc, ...rest } = base;
    void _cc;
    const next: SkyCompassCardConfig = trimmed
      ? { ...(rest as SkyCompassCardConfig), ...overrides, cover_colors: trimmed }
      : { ...(rest as SkyCompassCardConfig), ...overrides };
    this._emit(next);
  }

  private _onCoverColorChange(index: number, value: string): void {
    const base = this._baseConfig();
    const colors: (string | null)[] = [...(base.cover_colors ?? [])];
    while (colors.length <= index) colors.push(null);
    colors[index] = value;
    this._emitWithColors(base, colors);
  }

  private _onCoverColorReset(index: number): void {
    const base = this._baseConfig();
    const colors: (string | null)[] = [...(base.cover_colors ?? [])];
    if (index < colors.length) colors[index] = null;
    this._emitWithColors(base, colors);
  }

  /** Window keys the config selects: `windows` plus legacy `entry_ids`. */
  private _selectedKeys(cfg: SkyCompassCardConfig): string[] {
    return [...(cfg.windows ?? []), ...(cfg.entry_ids ?? [])];
  }

  /**
   * Toggle one window. The selection is saved as `windows:` in picker order and
   * a legacy `entry_ids` list is folded into it; `covers` is left alone.
   */
  private _onWindowToggle(key: string, enabled: boolean): void {
    const base = this._baseConfig();
    const current = new Set(this._selectedKeys(base));
    if (enabled) current.add(key);
    else current.delete(key);
    // Preserve picker order for consistency.
    const ordered = (this._windows ?? []).map((w) => w.window_key).filter((k) => current.has(k));
    const next: SkyCompassCardConfig = { ...base, windows: ordered };
    delete next.entry_ids;
    // Re-align cover_colors (indexed by overlay order) to the new order. A
    // legacy entry_id and the same key under `windows` share an id.
    const oldOrder = windowRefsFromConfig(base).map(windowRefId);
    const oldColors = base.cover_colors ?? [];
    const newColors: (string | null)[] = windowRefsFromConfig(next).map((ref) => {
      const oldIdx = oldOrder.indexOf(windowRefId(ref));
      return oldIdx >= 0 ? (oldColors[oldIdx] ?? null) : null;
    });
    this._emitWithColors(next, newColors);
  }

  /** Display name of an overlay in the color list. */
  private _refTitle(ref: WindowRef): string {
    if (ref.kind === 'cover') {
      const name = this.hass?.states?.[ref.entity_id]?.attributes?.friendly_name;
      return typeof name === 'string' && name ? name : ref.entity_id;
    }
    return this._windows?.find((w) => w.window_key === ref.key)?.title ?? windowRefLabel(ref);
  }

  private _onToggle(key: ToggleKey, enabled: boolean): void {
    this._emit({ ...this._baseConfig(), [key]: enabled });
  }

  _onNorthOffsetChange(e: Event): void {
    const raw = parseFloat((e.target as HTMLInputElement).value);
    const value = Number.isFinite(raw) ? raw : 0;
    this._emit({ ...this._baseConfig(), north_offset: value });
  }

  private _onTitleChange(e: Event): void {
    const value = (e.target as HTMLInputElement).value;
    const base = this._baseConfig();
    if (value) this._emit({ ...base, title: value });
    else {
      const { title: _title, ...rest } = base;
      void _title;
      this._emit(rest as SkyCompassCardConfig);
    }
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this._config) return nothing;
    const selected = new Set(this._selectedKeys(this._config));
    const overlays = windowRefsFromConfig(this._config);
    return html`
      <div class="form">
        <div class="section">
          <label class="field-label">${t('editor.compass.instances')}</label>
          <div class="hint">${t('editor.compass.instances_hint')}</div>
          ${this._renderWindowPicker(selected)}
        </div>

        <div class="section">
          <label class="field-label">${t('editor.common.title_optional')}</label>
          <input
            type="text"
            class="text-input"
            .value=${this._config.title ?? ''}
            placeholder=${t('editor.common.title_placeholder')}
            @change=${this._onTitleChange}
          />
        </div>

        ${overlays.length > 0
          ? html`
              <div class="section">
                <label class="field-label">${t('editor.compass.cover_colors')}</label>
                <div class="hint">${t('editor.compass.cover_colors_hint')}</div>
                ${overlays.map((ref, i) => {
                  const override = this._config!.cover_colors?.[i] ?? null;
                  const resolved = override ?? colorForIndex(i);
                  return html`
                    <div class="color-row">
                      <input
                        type="color"
                        .value=${resolved}
                        @change=${(e: Event) =>
                          this._onCoverColorChange(i, (e.target as HTMLInputElement).value)}
                      />
                      <span class="toggle-text">
                        <span class="toggle-label">${this._refTitle(ref)}</span>
                        <span class="toggle-desc"
                          >${override ? override : t('editor.compass.default_color')}</span
                        >
                      </span>
                      <button
                        type="button"
                        class="reset-btn"
                        ?disabled=${!override}
                        @click=${() => this._onCoverColorReset(i)}
                      >
                        ${t('editor.common.reset')}
                      </button>
                    </div>
                  `;
                })}
              </div>
            `
          : nothing}

        <div class="section">
          <label class="field-label">${t('editor.compass.display')}</label>
          ${TOGGLE_ROWS.map(
            (row) => html`
              <label class="toggle-row">
                <input
                  type="checkbox"
                  .checked=${((this._config as Record<string, unknown>)[row.key] as boolean) ??
                  row.defaultOn}
                  @change=${(e: Event) =>
                    this._onToggle(row.key, (e.target as HTMLInputElement).checked)}
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

  private _renderWindowPicker(selected: Set<string>): TemplateResult {
    if (this._windowsError) {
      return html`<div class="error">
        ${t('editor.common.load_failed', { error: this._windowsError })}
      </div>`;
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
      <div class="entry-list">
        ${this._windows.map(
          (w) => html`
            <label class="toggle-row">
              <input
                type="checkbox"
                .checked=${selected.has(w.window_key)}
                @change=${(evt: Event) =>
                  this._onWindowToggle(w.window_key, (evt.target as HTMLInputElement).checked)}
              />
              <span class="toggle-text">
                <span class="toggle-label">${w.title}</span>
                <span class="toggle-desc">${w.cover ?? w.window_key}</span>
              </span>
            </label>
          `,
        )}
      </div>
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
    .entry-list {
      display: flex;
      flex-direction: column;
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
