import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { COVER_TYPE_ICONS, HANDLER_I18N_KEYS, INTEGRATION_DOMAIN, type BadgeKind } from '../const';
import { buildDecisionSentence } from '../lib/decision-summary';
import {
  buildSolarActiveContext,
  selectVisibleBadges,
  winnerBadgeKind,
} from '../lib/badge-visibility';
import { startMinuteTimer } from '../lib/minute-timer';
import type { AdaptiveCoverTileCardConfig, DiscoveredEntities } from '../types';
import { readCoverAttrs, readForecast, readIntent, readTraceAttrs } from '../lib/trace-adapter';
import { formatPercent } from '../lib/formatters';
import { t } from '../lib/i18n';
import { tooltip } from '../lib/tooltip';

import './tile-badge';
import './decision-strip';
import './overrides-panel';
import './cover-bar';
import './forecast-strip';
import './sky-compass';
import './elevation-chart';

/**
 * Card-owned more-info dialog (HA's built-in more-info is entity-bound and
 * cannot carry the integration-specific context).
 *
 * Renders the winner badge, the plain-English decision summary, a position
 * block, Resume Auto, and a collapsible Advanced section that embeds the
 * existing panel components for the full diagnostic surface.
 */
@customElement('acp-more-info-dialog')
export class MoreInfoDialog extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public discovered!: DiscoveredEntities;
  @property({ type: Boolean, reflect: true }) public open = false;

  @property({ type: Boolean }) public advancedOpen = false;
  @property({ type: Boolean }) public showCompass = true;
  @property({ type: Boolean }) public showElevationChart = true;

  /** Per-kind badge opt-in, threaded down from the tile-card config. */
  @property({ attribute: false }) public badges?: AdaptiveCoverTileCardConfig['badges'];

  // Refresh the time-derived bits (the forecast strip's `now` cursor) every minute while
  // the dialog is open, aligned to the minute boundary. The dialog is always in the DOM via
  // the tile card, so gate on `open` rather than connection so a closed dialog isn't ticking.
  private _cancelMinuteTimer: (() => void) | null = null;

  protected updated(): void {
    this._syncMinuteTimer(this.open);
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    this._syncMinuteTimer(false);
  }

  private _syncMinuteTimer(active: boolean): void {
    if (active && this._cancelMinuteTimer === null) {
      this._cancelMinuteTimer = startMinuteTimer(() => this.requestUpdate());
    } else if (!active && this._cancelMinuteTimer !== null) {
      this._cancelMinuteTimer();
      this._cancelMinuteTimer = null;
    }
  }

  // Stable single-element wrapper for the embedded compass/chart, rebuilt only when
  // `discovered` changes — a fresh `[this.discovered]` literal each render would churn
  // the children's array prop and defeat their own `shouldUpdate` guards.
  private _listSource: DiscoveredEntities | null = null;
  private _list: DiscoveredEntities[] = [];
  private get _discoveredList(): DiscoveredEntities[] {
    if (this.discovered !== this._listSource) {
      this._listSource = this.discovered;
      this._list = this.discovered ? [this.discovered] : [];
    }
    return this._list;
  }

  private _buildHandlerLabels(): Record<string, string> {
    const labels: Record<string, string> = {};
    for (const [key, dotted] of Object.entries(HANDLER_I18N_KEYS)) {
      labels[key] = t(dotted, this.hass);
    }
    return labels;
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.open || !this.hass || !this.discovered) return nothing;
    const winner = readIntent(this.hass, this.discovered);
    const attrs = readTraceAttrs(this.hass, this.discovered);
    const target = this._target();
    const summary = attrs
      ? buildDecisionSentence(attrs.trace, attrs, winner, this._buildHandlerLabels(), target)
      : '';
    const showResume = this._shouldShowResume();
    const automaticControl = this._switchOn('automatic_control_switch');
    const badgeKinds = this._badgeKinds(winner, automaticControl);
    const configureLabel = t('dialog.configure_integration', this.hass);
    const deviceLabel = t('dialog.open_device_page', this.hass);
    const closeLabel = t('dialog.close', this.hass);

    return html`
      <div class="backdrop" data-open @click=${this._onBackdrop}>
        <div class="dialog" @click=${this._stop} role="dialog" aria-modal="true">
          <div class="header">
            <ha-icon
              class="cover-icon"
              icon=${COVER_TYPE_ICONS[this.discovered.cover_type] ?? 'mdi:window-shutter'}
            ></ha-icon>
            <div class="title">${this.discovered.entry_title}</div>
            <div class="badges">
              ${badgeKinds.map(
                (k) =>
                  html`<acp-tile-badge
                    .hass=${this.hass}
                    .winner=${winner}
                    .kindOverride=${k}
                    .integrationEnabled=${automaticControl}
                  ></acp-tile-badge>`,
              )}
            </div>
            <button
              class="icon-btn options-link"
              type="button"
              aria-label=${configureLabel}
              ${tooltip(configureLabel)}
              @click=${this._openIntegrationPage}
            >
              <ha-icon icon="mdi:tune-variant"></ha-icon>
            </button>
            ${this.discovered.device_id
              ? html`<button
                  class="icon-btn device-link"
                  type="button"
                  aria-label=${deviceLabel}
                  ${tooltip(deviceLabel)}
                  @click=${this._openDevicePage}
                >
                  <ha-icon icon="mdi:cog"></ha-icon>
                </button>`
              : nothing}
            <button class="close" type="button" aria-label=${closeLabel} @click=${this._emitClose}>
              ✕
            </button>
          </div>

          ${summary ? html`<div class="summary">${summary}</div>` : nothing}

          <div class="position-block">
            <div class="position-label">${t('dialog.target', this.hass)}</div>
            <div class="position-value">${formatPercent(target)}</div>
          </div>

          <acp-cover-bar .hass=${this.hass} .discovered=${this.discovered}></acp-cover-bar>

          ${this._renderForecastStrip()} ${this._renderControls()}
          ${showResume
            ? html`<div class="actions">
                <button class="resume" type="button" @click=${this._onResume}>
                  ${t('dialog.resume_auto', this.hass)}
                </button>
              </div>`
            : nothing}

          <button class="advanced-toggle" type="button" @click=${this._toggleAdvanced}>
            ${this.advancedOpen
              ? t('dialog.hide_advanced', this.hass)
              : t('dialog.show_advanced', this.hass)}
          </button>
          ${this.advancedOpen
            ? html`<div class="advanced">
                ${this.showCompass
                  ? html`<div class="advanced-compass">
                      <acp-sky-compass
                        .hass=${this.hass}
                        .discovered_list=${this._discoveredList}
                        ?compact=${true}
                        .showLegend=${false}
                        .showStats=${true}
                      ></acp-sky-compass>
                    </div>`
                  : nothing}
                ${this.showElevationChart
                  ? html`<acp-elevation-chart
                      .hass=${this.hass}
                      .discoveredList=${this._discoveredList}
                      ?compact=${true}
                    ></acp-elevation-chart>`
                  : nothing}
                <acp-decision-strip
                  .hass=${this.hass}
                  .discovered=${this.discovered}
                ></acp-decision-strip>
                ${this._renderMoves()}
                <acp-overrides-panel
                  .hass=${this.hass}
                  .discovered=${this.discovered}
                ></acp-overrides-panel>
              </div>`
            : nothing}
        </div>
      </div>
    `;
  }

  /** The winner badge (plus manual/off state), run through the per-kind opt-in. */
  private _badgeKinds(winner: string, automaticControl: boolean): BadgeKind[] {
    const attrs = readTraceAttrs(this.hass, this.discovered);
    const kind = winnerBadgeKind({
      winner,
      integrationEnabled: automaticControl,
      manualActive: this._manualOverrideOn(),
    });
    const ctx = buildSolarActiveContext(attrs?.trace, winner);
    return selectVisibleBadges([kind], this.badges, ctx);
  }

  private _target(): number | null {
    const id = this.discovered.entities.target_position_sensor;
    if (!id) return null;
    const st = this.hass.states[id];
    if (!st) return null;
    const v = parseFloat(st.state);
    return Number.isNaN(v) ? null : v;
  }

  private _onResume = (): void => {
    const btn = this.discovered.entities.reset_override_button;
    if (!btn) return;
    this.hass.callService('button', 'press', { entity_id: btn });
  };

  private _manualOverrideOn(): boolean {
    const id = this.discovered.entities.manual_override_binary;
    if (!id) return false;
    return this.hass.states[id]?.state === 'on';
  }

  private _switchOn(role: 'automatic_control_switch'): boolean {
    const id = this.discovered.entities[role];
    if (!id) return true;
    return this.hass.states[id]?.state !== 'off';
  }

  private _shouldShowResume(): boolean {
    if (!this.discovered.entities.reset_override_button) return false;
    return this._manualOverrideOn();
  }

  private _renderControls(): TemplateResult | typeof nothing {
    type SwitchRole = 'automatic_control_switch' | 'climate_mode_switch' | 'manual_toggle_switch';
    const rows: Array<{ role: SwitchRole; label: string }> = (
      [
        { role: 'automatic_control_switch', label: t('dialog.automatic', this.hass) },
        { role: 'climate_mode_switch', label: t('dialog.climate', this.hass) },
        { role: 'manual_toggle_switch', label: t('dialog.manual_detection', this.hass) },
      ] as const
    ).filter((r) => !!this.discovered.entities[r.role]);
    if (rows.length === 0) return nothing;
    return html`<div class="controls-block">
      <div class="controls-label">${t('dialog.controls', this.hass)}</div>
      <div class="controls-row">${rows.map((r) => this._renderSwitchChip(r.role, r.label))}</div>
    </div>`;
  }

  private _renderSwitchChip(
    role: 'automatic_control_switch' | 'climate_mode_switch' | 'manual_toggle_switch',
    label: string,
  ): TemplateResult {
    const id = this.discovered.entities[role]!;
    const on = this.hass.states[id]?.state === 'on';
    const state = on ? t('dialog.state_on', this.hass) : t('dialog.state_off', this.hass);
    const onOff = on ? t('dialog.on', this.hass) : t('dialog.off', this.hass);
    return html`<button
      class="ctrl-toggle ${on ? 'on' : 'off'}"
      type="button"
      aria-pressed=${on}
      aria-label=${t('dialog.toggle_hint', this.hass, { label, state })}
      @click=${() => this._toggleSwitch(id, on)}
    >
      <span class="ctrl-label">${label}</span>
      <span class="ctrl-state">${onOff}</span>
    </button>`;
  }

  private _toggleSwitch(entity_id: string, currentlyOn: boolean): void {
    this.hass.callService('switch', currentlyOn ? 'turn_off' : 'turn_on', { entity_id });
  }

  private _renderForecastStrip(): TemplateResult | typeof nothing {
    const forecast = readForecast(this.hass, this.discovered);
    if (!forecast || forecast.forecast.length === 0) return nothing;
    return html`<div class="forecast-block">
      <div class="forecast-label">${t('dialog.todays_forecast', this.hass)}</div>
      <acp-forecast-strip
        .hass=${this.hass}
        .samples=${forecast.forecast}
        .events=${forecast.events}
        .now=${Date.now()}
      ></acp-forecast-strip>
      <div class="forecast-note">${t('forecast.solar_only_note', this.hass)}</div>
    </div>`;
  }

  /** Recent per-cover move log + currently blocked gates, from the Cover
   *  Position sensor's `last_moves` / `move_blocked_by` attributes. */
  private _renderMoves(): TemplateResult | typeof nothing {
    const attrs = readCoverAttrs(this.hass, this.discovered);
    const moves = Object.entries(attrs?.last_moves ?? {});
    const blocked = Object.entries(attrs?.move_blocked_by ?? {});
    if (moves.length === 0 && blocked.length === 0) return nothing;
    const friendly = (id: string): string =>
      (this.hass.states[id]?.attributes?.friendly_name as string | undefined) ?? id;
    return html`<div class="moves-section">
      <div class="moves-label">${t('dialog.last_moves', this.hass)}</div>
      ${moves.map(
        ([id, line]) =>
          html`<div class="move-row">
            <span class="move-name" ${tooltip(id)}>${friendly(id)}</span>
            <span class="move-line dim">${line}</span>
          </div>`,
      )}
      ${blocked.map(
        ([id, gate]) =>
          html`<div class="move-row blocked">
            <span class="move-name" ${tooltip(id)}>${friendly(id)}</span>
            <span class="move-line">${t('dialog.move_blocked', this.hass, { gate })}</span>
          </div>`,
      )}
    </div>`;
  }

  private _toggleAdvanced = (): void => {
    this.advancedOpen = !this.advancedOpen;
  };

  private _openDevicePage = (): void => {
    const deviceId = this.discovered.device_id;
    if (!deviceId) return;
    this._navigate(`/config/devices/device/${deviceId}`);
  };

  private _openIntegrationPage = (): void => {
    this._navigate(`/config/integrations/integration/${INTEGRATION_DOMAIN}`);
  };

  private _navigate(path: string): void {
    history.pushState(null, '', path);
    window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } }));
    this._emitClose();
  }

  private _onBackdrop = (e: MouseEvent): void => {
    if (e.target === e.currentTarget) this._emitClose();
  };

  private _emitClose = (): void => {
    this.dispatchEvent(new CustomEvent('acp-dialog-close', { bubbles: true, composed: true }));
  };

  private _stop = (e: Event): void => {
    e.stopPropagation();
  };

  public static styles = css`
    :host {
      display: contents;
    }
    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.5);
      z-index: 9999;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 5vh 12px;
      overflow-y: auto;
    }
    .dialog {
      width: 100%;
      max-width: 520px;
      background: var(--card-background-color, white);
      color: var(--primary-text-color);
      border-radius: 12px;
      padding: 14px 16px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header .cover-icon {
      --mdc-icon-size: 22px;
    }
    .header .title {
      font-size: 1.1rem;
      font-weight: 600;
      flex: 1;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .header .badges {
      display: inline-flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .close {
      border: 0;
      background: transparent;
      cursor: pointer;
      font-size: 1.1rem;
      color: var(--secondary-text-color);
      padding: 4px 6px;
    }
    .close:hover {
      color: var(--primary-text-color);
    }
    .icon-btn {
      border: 0;
      background: transparent;
      cursor: pointer;
      color: var(--secondary-text-color);
      padding: 4px 6px;
      display: inline-flex;
      align-items: center;
      --mdc-icon-size: 18px;
    }
    .icon-btn:hover {
      color: var(--primary-text-color);
    }
    .summary {
      font-size: 0.9rem;
      font-style: italic;
      color: var(--secondary-text-color);
    }
    .position-block {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.95rem;
    }
    .position-label {
      color: var(--secondary-text-color);
    }
    .position-value {
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .actions {
      display: flex;
      gap: 8px;
    }
    .resume {
      padding: 6px 14px;
      border: 1px solid var(--primary-color);
      border-radius: 999px;
      background: transparent;
      color: var(--primary-color);
      font-size: 0.9rem;
      cursor: pointer;
    }
    .resume:hover {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }
    .advanced-toggle {
      border: 0;
      background: transparent;
      cursor: pointer;
      color: var(--primary-color);
      font-size: 0.85rem;
      text-align: left;
      padding: 4px 0;
    }
    .advanced {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-top: 4px;
      border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.08));
    }
    .advanced-compass {
      display: flex;
      justify-content: center;
    }
    .moves-section {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .moves-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .move-row {
      display: grid;
      grid-template-columns: minmax(80px, 1fr) auto;
      gap: 8px;
      align-items: baseline;
      font-size: 0.82rem;
      padding: 1px 4px;
    }
    .move-name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .move-line {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .move-row.blocked .move-line {
      color: var(--warning-color, orange);
    }
    .move-name[data-tooltip]:hover {
      cursor: help;
    }
    .move-name[data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .forecast-block {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .forecast-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .forecast-note {
      font-size: 0.7rem;
      color: var(--secondary-text-color);
      opacity: 0.75;
    }
    .controls-block {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .controls-label {
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .controls-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .ctrl-toggle {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 999px;
      border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.16));
      background: transparent;
      cursor: pointer;
      font-size: 0.8rem;
      color: var(--primary-text-color);
    }
    .ctrl-toggle .ctrl-label {
      font-weight: 500;
    }
    .ctrl-toggle .ctrl-state {
      font-size: 0.75rem;
      color: var(--secondary-text-color);
    }
    .ctrl-toggle.on {
      background: rgba(76, 175, 80, 0.16);
      border-color: rgba(76, 175, 80, 0.5);
    }
    .ctrl-toggle.on .ctrl-state {
      color: #1b5e20;
    }
    .ctrl-toggle.off {
      opacity: 0.85;
    }
    .ctrl-toggle:hover {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }
  `;
}
