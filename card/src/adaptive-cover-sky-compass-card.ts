import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { SKY_COMPASS_CARD_EDITOR_NAME, SKY_COMPASS_CARD_NAME } from './const';
import {
  createDiscoveryListMemo,
  windowRegistrySlice,
  type DiscoveryListResult,
} from './lib/entity-discovery';
import { entityStateChanged } from './lib/hass-change';
import { fetchWindowOptions } from './lib/window-options';
import {
  windowRefId,
  windowRefLabel,
  windowRefsFromConfig,
  type WindowRef,
} from './lib/window-binding';
import { normalizeAzimuth } from './lib/geometry';
import { t } from './lib/i18n';
import { subscribeEntityRegistry, type EntityRegistryEntry } from './lib/entity-registry';
import { loadEntityRegistry, getCachedRegistry } from './lib/registry-store';
import { registryCache } from './lib/registry-cache';
import type { SkyCompassCardConfig } from './types';
import { setTooltipDefaults } from './lib/tooltip';

import './components/sky-compass';
import './components/elevation-chart';
import './adaptive-cover-sky-compass-card-editor';

@customElement(SKY_COMPASS_CARD_NAME)
export class AdaptiveCoverSkyCompassCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: SkyCompassCardConfig;
  @state() private _registry: EntityRegistryEntry[] | null = null;
  @state() private _registryError: string | null = null;

  private _unsubRegistry: (() => void) | null = null;
  private _fetchInFlight = false;

  // Memoized multi-entry discovery → stable `list` array across ticks, so the hosted
  // compass/chart aren't re-rendered by a churning array prop. See createDiscoveryListMemo.
  private _listMemo = createDiscoveryListMemo();
  private _discoveredResult: DiscoveryListResult = { list: [], missing: [] };
  private _refs: WindowRef[] = [];

  public setConfig(config: SkyCompassCardConfig): void {
    const lists = (['windows', 'covers', 'entry_ids'] as const).filter(
      (k) => config?.[k] !== undefined,
    );
    for (const k of lists) {
      const list = config[k];
      if (!Array.isArray(list)) {
        throw new Error(`adaptive-cover-sky-compass-card: \`${k}\` must be an array`);
      }
      if (list.some((id) => typeof id !== 'string' || id.length === 0)) {
        throw new Error(
          `adaptive-cover-sky-compass-card: every \`${k}\` item must be a non-empty string`,
        );
      }
    }
    const refs = windowRefsFromConfig(config);
    if (refs.length === 0) {
      throw new Error(
        'adaptive-cover-sky-compass-card: list at least one window in `windows` ' +
          '(or `covers`, or the legacy `entry_ids`)',
      );
    }
    this._config = { ...config };
    for (const k of lists) this._config[k] = [...config[k]!];
    this._refs = refs;
    if (config.tooltips) setTooltipDefaults(config.tooltips);
    // Warm-start from the persisted ACP slices so a reload skips the Loading state — but
    // only when every configured window is cached, otherwise the missing ones would flash a
    // false "not found" until the shared fetch revalidates.
    if (this._registry === null) {
      const slices = refs.map((ref) => registryCache.get(windowRefId(ref))?.entries);
      if (slices.every((s) => s !== undefined)) {
        this._registry = (slices as EntityRegistryEntry[][]).flat();
      }
    }
  }

  public getCardSize(): number {
    return 4;
  }

  // Sections-layout grid sizing. The card auto-sizes its height to its content
  // (`rows: 'auto'`) so the legend, stats, and elevation chart always fit no
  // matter how many covers are configured — no fixed-height clipping and no
  // scrollbar (issue #146). Full section width with resize bounds.
  public getGridOptions() {
    return {
      columns: 12,
      rows: 'auto',
      min_columns: 6,
      max_columns: 12,
    };
  }

  public static async getConfigElement(): Promise<HTMLElement> {
    return document.createElement(SKY_COMPASS_CARD_EDITOR_NAME);
  }

  public static async getStubConfig(hass: HomeAssistant): Promise<SkyCompassCardConfig> {
    let windows: string[] = [];
    try {
      const options = await fetchWindowOptions(hass);
      if (options[0]) windows = [options[0].window_key];
    } catch {
      /* none discoverable — picker falls back to name + description */
    }
    return {
      type: `custom:${SKY_COMPASS_CARD_NAME}`,
      windows,
    };
  }

  public connectedCallback(): void {
    super.connectedCallback();
    if (this._registry === null) {
      const mem = getCachedRegistry();
      if (mem) this._registry = mem;
    }
    if (this.hass) this._ensureRegistry();
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    if (this._unsubRegistry) {
      this._unsubRegistry();
      this._unsubRegistry = null;
    }
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('hass') && this.hass) this._ensureRegistry();
  }

  // This card forwards `hass` to the compass + chart, so it must re-render whenever any
  // entity those children read changed — but it skips ticks that touched none of them.
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    const ids: Array<string | undefined> = [];
    for (const d of this._discoveredResult.list) ids.push(...Object.values(d.entities));
    if (ids.length === 0) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    return entityStateChanged(old, this.hass, ids);
  }

  protected willUpdate(changed: PropertyValues): void {
    if (
      this._config &&
      this.hass &&
      this._registry !== null &&
      (changed.has('hass') || changed.has('_registry') || changed.has('_config'))
    ) {
      this._discoveredResult = this._listMemo(this.hass, this._refs, this._registry);
    }
  }

  private _ensureRegistry(): void {
    // Revalidate against the shared registry store — cheap when warm (no websocket call),
    // so this also refreshes slices we warm-started from localStorage.
    this._fetchRegistry();
    if (!this._unsubRegistry) {
      this._unsubRegistry = subscribeEntityRegistry(this.hass, () => {
        this._fetchRegistry(true);
      });
    }
  }

  private _fetchRegistry(force = false): void {
    if (this._fetchInFlight) return;
    this._fetchInFlight = true;
    loadEntityRegistry(this.hass, force)
      .then((entries) => {
        if (entries === this._registry) return; // unchanged shared cache → O(1) revalidation
        this._registry = entries;
        this._registryError = null;
        if (this._config && this.hass) {
          for (const ref of this._refs) {
            registryCache.set(windowRefId(ref), windowRegistrySlice(this.hass, ref, entries));
          }
        }
      })
      .catch((err: Error) => {
        this._registryError = err?.message ?? 'entity registry fetch failed';
      })
      .finally(() => {
        this._fetchInFlight = false;
      });
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this._config || !this.hass) return nothing;

    if (this._registry === null) {
      return html`<ha-card>
        <div class="empty">
          <p class="dim">
            ${this._registryError
              ? t('tile.registry_failed', { error: this._registryError })
              : t('root.loading_registry')}
          </p>
        </div>
      </ha-card>`;
    }

    const { list: discoveredList, missing } = this._discoveredResult;

    if (discoveredList.length === 0) {
      return html`<ha-card>
        <div class="empty">
          <p><strong>${t('root.compass_no_match')}</strong></p>
          <p class="dim">
            ${t('root.compass_configured', {
              entries: this._refs.map(windowRefLabel).join(', '),
            })}
          </p>
        </div>
      </ha-card>`;
    }

    const cfg = this._config;
    return html`
      <ha-card>
        ${cfg.title ? html`<div class="card-header">${cfg.title}</div>` : nothing}
        <acp-sky-compass
          .hass=${this.hass}
          .discovered_list=${discoveredList}
          ?compact=${!!cfg.compact}
          .showLegend=${cfg.show_legend ?? true}
          .showStats=${cfg.show_stats ?? true}
          .showMoon=${cfg.show_moon ?? false}
          .showCardinals=${cfg.show_cardinals ?? true}
          .showBlindSpot=${cfg.show_blind_spot ?? true}
          .showSunPath=${cfg.show_sun_path ?? true}
          .showSunriseSunset=${cfg.show_sunrise_sunset ?? true}
          .showCoverFill=${cfg.show_cover_fill ?? true}
          .showWindowArrow=${cfg.show_window_arrow ?? true}
          .coverColors=${cfg.cover_colors ?? []}
          .northOffsetDeg=${normalizeAzimuth(cfg.north_offset ?? 0)}
        ></acp-sky-compass>
        ${cfg.show_elevation_chart !== false
          ? html`<acp-elevation-chart
              .hass=${this.hass}
              .discoveredList=${discoveredList}
              .coverColors=${cfg.cover_colors ?? []}
              ?compact=${!!cfg.compact}
            ></acp-elevation-chart>`
          : nothing}
        ${missing.length > 0
          ? html`<div class="warn dim">
              ${t('root.compass_not_found', { entries: missing.map(windowRefLabel).join(', ') })}
            </div>`
          : nothing}
      </ha-card>
    `;
  }

  public static styles = css`
    :host {
      display: block;
    }
    ha-card {
      padding: 12px 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-sizing: border-box;
    }
    .card-header {
      font-size: 1.05rem;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .empty {
      padding: 16px;
      text-align: center;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .warn {
      font-size: 0.78rem;
      text-align: center;
    }
  `;
}

declare global {
  interface Window {
    customCards: Array<{
      type: string;
      name: string;
      description: string;
      preview?: boolean;
      documentationURL?: string;
    }>;
  }
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === SKY_COMPASS_CARD_NAME)) {
  window.customCards.push({
    type: SKY_COMPASS_CARD_NAME,
    name: 'Adaptive Cover — Sky Compass',
    description:
      'Polar sun-vs-FOV plot; overlay one or more Adaptive Cover entries on a single compass.',
    preview: true,
    documentationURL: 'https://github.com/mrvollger/adaptive-cover-card',
  });
}
