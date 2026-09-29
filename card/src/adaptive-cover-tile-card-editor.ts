import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant, LovelaceCardEditor } from 'custom-card-helpers';

import { TILE_CARD_EDITOR_NAME } from './const';
import { fetchWindowOptions, type WindowOption } from './lib/window-options';
import { configuredWindowKey, withWindowKey } from './lib/window-binding';
import { renderEditorFooter } from './lib/editor-footer';
import {
  fetchEntityRegistry,
  subscribeEntityRegistry,
  type EntityRegistryEntry,
} from './lib/entity-registry';
import { discoverEntities } from './lib/entity-discovery';
import { t } from './lib/i18n';
import type { AdaptiveCoverTileCardConfig } from './types';

interface ValueChangedEvent extends CustomEvent {
  detail: { value: AdaptiveCoverTileCardConfig };
}

interface HaFormSchemaItem {
  name: string;
  required?: boolean;
  selector?: Record<string, unknown>;
  // Layout-group containers (ha-form `expandable` / `grid`). When `type` is set
  // the item groups `schema` children instead of binding a selector.
  type?: string;
  title?: string;
  icon?: string;
  expanded?: boolean;
  column_min_width?: string;
  schema?: HaFormSchemaItem[];
}

// Mirror the runtime defaults applied in the tile card so the editor toggles
// reflect actual behavior when a key is omitted from YAML.
// The configurable badge kinds, surfaced as flat `badge_<kind>` boolean fields
// in the form and reassembled into a nested `badges` object on emit. `off` is
// a state-fallback and is never user-configurable.
const BADGE_KINDS = [
  'auto',
  'solar',
  'manual',
  'climate',
  'glare_zone',
  'privacy',
  'sunset',
] as const;

const FORM_DEFAULTS = {
  show_position: true,
  show_state: true,
  show_decision_summary: false,
  show_controls: true,
  show_badge: true,
  show_compass: true,
  show_elevation_chart: true,
  layout: 'detailed',
  // All badges default on; only `=== false` hides.
  badge_auto: true,
  badge_solar: true,
  badge_manual: true,
  badge_climate: true,
  badge_glare_zone: true,
  badge_privacy: true,
  badge_sunset: true,
} as const;

const LABEL_KEYS: Record<string, string> = {
  window: 'editor.common.window',
  name: 'editor.tile.name',
  icon: 'editor.tile.icon',
  cover: 'editor.tile.cover',
  layout: 'editor.tile.layout',
  show_position: 'editor.tile.show_position',
  show_state: 'editor.tile.show_state',
  show_decision_summary: 'editor.tile.show_decision_summary',
  show_controls: 'editor.tile.show_controls',
  show_badge: 'editor.tile.show_badge',
  badge_section: 'editor.tile.badge_section',
  badge_auto: 'editor.tile.badge_auto',
  badge_solar: 'editor.tile.badge_solar',
  badge_manual: 'editor.tile.badge_manual',
  badge_climate: 'editor.tile.badge_climate',
  badge_glare_zone: 'editor.tile.badge_glare_zone',
  badge_privacy: 'editor.tile.badge_privacy',
  badge_sunset: 'editor.tile.badge_sunset',
  show_compass: 'editor.tile.show_compass',
  show_elevation_chart: 'editor.tile.show_elevation_chart',
  tap_action: 'editor.tile.tap_action',
  hold_action: 'editor.tile.hold_action',
  double_tap_action: 'editor.tile.double_tap_action',
};

@customElement(TILE_CARD_EDITOR_NAME)
export class AdaptiveCoverTileCardEditor extends LitElement implements LovelaceCardEditor {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: AdaptiveCoverTileCardConfig;
  @state() public _windows: WindowOption[] | null = null;
  @state() private _windowsError: string | null = null;
  @state() public _registry: EntityRegistryEntry[] | null = null;
  @state() private _managedCovers: string[] = [];

  private _windowsFetchInFlight = false;
  private _registryFetchInFlight = false;
  private _unsubRegistry: (() => void) | null = null;

