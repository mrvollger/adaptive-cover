import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { entityStateChanged } from '../lib/hass-change';
import { HANDLER_I18N_KEYS } from '../const';
import type { DecisionStep, DiscoveredEntities } from '../types';
import { buildDecisionSentence, isKnownIntent, normalizeHandler } from '../lib/decision-summary';
import { readTraceAttrs } from '../lib/trace-adapter';
import { coverHeldPosition } from '../lib/cover-position';
import { t } from '../lib/i18n';
import { tooltip } from '../lib/tooltip';

/**
 * Decision strip: renders the integration's `decision_trace` — a list of
 * prose lines on the Cover Position sensor — as ordered steps, with the final
 * (winning) line highlighted and the `intent` shown as the winner label.
 */
@customElement('acp-decision-strip')
export class DecisionStrip extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public discovered!: DiscoveredEntities;
  @property({ type: Boolean, reflect: true }) public compact = false;

  @property({ type: Boolean, reflect: true, attribute: 'show-summary' }) public showSummary = true;

  /** When true, show only the final (winning) trace step. */
  @property({ type: Boolean, reflect: true, attribute: 'hide-inactive' }) public hideInactive =
    false;

  // The Cover Position sensor drives this strip; skip unrelated hass ticks.
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    const e = this.discovered?.entities;
    return entityStateChanged(old, this.hass, [e?.target_position_sensor]);
  }

  private _winnerLabel(intent: string): string {
    const key = normalizeHandler(intent);
    return isKnownIntent(key) ? t(HANDLER_I18N_KEYS[key], this.hass) : intent;
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.hass || !this.discovered) return nothing;
    const attrs = readTraceAttrs(this.hass, this.discovered);
    if (!attrs || attrs.trace.length === 0) {
      return html`<div class="placeholder">${t('decision.placeholder', this.hass)}</div>`;
    }
    const winnerLabel = this._winnerLabel(attrs.winner);
    const summary = buildDecisionSentence(
      attrs.trace,
      attrs,
      attrs.winner,
      this._labels(),
      coverHeldPosition(this.hass, this.discovered),
    );
    const visible = this.hideInactive ? attrs.trace.slice(-1) : attrs.trace;
    return html`
      <div class="wrap">
        <div class="head">
          <span class="label">${t('decision.pipeline', this.hass)}</span>
          <span class="winner">${t('decision.winner', this.hass, { name: winnerLabel })}</span>
        </div>
        ${this.showSummary && summary
          ? html`<div class="summary" ${tooltip(t('decision.summary_tooltip', this.hass))}>
              ${summary}
            </div>`
          : nothing}
        <div class="rows">${visible.map((step, i) => this._row(step, i))}</div>
      </div>
    `;
  }

  private _labels(): Record<string, string> {
    const labels: Record<string, string> = {};
    for (const [key, dotted] of Object.entries(HANDLER_I18N_KEYS)) {
      labels[key] = t(dotted, this.hass);
    }
    return labels;
  }

  private _row(step: DecisionStep, index: number): TemplateResult {
    return html`
      <div class="row ${step.matched ? 'winner' : 'match'}">
        <span class="idx dim">${index + 1}</span>
        <span class="reason-inline">${step.handler}</span>
        ${step.matched ? html`<span class="badge">✓</span>` : nothing}
      </div>
    `;
  }

  public static styles = css`
    :host {
      display: block;
    }
    /* Floating-tooltip cursor lifecycle: a help cursor hints "there's more
       here" on hover, flipping to default the moment OUR bubble appears. */
    [data-tooltip]:hover {
      cursor: help;
    }
    [data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .head {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
      margin-bottom: 2px;
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .rows {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .row {
      display: grid;
      grid-template-columns: 20px 1fr auto;
      align-items: center;
      gap: 6px;
      padding: 3px 6px;
      border-radius: 4px;
      font-size: 0.8rem;
      line-height: 1.3;
    }
    :host([compact]) .row {
      grid-template-columns: 16px 1fr auto;
      font-size: 0.72rem;
      padding: 1px 4px;
    }
    :host([compact]) .head {
      display: none;
    }
    .row.match {
      background: rgba(255, 193, 7, 0.08);
    }
    .row.winner {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-weight: 600;
    }
    .row.winner .dim {
      color: inherit;
      opacity: 0.85;
    }
    .idx {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .reason-inline {
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .badge {
      font-weight: 700;
      padding-left: 4px;
    }
    .summary {
      font-size: 0.85rem;
      line-height: 1.3;
      padding: 2px 4px 4px;
      color: var(--primary-text-color);
    }
    :host([compact]) .summary {
      font-size: 0.75rem;
      padding: 0 2px 2px;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .placeholder {
      color: var(--secondary-text-color);
      padding: 16px;
      text-align: center;
    }
  `;
}

// Re-export for callers that previously imported normalizeHandler from here.
export { normalizeHandler };
