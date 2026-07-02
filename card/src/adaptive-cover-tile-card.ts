import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import {
  handleAction,
  hasAction,
  type ActionConfig,
  type HomeAssistant,
} from 'custom-card-helpers';

import { HANDLER_I18N_KEYS, TILE_CARD_NAME, TILE_CARD_EDITOR_NAME } from './const';
import { createDiscoveryMemo } from './lib/entity-discovery';
import { entityStateChanged } from './lib/hass-change';
import { fetchAcpConfigEntries } from './lib/config-entries';
import { pickCoverIcon } from './lib/icons';
import { subscribeEntityRegistry, type EntityRegistryEntry } from './lib/entity-registry';
import { loadEntityRegistry, getCachedRegistry } from './lib/registry-store';
import { registryCache } from './lib/registry-cache';
import { filterAcp } from './lib/registry-diff';
import type { AdaptiveCoverTileCardConfig, DiscoveredEntities } from './types';
import { buildDecisionSentence } from './lib/decision-summary';
import { readIntent, readTraceAttrs, liveCoverPosition } from './lib/trace-adapter';
import {
  buildSolarActiveContext,
  isAutoControlActive,
  resolveTileBadgeKind,
  selectVisibleBadges,
} from './lib/badge-visibility';
import { formatCoverState, formatPercent } from './lib/formatters';
import { t } from './lib/i18n';
import { setTooltipDefaults, tooltip } from './lib/tooltip';

import './components/tile-badge';
import './components/more-info-dialog';
import './adaptive-cover-tile-card-editor';

const HOLD_DURATION_MS = 500;
const DOUBLE_TAP_WINDOW_MS = 250;