  public setConfig(config: AdaptiveCoverTileCardConfig): void {
    this._config = { ...config };
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._unsubRegistry) {
      this._unsubRegistry();
      this._unsubRegistry = null;
    }
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('hass') && this.hass) {
      this._ensureWindows();
      this._ensureRegistry();
    }
    if (changed.has('_registry') && this._registry !== null) {
      this._maybePrefillCover();
    }
  }

  private _ensureWindows(): void {
    if (this._windows || this._windowsFetchInFlight) return;
    this._windowsFetchInFlight = true;
    fetchWindowOptions(this.hass)
      .then((windows) => {
        this._windows = windows;
        this._windowsError = null;
        // A new card with a single window to pick from → select it.
        if (!this._hasBinding() && windows.length === 1) {
          this._emit(withWindowKey(this._config ?? { type: '' }, windows[0].window_key));
        }
        this._maybePrefillCover();
      })
      .catch((err: Error) => {
        this._windowsError = err?.message ?? 'failed to load windows';
      })
      .finally(() => {
        this._windowsFetchInFlight = false;
      });
  }

  /** True when the config already names its window (`window`, `entry_id` or `cover`). */
  private _hasBinding(): boolean {
    return !!(this._config?.window || this._config?.entry_id || this._config?.cover);
  }

  private _ensureRegistry(): void {
    if (this._registry === null && !this._registryFetchInFlight) {
      this._registryFetchInFlight = true;
      fetchEntityRegistry(this.hass)
        .then((entries) => {
          this._registry = entries;
          this._maybePrefillCover();
        })
        .catch(() => {
          // Cover picker just falls back to the unfiltered cover domain.
          this._registry = [];
        })
        .finally(() => {
          this._registryFetchInFlight = false;
        });
    }
    if (!this._unsubRegistry) {
      this._unsubRegistry = subscribeEntityRegistry(this.hass, () => {
        this._registryFetchInFlight = true;
        fetchEntityRegistry(this.hass)
          .then((entries) => {
            this._registry = entries;
          })
          .catch(() => {
            // ignore — keep last good value
          })
          .finally(() => {
            this._registryFetchInFlight = false;
          });
      });
    }
  }

  private _emit(next: AdaptiveCoverTileCardConfig): void {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _maybePrefillCover(): void {
    const cfg = this._config;
    if (!cfg || !configuredWindowKey(cfg) || cfg.cover || !this._registry || !this.hass) return;
    const discovered = discoverEntities(this.hass, cfg, this._registry);
    this._managedCovers = discovered?.managed_covers ?? [];
    if (discovered?.managed_covers.length === 1) {
      this._emit({ ...cfg, cover: discovered.managed_covers[0] });
    }
  }

  private _computeLabel = (schema: HaFormSchemaItem): string => {
    const key = LABEL_KEYS[schema.name];
    return key ? t(key) : schema.name;
  };

  private _valueChanged = (e: ValueChangedEvent): void => {
    e.stopPropagation();
    const value = e.detail.value;
    // ha-form passes back the entire form value (including defaults we pre-fill
    // for display). Drop keys that match the default and weren't already in
    // the user's config, so the YAML stays minimal.
    const cleaned: Record<string, unknown> = { ...value };
    for (const [k, def] of Object.entries(FORM_DEFAULTS)) {
      // The flat badge_* fields don't live on _config (they're nested under
      // `badges`), so treat them purely as default-prunable: drop them whenever
      // they equal the default (true). Off badges survive and are reassembled
      // into the nested object below.
      if (k.startsWith('badge_')) {
        if (cleaned[k] === def) delete cleaned[k];
        continue;
      }
      const wasSet = this._config && Object.prototype.hasOwnProperty.call(this._config, k);
      if (!wasSet && cleaned[k] === def) delete cleaned[k];
    }

    // Reassemble the surviving flat badge_<kind>=false fields into a nested
    // `badges` object, and strip the flat keys so they don't leak into YAML.
    const badges: Record<string, boolean> = {};
    for (const k of BADGE_KINDS) {
      const flatKey = `badge_${k}`;
      if (cleaned[flatKey] === false) badges[k] = false;
      delete cleaned[flatKey];
    }

    // The form shows a legacy `entry_id` under the `window` picker. Leave the
    // saved binding alone unless the user picked a different window; a new
    // pick is saved as `window:` and drops the legacy key.
    const picked = cleaned.window;
    delete cleaned.window;

    let next: Record<string, unknown> = {
      ...(this._config ?? { type: '' }),
      ...cleaned,
    };
    if (typeof picked === 'string' && picked && picked !== configuredWindowKey(this._config)) {
      next = withWindowKey(next, picked);
    }
    // Prune the object entirely when all nine badges are on (keeps YAML minimal).
    if (Object.keys(badges).length > 0) next.badges = badges;
    else delete next.badges;

    this._emit(next as AdaptiveCoverTileCardConfig);
  };

  protected render(): TemplateResult | typeof nothing {
    if (!this._config) return nothing;

    if (this._windowsError && !this._windows) {
      // Fall back to the same manual-entry input the main editor uses.
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
    // Flatten the nested `badges` object into `badge_<kind>` form fields. The
    // `badges` key itself is not a form field, so drop it from `data`.
    const { badges, entry_id: _legacyEntryId, ...rest } = this._config;
    void _legacyEntryId;
    const flatBadges: Record<string, boolean> = {};
    for (const k of BADGE_KINDS) {
      if (badges && badges[k] === false) flatBadges[`badge_${k}`] = false;
    }
    // The picker shows the configured window, whether it is saved as `window`
    // or as a legacy `entry_id`.
    const windowKey = configuredWindowKey(this._config);
    const data = {
      ...FORM_DEFAULTS,
      ...rest,
      ...flatBadges,
      ...(windowKey ? { window: windowKey } : {}),
    };

    return html`
      <div class="form">
        <ha-form
          .hass=${this.hass}
          .data=${data}
          .schema=${schema}
          .computeLabel=${this._computeLabel}
          @value-changed=${this._valueChanged}
        ></ha-form>
        ${this._managedCovers.length > 1 && !this._config?.cover
          ? html`<div class="hint">${t('editor.tile.cover_blank_hint')}</div>`
          : nothing}
        ${renderEditorFooter()}
      </div>
    `;
  }

  private _schema(): HaFormSchemaItem[] {
    const windowOptions = this._windowOptions();

    const layoutOptions = [
      { value: 'one-line', label: t('editor.tile.layout_option_one_line') },
      { value: 'detailed', label: t('editor.tile.layout_option_detailed') },
    ];

    // Filter the cover picker to the window's covers once we have the
    // registry and a window. Without those, fall back to any cover.* so the
    // field is still usable.
    let coverSelector: Record<string, unknown> = { entity: { domain: 'cover' } };
    if (this._registry && configuredWindowKey(this._config)) {
      const discovered = discoverEntities(this.hass, this._config, this._registry);
      if (discovered && discovered.managed_covers.length > 0) {
        coverSelector = {
          entity: { domain: 'cover', include_entities: discovered.managed_covers },
        };
      }
    }

    return [
      {
        name: 'window',
        required: !this._config?.cover,
        selector: { select: { options: windowOptions, mode: 'dropdown' } },
      },
      { name: 'name', selector: { text: {} } },
      { name: 'icon', selector: { icon: {} } },
      { name: 'cover', selector: coverSelector },
      {
        name: 'layout',
        selector: { select: { mode: 'list', options: layoutOptions } },
      },
      { name: 'show_position', selector: { boolean: {} } },
      { name: 'show_state', selector: { boolean: {} } },
      { name: 'show_decision_summary', selector: { boolean: {} } },
      { name: 'show_controls', selector: { boolean: {} } },
      { name: 'show_badge', selector: { boolean: {} } },
      {
        // Layout-only container with an empty name so the badge_<kind> booleans
        // stay flat in the form value (ha-form does not nest unnamed groups).
        type: 'expandable',
        name: '',
        title: t('editor.tile.badge_section'),
        icon: 'mdi:label-multiple-outline',
        schema: [
          {
            type: 'grid',
            name: '',
            schema: BADGE_KINDS.map((k) => ({
              name: `badge_${k}`,
              selector: { boolean: {} },
            })),
          },
        ],
      },
      { name: 'show_compass', selector: { boolean: {} } },
      { name: 'show_elevation_chart', selector: { boolean: {} } },
      { name: 'tap_action', selector: { ui_action: {} } },
      { name: 'hold_action', selector: { ui_action: {} } },
      { name: 'double_tap_action', selector: { ui_action: {} } },
    ];
  }

  /** Picker options: every window, plus the configured key when it is not
   *  among them (so a stale key still shows instead of a blank select). */
  private _windowOptions(): Array<{ value: string; label: string }> {
    const options = (this._windows ?? []).map((w) => ({ value: w.window_key, label: w.title }));
    const key = configuredWindowKey(this._config);
    if (key && !options.some((o) => o.value === key)) {
      options.unshift({ value: key, label: t('editor.common.unknown_entry', { entry: key }) });
    }
    return options;
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
    .hint {
      font-size: 0.8rem;
      color: var(--secondary-text-color, #888);
      padding: 4px 0 0;
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
