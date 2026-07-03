import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { entityStateChanged } from '../lib/hass-change';
import type { DiscoveredEntities } from '../types';
import { t } from '../lib/i18n';
import { confirmResume, resumeTarget } from '../lib/confirm';

@customElement('acp-overrides-panel')
export class OverridesPanel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public discovered!: DiscoveredEntities;
  @property({ type: Boolean, reflect: true }) public compact = false;
  @property({ type: Boolean, attribute: 'reset-enabled' }) public resetEnabled = true;

  // Skip re-render on hass ticks that touched none of this panel's entities.
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    const e = this.discovered?.entities;
    return entityStateChanged(old, this.hass, [
      e?.manual_override_binary,
      e?.reset_override_button,
    ]);
  }

  private _manualActive(): boolean {
    const id = this.discovered.entities.manual_override_binary;
    return id ? this.hass.states[id]?.state === 'on' : false;
  }

  /** Covers currently under manual control, from the binary sensor's
   *  `manual_controlled` attribute. */
  private _manualList(): string[] {
    const id = this.discovered.entities.manual_override_binary;
    if (!id) return [];
    const list = (this.hass.states[id]?.attributes as { manual_controlled?: string[] })
      ?.manual_controlled;
    return Array.isArray(list) ? list : [];
  }

  private _resetManual(): void {
    const id = this.discovered.entities.reset_override_button;
    if (!id) return;
    if (!confirmResume(this.hass, resumeTarget(this.hass, this.discovered.entities.target_position_sensor)))
      return;
    this.hass.callService('button', 'press', { entity_id: id });
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.hass || !this.discovered) return nothing;
    const manualActive = this._manualActive();
    const manualList = this._manualList();
    const resetId = this.discovered.entities.reset_override_button;
    const resetLabel = t('overrides.reset_manual', this.hass);

    return html`
      <div class="wrap">
        <div class="label dim">${t('overrides.title', this.hass)}</div>
        <div class="grid">
          <div class="tile ${manualActive ? 'active' : ''}">
            <div class="tile-label">${t('overrides.manual', this.hass)}</div>
            <div class="tile-value">
              ${manualActive ? t('overrides.active', this.hass) : t('overrides.off', this.hass)}
            </div>
            ${manualActive && manualList.length > 0
              ? html`<div class="tile-sub dim">
                  ${t('overrides.active_count', this.hass, { count: manualList.length })}
                </div>`
              : nothing}
          </div>

          ${resetId
            ? this.resetEnabled
              ? html`<button class="tile action" @click=${this._resetManual}>
                  <ha-icon icon="mdi:restore"></ha-icon>
                  <div class="tile-value">${resetLabel}</div>
                </button>`
              : html`<button class="tile action readonly" aria-disabled="true" tabindex="-1">
                  <ha-icon icon="mdi:restore"></ha-icon>
                  <div class="tile-value">${resetLabel}</div>
                </button>`
            : nothing}
        </div>
      </div>
    `;
  }

  public static styles = css`
    :host {
      display: block;
    }
    .wrap {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .label {
      font-size: 0.78rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 6px;
    }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 10px;
      border-radius: 6px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      font-size: 0.8rem;
    }
    :host([compact]) .tile {
      padding: 4px 8px;
      font-size: 0.72rem;
    }
    :host([compact]) .tile-sub {
      display: none;
    }
    :host([compact]) .label {
      display: none;
    }
    .tile.active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .tile.action {
      cursor: pointer;
      border: none;
      text-align: left;
      font-family: inherit;
      align-items: flex-start;
    }
    .tile.action:hover {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .tile.action.readonly {
      cursor: default;
      opacity: 0.85;
      pointer-events: none;
    }
    .tile.action.readonly:hover {
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      color: inherit;
    }
    .tile-label {
      font-size: 0.72rem;
      opacity: 0.8;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .tile-value {
      font-weight: 500;
    }
    .tile-sub {
      font-size: 0.72rem;
    }
    .dim {
      color: var(--secondary-text-color);
    }
    .tile.active .dim {
      color: inherit;
      opacity: 0.85;
    }
    ha-icon {
      --mdc-icon-size: 18px;
    }
  `;
}