@customElement(TILE_CARD_NAME)
export class AdaptiveCoverTileCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: AdaptiveCoverTileCardConfig;
  // _registry is left public-by-convention so tests can inject a registry and
  // skip the websocket fetch dance (mirrors the sky-compass card pattern).
  @state() public _registry: EntityRegistryEntry[] | null = null;
  @state() private _registryError: string | null = null;
  @state() private _dialogOpen = false;

  private _unsubRegistry: (() => void) | null = null;
  private _fetchInFlight = false;

  // Memoized discovery → stable `_discovered` reference across ticks (keeps the
  // more-info-dialog and its compass from re-rendering on unrelated state changes).
  private _memo = createDiscoveryMemo();
  private _discovered: DiscoveredEntities | null = null;

  public setConfig(config: AdaptiveCoverTileCardConfig): void {
    if (!config || typeof config.entry_id !== 'string' || config.entry_id.length === 0) {
      throw new Error(`${TILE_CARD_NAME}: \`entry_id\` is required and must be a non-empty string`);
    }
    let next: AdaptiveCoverTileCardConfig = { ...config };
    if (typeof next.tap_action === 'string') {
      next = {
        ...next,
        tap_action: next.tap_action === 'none' ? { action: 'none' } : undefined,
      };
    }
    this._config = next;
    if (next.tooltips) setTooltipDefaults(next.tooltips);
    // Warm-start synchronously from the persisted registry slice so a reload skips the
    // Loading state; the shared fetch below revalidates.
    if (this._registry === null) {
      const cached = registryCache.get(next.entry_id);
      if (cached) this._registry = cached.entries;
    }
  }

  public getCardSize(): number {
    return 1;
  }

  // Sections-layout grid sizing. Defaults to full section width and
  // content-driven (auto) height; still narrowable via the column handle.
  public getGridOptions() {
    const detailed = this._config?.layout !== 'one-line';
    return {
      columns: 'full',
      rows: 'auto',
      min_columns: 3,
      min_rows: detailed ? 2 : 1,
    };
  }

  public static async getStubConfig(hass: HomeAssistant): Promise<AdaptiveCoverTileCardConfig> {
    let entry_id = '';
    try {
      const entries = await fetchAcpConfigEntries(hass);
      entry_id = entries[0]?.entry_id ?? '';
    } catch {
      /* none discoverable — picker falls back to name + description */
    }
    return { type: `custom:${TILE_CARD_NAME}`, entry_id };
  }

  public static async getConfigElement(): Promise<HTMLElement> {
    return document.createElement(TILE_CARD_EDITOR_NAME);
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

  // Re-render only on hass ticks that touched one of this entry's entities or
  // managed covers (the union covers the tile body and everything the
  // more-info-dialog forwards).
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    if (!this._discovered) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    return entityStateChanged(old, this.hass, [
      ...Object.values(this._discovered.entities),
      ...this._discovered.managed_covers,
    ]);
  }

  protected willUpdate(changed: PropertyValues): void {
    if (
      this._config &&
      this.hass &&
      this._registry !== null &&
      (changed.has('hass') || changed.has('_registry') || changed.has('_config'))
    ) {
      this._discovered = this._memo(
        this.hass,
        { type: this._config.type, entry_id: this._config.entry_id },
        this._registry,
      );
    }
  }

  private _ensureRegistry(): void {
    // Revalidate against the shared registry store — cheap when warm (no websocket call),
    // so this also refreshes a slice we warm-started from localStorage.
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
    // Capture a generation counter so a late-resolving stale fetch can't
    // overwrite a newer registry value injected (or assigned) in the meantime.
    const myGen = ++this._fetchGen;
    loadEntityRegistry(this.hass, force)
      .then((entries) => {
        if (myGen !== this._fetchGen) return;
        if (entries === this._registry) return; // unchanged shared cache → O(1) revalidation
        this._registry = entries;
        this._registryError = null;
        if (this._config)
          registryCache.set(this._config.entry_id, filterAcp(entries, this._config.entry_id));
      })
      .catch((err: Error) => {
        if (myGen !== this._fetchGen) return;
        this._registryError = err?.message ?? 'entity registry fetch failed';
      })
      .finally(() => {
        if (myGen === this._fetchGen) this._fetchInFlight = false;
      });
  }

  private _fetchGen = 0;

  protected render(): TemplateResult | typeof nothing {
    if (!this._config || !this.hass) return nothing;

    if (this._registry === null) {
      return html`<ha-card>
        <div class="empty">
          <p class="dim">
            ${this._registryError
              ? t('tile.registry_failed', this.hass, { error: this._registryError })
              : t('tile.loading', this.hass)}
          </p>
        </div>
      </ha-card>`;
    }

    const discovered = this._discovered;
    if (!discovered) {
      return html`<ha-card>
        <div class="empty">
          <p class="dim">
            ${t('tile.entry_not_found', this.hass, {
              entry: this._config.entry_id,
            })}
          </p>
        </div>
      </ha-card>`;
    }

    return html`
      <ha-card>${this._renderTile(discovered)}</ha-card>
      <acp-more-info-dialog
        .hass=${this.hass}
        .discovered=${discovered}
        .open=${this._dialogOpen}
        .showCompass=${this._config.show_compass !== false}
        .showElevationChart=${this._config.show_elevation_chart !== false}
        .badges=${this._config.badges}
        @acp-dialog-close=${this._closeDialog}
      ></acp-more-info-dialog>
    `;
  }

  private _closeDialog = (): void => {
    this._dialogOpen = false;
  };

  private _buildHandlerLabels(): Record<string, string> {
    const labels: Record<string, string> = {};
    for (const [key, dotted] of Object.entries(HANDLER_I18N_KEYS)) {
      labels[key] = t(dotted, this.hass);
    }
    return labels;
  }

  private _renderTile(discovered: DiscoveredEntities): TemplateResult {
    const cfg = this._config!;
    const title = cfg.name ?? discovered.entry_title;
    const covers = this._targetCovers(discovered);
    const primaryCover = covers[0];
    const reportedPosition = this._liveCoverPosition(discovered, primaryCover);
    const icon = cfg.icon ?? pickCoverIcon(discovered.cover_type, reportedPosition);
    const showPosition = cfg.show_position !== false;
    const showState = cfg.show_state !== false;
    const showControls = cfg.show_controls !== false;
    const showBadge = cfg.show_badge !== false;
    // `detailed` is the default layout; `one-line` is the compact opt-out.
    const detailed = cfg.layout !== 'one-line';
    const calculatedPosition = this._currentPosition(discovered);
    const livePosition = reportedPosition ?? calculatedPosition;
    // When the cover reports its position, disable the control that can't do
    // anything: open (↑) at fully-open, close (↓) at fully-closed. Covers that
    // don't report a position leave both enabled (gate stays on `!covers.length`).
    const atOpen = reportedPosition !== null && reportedPosition >= 100;
    const atClosed = reportedPosition !== null && reportedPosition <= 0;
    const winner = readIntent(this.hass, discovered);
    const traceAttrs = readTraceAttrs(this.hass, discovered);
    const inert = this._isFullyInert(cfg);
    const summary =
      cfg.show_decision_summary === true && traceAttrs
        ? buildDecisionSentence(
            traceAttrs.trace,
            traceAttrs,
            winner,
            this._buildHandlerLabels(),
            calculatedPosition,
          )
        : '';

    const hasBottomSummary = !!summary && detailed;
    const automaticControl = this._switchOn(discovered, 'automatic_control_switch');
    const manualActive = this._manualOverrideOn(discovered);
    // Resolve the single winner badge through the per-badge opt-in.
    const winnerKind = resolveTileBadgeKind({
      winner,
      integrationEnabled: automaticControl,
      manualActive,
      badges: cfg.badges,
    });
    const solarCtx = buildSolarActiveContext(traceAttrs?.trace, winner);
    const winnerVisible =
      winnerKind !== null && selectVisibleBadges([winnerKind], cfg.badges, solarCtx).length > 0;
    const renderBadge = showBadge && winnerVisible;
    // Standalone "Auto" indicator: shows whenever the cover is under automatic
    // control, independent of which intent won, so a non-auto winner badge
    // (Solar, Climate, …) doesn't hide the fact that automatic control is
    // running. Detailed layout only — one-line has no room.
    const autoActive = isAutoControlActive({
      winner,
      integrationEnabled: automaticControl,
      automaticControl,
      manualActive,
    });
    const showAutoBadge = detailed && showBadge && cfg.badges?.auto !== false && autoActive;
    // Dedupe: when the winner badge is itself `auto` (default winner), render
    // the Auto line only and suppress the inline winner badge.
    const inlineWinnerBadge = !(showAutoBadge && winnerKind === 'auto');
    const stateText = showState && primaryCover ? formatCoverState(this.hass, primaryCover) : null;
    const positionText = showPosition && livePosition !== null ? formatPercent(livePosition) : null;
    const labelParts = [stateText, positionText].filter((p): p is string => !!p);
    const hasStateLabel = !!stateText;

    // The Resume action is folded into the badge: while a manual override is
    // active and the integration exposes a reset button, the contextual badge
    // becomes tappable to resume automatic control.
    const resumable = manualActive && !!discovered.entities.reset_override_button;

    const positionTpl =
      labelParts.length > 0 ? html`<div class="position">${labelParts.join(' · ')}</div>` : nothing;
    const badgeTpl = renderBadge
      ? html`<acp-tile-badge
          .hass=${this.hass}
          .winner=${winner}
          .kindOverride=${winnerKind ?? undefined}
          .integrationEnabled=${automaticControl}
          .manualActive=${manualActive}
          .resumable=${resumable}
          @acp-resume=${() => this._resume(discovered)}
        ></acp-tile-badge>`
      : nothing;
    // The standalone Auto badge reuses the existing `auto` kind/tokens/icon —
    // no resume/manual context, just the indicator.
    const autoBadgeTpl = showAutoBadge
      ? html`<acp-tile-badge
          .hass=${this.hass}
          .winner=${winner}
          .kindOverride=${'auto'}
          .integrationEnabled=${automaticControl}
        ></acp-tile-badge>`
      : nothing;

    return html`
      <div
        class=${`tile-body${detailed ? ' detailed' : ''}${hasBottomSummary ? ' has-summary' : ''}${hasStateLabel ? ' has-state-label' : ''}`}
        role=${inert ? 'group' : 'button'}
        tabindex=${inert ? -1 : 0}
        @pointerdown=${this._onPointerDown}
        @pointerup=${this._onPointerUp}
        @pointercancel=${this._onPointerCancel}
        @pointerleave=${this._onPointerCancel}
        @click=${this._onClick}
      >
        <div class="cover-icon-wrap">
          <ha-icon class="cover-icon" icon=${icon}></ha-icon>
        </div>
        <div class="label">
          <div class="title">${title}</div>
          ${summary && !detailed ? html`<div class="summary">${summary}</div>` : nothing}
          ${hasBottomSummary
            ? html`<div class="summary inline-summary" ${tooltip(summary)}>${summary}</div>`
            : nothing}
        </div>
        ${detailed && showAutoBadge ? html`<div class="auto-line">${autoBadgeTpl}</div>` : nothing}
        ${detailed
          ? html`<div class="detail-line">
              ${positionTpl}${inlineWinnerBadge ? badgeTpl : nothing}
            </div>`
          : html`${positionTpl}`}
        ${showControls
          ? html`<div class="controls" @click=${this._stop} @pointerdown=${this._stop}>
              <button
                class="up"
                type="button"
                aria-label=${t('tile.open', this.hass)}
                ?disabled=${covers.length === 0 || atOpen}
                @click=${() => this._setCoversPosition(discovered, covers, 100)}
              >
                <ha-icon icon="mdi:arrow-up"></ha-icon>
              </button>
              <button
                class="stop"
                type="button"
                aria-label=${t('tile.stop', this.hass)}
                ?disabled=${covers.length === 0}
                @click=${() => this._stopCovers(covers)}
              >
                <ha-icon icon="mdi:stop"></ha-icon>
              </button>
              <button
                class="down"
                type="button"
                aria-label=${t('tile.close', this.hass)}
                ?disabled=${covers.length === 0 || atClosed}
                @click=${() => this._setCoversPosition(discovered, covers, 0)}
              >
                <ha-icon icon="mdi:arrow-down"></ha-icon>
              </button>
            </div>`
          : nothing}
        ${detailed ? nothing : badgeTpl}
      </div>
    `;
  }

  /** Covers the ↑■▼ controls act on: the explicit config `cover`, else every
   *  managed cover discovered from the integration's attributes. */
  private _targetCovers(discovered: DiscoveredEntities): string[] {
    if (this._config?.cover) return [this._config.cover];
    return discovered.managed_covers;
  }

  private _currentPosition(discovered: DiscoveredEntities): number | null {
    const id = discovered.entities.target_position_sensor;
    if (!id) return null;
    const st = this.hass.states[id];
    if (!st) return null;
    const v = parseFloat(st.state);
    return Number.isNaN(v) ? null : v;
  }

  private _liveCoverPosition(
    discovered: DiscoveredEntities,
    cover: string | undefined,
  ): number | null {
    if (!cover) return null;
    return liveCoverPosition(this.hass, discovered.cover_type, cover);
  }

  private _manualOverrideOn(discovered: DiscoveredEntities): boolean {
    const id = discovered.entities.manual_override_binary;
    if (!id) return false;
    return this.hass.states[id]?.state === 'on';
  }

  private _switchOn(discovered: DiscoveredEntities, role: 'automatic_control_switch'): boolean {
    const id = discovered.entities[role];
    if (!id) return true;
    return this.hass.states[id]?.state !== 'off';
  }

  /** Standard cover services on every target cover. Tilt-type entries drive
   *  the slat axis (`set_cover_tilt_position`); everything else the position
   *  axis (`set_cover_position`). */
  private _setCoversPosition(
    discovered: DiscoveredEntities,
    covers: string[],
    position: number,
  ): void {
    if (covers.length === 0) return;
    if (discovered.cover_type === 'cover_tilt') {
      this.hass.callService('cover', 'set_cover_tilt_position', {
        entity_id: covers,
        tilt_position: position,
      });
    } else {
      this.hass.callService('cover', 'set_cover_position', {
        entity_id: covers,
        position,
      });
    }
  }

  private _stopCovers(covers: string[]): void {
    if (covers.length === 0) return;
    this.hass.callService('cover', 'stop_cover', { entity_id: covers });
  }

  private _resume(discovered: DiscoveredEntities): void {
    const btn = discovered.entities.reset_override_button;
    if (!btn) return;
    this.hass.callService('button', 'press', { entity_id: btn });
  }

  private _holdTimer: ReturnType<typeof setTimeout> | null = null;
  private _pendingTapTimer: ReturnType<typeof setTimeout> | null = null;
  private _holdFired = false;

  private _onPointerDown = (): void => {
    this._holdFired = false;
    if (this._holdTimer != null) clearTimeout(this._holdTimer);
    if (!hasAction(this._config?.hold_action)) return;
    this._holdTimer = setTimeout(() => {
      this._holdFired = true;
      this._holdTimer = null;
      this._fireAction('hold');
    }, HOLD_DURATION_MS);
  };

  private _onPointerUp = (): void => {
    if (this._holdTimer != null) {
      clearTimeout(this._holdTimer);
      this._holdTimer = null;
    }
  };

  private _onPointerCancel = (): void => {
    if (this._holdTimer != null) {
      clearTimeout(this._holdTimer);
      this._holdTimer = null;
    }
  };

  private _onClick = (): void => {
    if (this._holdFired) {
      this._holdFired = false;
      return;
    }
    const hasDouble = hasAction(this._config?.double_tap_action);
    if (!hasDouble) {
      this._fireAction('tap');
      return;
    }
    if (this._pendingTapTimer != null) {
      clearTimeout(this._pendingTapTimer);
      this._pendingTapTimer = null;
      this._fireAction('double_tap');
      return;
    }
    this._pendingTapTimer = setTimeout(() => {
      this._pendingTapTimer = null;
      this._fireAction('tap');
    }, DOUBLE_TAP_WINDOW_MS);
  };

  private _tapActionConfig(): ActionConfig | undefined {
    const ta = this._config?.tap_action;
    if (typeof ta === 'string') return undefined; // setConfig normalizes, but be safe
    return ta;
  }

  private _isFullyInert(cfg: AdaptiveCoverTileCardConfig): boolean {
    const tap = this._tapActionConfig();
    const isNone = (a?: ActionConfig): boolean => !!a && a.action === 'none';
    // tap_action undefined means "default = open the dialog" → not inert.
    if (!isNone(tap)) return false;
    if (hasAction(cfg.hold_action)) return false;
    if (hasAction(cfg.double_tap_action)) return false;
    return true;
  }

  private _fireAction(action: 'tap' | 'hold' | 'double_tap'): void {
    if (!this._config || !this.hass) return;
    const tap = this._tapActionConfig();
    if (action === 'tap' && tap === undefined) {
      // Preserve the default: open the more-info dialog.
      this._dialogOpen = true;
      this.dispatchEvent(new CustomEvent('acp-tile-tap', { bubbles: true, composed: true }));
      return;
    }
    const cover = this._resolvedCoverFromState();
    handleAction(
      this,
      this.hass,
      {
        entity: cover,
        tap_action: tap,
        hold_action: this._config.hold_action,
        double_tap_action: this._config.double_tap_action,
      },
      action,
    );
  }

  private _resolvedCoverFromState(): string | undefined {
    if (this._config?.cover) return this._config.cover;
    if (this._registry === null) return undefined;
    const discovered =
      this._discovered ??
      this._memo(
        this.hass,
        { type: this._config!.type, entry_id: this._config!.entry_id },
        this._registry,
      );
    return discovered?.managed_covers[0];
  }

  private _stop(e: Event): void {
    e.stopPropagation();
  }

  public static styles = css`
    :host {
      display: block;
      height: 100%;
    }
    ha-card {
      padding: 6px 10px;
      overflow: hidden;
      height: 100%;
      box-sizing: border-box;
      /* Center the tile body vertically so a taller-than-default grid cell
         (Sections drag-resize) keeps the content centered rather than top-aligned. */
      display: flex;
      flex-direction: column;
      justify-content: center;
      /* In HA's "Sections" view the tile width is driven by the dashboard
         column, not the viewport, so @media can't see the squeeze. Make the
         card a query container so the detailed layout can reflow its controls
         onto their own row once the column gets narrow. */
      container-type: inline-size;
    }
    .tile-body {
      display: grid;
      /* Position column is fixed-width so the controls land at the same x
         across stacked tiles regardless of the digit count (87% vs 100%). */
      grid-template-columns: 24px minmax(0, 1fr) 3rem auto auto;
      grid-template-areas: 'icon label position controls badge';
      align-items: center;
      column-gap: 8px;
      row-gap: 2px;
      cursor: pointer;
      user-select: none;
      min-width: 0;
    }
    /* When the state label is rendered ("Open · 12%") the position cell needs
       to grow to fit variable-width text. */
    .tile-body.has-state-label {
      grid-template-columns: 24px minmax(0, 1fr) auto auto auto;
    }
    /* Detailed layout: title row, then a state row that inlines the position
       text + contextual badge (.detail-line). Icon spans both rows so it's
       vertically centered; controls float to the right of rows 1-2 (HA
       tile-card style). */
    .tile-body.detailed {
      grid-template-columns: 24px minmax(0, 1fr) auto auto;
      grid-template-rows: auto auto;
      grid-template-areas:
        'icon label       auto-line   controls'
        'icon detail-line detail-line controls';
      row-gap: 2px;
    }
    /* The standalone Auto indicator rides right-aligned on the title row —
       same line as the cover name, above the state line — so the tile stays
       two text lines tall. When absent the cell collapses to 0px. */
    .auto-line {
      grid-area: auto-line;
      display: flex;
      justify-content: flex-end;
      align-items: center;
      min-width: 0;
    }
    .auto-line acp-tile-badge {
      overflow: visible;
    }
    .detail-line {
      grid-area: detail-line;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      min-width: 0;
    }
    .detail-line .position {
      padding: 0;
      text-align: left;
      /* Push the badge to the right edge of the row so it sits flush against
         the controls column. */
      margin-right: auto;
    }
    .detail-line acp-tile-badge {
      overflow: visible;
    }
    .tile-body.detailed.has-state-label {
      grid-template-columns: 24px minmax(0, 1fr) auto auto;
      grid-template-rows: auto auto;
      grid-template-areas:
        'icon label       auto-line   controls'
        'icon detail-line detail-line controls';
    }
    .tile-body.detailed.has-summary .label {
      display: flex;
      align-items: baseline;
      gap: 8px;
      min-width: 0;
    }
    .tile-body.detailed.has-summary .label .title {
      flex: 1 1 auto;
      min-width: 0;
    }
    .tile-body.detailed.has-summary .label .inline-summary {
      flex: 0 1 auto;
      text-align: right;
    }
    .tile-body.detailed .position {
      text-align: left;
      padding: 0;
    }
    .tile-body.detailed .controls {
      align-self: center;
      gap: 6px;
    }
    .tile-body.detailed .controls button {
      width: 56px;
      height: 44px;
      border-radius: 12px;
      border: none;
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.15));
    }
    .tile-body.detailed .controls button ha-icon {
      --mdc-icon-size: 22px;
      color: var(--primary-text-color);
    }
    .tile-body.detailed .controls button:hover {
      background: var(--divider-color, rgba(127, 127, 127, 0.25));
    }
    .tile-body.detailed .cover-icon-wrap {
      place-self: center;
    }
    .tile-body[role='group'] {
      cursor: default;
    }
    .cover-icon-wrap {
      grid-area: icon;
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
    }
    .cover-icon {
      --mdc-icon-size: 22px;
      color: var(--primary-text-color);
    }
    .label {
      grid-area: label;
      min-width: 0;
    }
    .title {
      font-size: 0.95rem;
      font-weight: 500;
      color: var(--primary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .summary {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }
    .position {
      grid-area: position;
      font-size: 0.85rem;
      font-variant-numeric: tabular-nums;
      color: var(--primary-text-color);
      padding: 0 4px;
      text-align: right;
    }
    .controls {
      grid-area: controls;
      display: inline-flex;
      gap: 2px;
    }
    .controls button {
      width: 26px;
      height: 26px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
      border-radius: 4px;
      background: var(--card-background-color, white);
      color: var(--primary-text-color);
      cursor: pointer;
      font-size: 0.8rem;
      line-height: 1;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .controls button ha-icon {
      --mdc-icon-size: 16px;
      color: var(--primary-text-color);
      line-height: 0;
    }
    .controls button:hover {
      background: var(--secondary-background-color);
    }
    .controls button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    acp-tile-badge {
      grid-area: badge;
      min-width: 0;
      overflow: hidden;
    }
    /* Floating-tooltip cursor lifecycle for the tooltip carriers inside the
       tile. Help hint on hover, default once OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    /* Reflow: drop the ↑■▼ controls onto their own full-width row beneath the
       name so the cover name gets the whole column. Two triggers:
         1. a phone: the whole viewport is narrow (≤500px) AND the tile is
            near full-width (≤480px).
         2. a desktop "Sections" narrow column (≤340px). */
    @media (max-width: 500px) {
      @container (max-width: 480px) {
        .tile-body.detailed,
        .tile-body.detailed.has-state-label {
          grid-template-columns: 24px minmax(0, 1fr) auto;
          grid-template-rows: auto auto auto;
          grid-template-areas:
            'icon label       auto-line'
            'icon detail-line detail-line'
            'controls controls controls';
        }
        .tile-body.detailed .controls {
          margin-top: 4px;
          gap: 6px;
          justify-content: space-between;
        }
        .tile-body.detailed .controls button {
          flex: 1 1 0;
          width: auto;
          height: 40px;
        }
      }
    }
    @container (max-width: 340px) {
      .tile-body.detailed,
      .tile-body.detailed.has-state-label {
        grid-template-columns: 24px minmax(0, 1fr) auto;
        grid-template-rows: auto auto auto;
        grid-template-areas:
          'icon label       auto-line'
          'icon detail-line detail-line'
          'controls controls controls';
      }
      .tile-body.detailed .controls {
        margin-top: 4px;
        gap: 6px;
        justify-content: space-between;
      }
      .tile-body.detailed .controls button {
        flex: 1 1 0;
        width: auto;
        height: 40px;
      }
    }
    .empty {
      padding: 12px;
      text-align: center;
    }
    .dim {
      color: var(--secondary-text-color);
      margin: 0;
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
if (!window.customCards.some((c) => c.type === TILE_CARD_NAME)) {
  window.customCards.push({
    type: TILE_CARD_NAME,
    name: 'Adaptive Cover — Tile',
    description:
      'Compact chip-style tile for one Adaptive Cover instance: icon, name, position, ↑■↓, contextual badge.',
    preview: true,
    documentationURL: 'https://github.com/mrvollger/adaptive-cover-card',
  });
}
