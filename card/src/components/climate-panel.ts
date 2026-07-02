import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { entityStateChanged } from '../lib/hass-change';
import type { DiscoveredEntities } from '../types';
import { t } from '../lib/i18n';

// Keyed by the states of the integration's Control Method sensor
// ("winter" / "summer" / "intermediate" — plus "basic" outside climate mode).
const STRATEGY_ICONS: Record<string, string> = {
  summer: 'mdi:weather-sunny',
  winter: 'mdi:snowflake',
  intermediate: 'mdi:weather-partly-cloudy',
  basic: 'mdi:sun-compass',
};

/**
 * Climate panel: renders the integration's Control Method sensor (the active
 * seasonal strategy) plus the Climate Mode switch state. Self-hides when the
 * sensor is absent.
 */
@customElement('acp-climate-panel')
export class ClimatePanel extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public discovered!: DiscoveredEntities;
  @property({ type: Boolean, reflect: true }) public compact = false;

  // Driven by the control-method sensor (+ the climate-mode switch for the off
  // label); skip hass ticks that touched neither.
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    const e = this.discovered?.entities;
    return entityStateChanged(old, this.hass, [e?.control_status_sensor, e?.climate_mode_switch]);
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.hass || !this.discovered) return nothing;
    const modeId = this.discovered.entities.climate_mode_switch;
    // No Climate Mode switch → the entry was configured without climate mode:
    // hide the section entirely.
    if (!modeId) return nothing;
    const id = this.discovered.entities.control_status_sensor;
    if (!id) return nothing;
    const st = this.hass.states[id];
    if (!st || st.state === 'unavailable') return nothing;

    const modeOff = this.hass.states[modeId]?.state === 'off';
    if (modeOff || st.state === 'unknown' || st.state === '') {
      const label = modeOff ? t('climate.mode_off', this.hass) : t('climate.standby', this.hass);
      const icon = modeOff ? 'mdi:power-off' : 'mdi:thermostat';
      return html`
        <div class="wrap">
          <div class="head">
            <span class="label">${t('climate.title', this.hass)}</span>
          </div>
          <div class="strategy standby">
            <ha-icon icon=${icon}></ha-icon>
            <span class="strategy-name dim">${label}</span>
          </div>
        </div>
      `;
    }

    const strategy = st.state;
    const icon = STRATEGY_ICONS[strategy] ?? 'mdi:thermostat';
    const fmt = (this.hass as unknown as { formatEntityState?: (s: unknown) => string })
      .formatEntityState;
    const strategyLabel = typeof fmt === 'function' ? (fmt(st) ?? strategy) : strategy;

    return html`
      <div class="wrap">
        <div class="head">
          <span class="label">${t('climate.title', this.hass)}</span>
        </div>
        <div class="strategy">
          <ha-icon icon=${icon}></ha-icon>
          <span class="strategy-name">${strategyLabel}</span>
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
    .head {
      display: flex;
      justify-content: space-between;
      font-size: 0.78rem;
      color: var(--secondary-text-color);
    }
    .label {
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .strategy {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.95rem;
      font-weight: 500;
    }
    .strategy ha-icon {
      --mdc-icon-size: 20px;
      color: var(--primary-color);
    }
    .strategy.standby ha-icon {
      color: var(--secondary-text-color);
    }
    :host([compact]) .strategy {
      font-size: 0.85rem;
    }
    :host([compact]) .head {
      display: none;
    }
    .dim {
      color: var(--secondary-text-color);
    }
  `;
}
