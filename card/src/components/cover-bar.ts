import { LitElement, html, css, nothing, type TemplateResult, type PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { entityStateChanged } from '../lib/hass-change';
import type { DiscoveredEntities } from '../types';
import { coverActualPositions, displayTarget, isOverrideDivergence } from '../lib/cover-position';
import { formatPercent } from '../lib/formatters';
import { t } from '../lib/i18n';
import { tooltip } from '../lib/tooltip';

@customElement('acp-cover-bar')
export class CoverBar extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public discovered!: DiscoveredEntities;
  @property({ type: Boolean, reflect: true }) public compact = false;
  /** User-selected cover colour (config `cover_colors[0]`) — recolours the
   *  closed segment to match the compass cover wedge. Null falls back to
   *  `--primary-color`, exactly like the compass in single-entry mode. */
  @property({ attribute: false }) public coverColor: string | null = null;

  // Live positions come from the managed cover entities; the target from the
  // Cover Position sensor. Skip unrelated hass ticks.
  protected shouldUpdate(changed: PropertyValues): boolean {
    if (changed.size > 1 || !changed.has('hass')) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    const e = this.discovered?.entities;
    return entityStateChanged(old, this.hass, [
      e?.target_position_sensor,
      e?.manual_override_binary,
      ...(this.discovered?.managed_covers ?? []),
    ]);
  }

  private _setPosition(entityId: string, position: number): void {
    if (this.discovered.cover_type === 'cover_tilt') {
      this.hass.callService('cover', 'set_cover_tilt_position', {
        entity_id: entityId,
        tilt_position: position,
      });
    } else {
      this.hass.callService('cover', 'set_cover_position', {
        entity_id: entityId,
        position,
      });
    }
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this.hass || !this.discovered) return nothing;
    const target = displayTarget(this.hass, this.discovered);
    const covers = coverActualPositions(this.hass, this.discovered);
    const overrideDivergence = isOverrideDivergence(this.hass, this.discovered);
    const entries = Object.entries(covers);
    if (entries.length === 0) {
      return html`<div class="placeholder">${t('covers.placeholder', this.hass)}</div>`;
    }
    return html`
      <div class="wrap" style=${this.coverColor ? `--acp-cover-color:${this.coverColor}` : nothing}>
        <div class="head">
          <span class="label">${t('covers.title', this.hass)}</span>
          <span class="targets">
            <span class="target"
              >${t(overrideDivergence ? 'covers.target_solar' : 'covers.target', this.hass, {
                pct: formatPercent(target),
              })}</span
            >
          </span>
        </div>
        ${entries.map(
          ([id, actual]) => html`
            <div class="cover-group">${this._bar(id, actual, target, overrideDivergence)}</div>
          `,
        )}
      </div>
    `;
  }

  private _bar(
    entityId: string,
    actual: number | null,
    target: number | null,
    overrideDivergence: boolean,
  ): TemplateResult {
    const friendly =
      (this.hass.states[entityId]?.attributes?.friendly_name as string | undefined) ?? entityId;
    const actualPct = actual ?? 0;
    const targetPct = target ?? 0;
    return html`
      <div class="cover">
        <div class="name" ${tooltip(entityId)}>${friendly}</div>
        <div class="num">${formatPercent(actual)}</div>
        <div
          class="track"
          @click=${(e: MouseEvent) => this._handleTrackClick(e, entityId)}
          ${tooltip(t('covers.click_to_set', this.hass))}
        >
          <div class="fill" style="width:${actualPct}%"></div>
          <div class="fill-closed" style="width:${100 - actualPct}%"></div>
          ${target !== null
            ? html`<div
                class="marker"
                style="left:clamp(1px, ${targetPct}%, calc(100% - 1px))"
                ${tooltip(
                  t(
                    overrideDivergence ? 'covers.target_tooltip_override' : 'covers.target_tooltip',
                    this.hass,
                    { pct: targetPct },
                  ),
                )}
              ></div>`
            : nothing}
        </div>
      </div>
    `;
  }

  private _handleTrackClick(e: MouseEvent, entityId: string): void {
    const track = e.currentTarget as HTMLElement;
    const rect = track.getBoundingClientRect();
    const pct = Math.round(((e.clientX - rect.left) / rect.width) * 100);
    const clamped = Math.max(0, Math.min(100, pct));
    this._setPosition(entityId, clamped);
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
    .targets {
      display: flex;
      gap: 12px;
    }
    .target {
      font-variant-numeric: tabular-nums;
    }
    .cover-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .cover {
      display: grid;
      grid-template-columns: minmax(80px, 1fr) 48px 3fr 16px;
      gap: 8px;
      align-items: center;
      font-size: 0.82rem;
    }
    .name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .name[data-tooltip]:hover {
      cursor: help;
    }
    .name[data-tooltip][acp-tt-shown] {
      cursor: default;
    }
    .track {
      position: relative;
      display: flex;
      height: 10px;
      background: var(--secondary-background-color, rgba(0, 0, 0, 0.08));
      border-radius: 6px;
      cursor: pointer;
      overflow: hidden;
    }
    :host([compact]) .track {
      height: 6px;
    }
    :host([compact]) .cover {
      font-size: 0.75rem;
      gap: 6px;
    }
    :host([compact]) .head {
      display: none;
    }
    .fill {
      height: 100%;
      flex-shrink: 0;
      background: color-mix(in srgb, var(--acp-cover-color, var(--primary-color)) 18%, transparent);
      transition: width 0.3s ease;
    }
    .fill-closed {
      height: 100%;
      flex-shrink: 0;
      background: color-mix(in srgb, var(--acp-cover-color, var(--primary-color)) 50%, transparent);
      transition: width 0.3s ease;
    }
    .marker {
      position: absolute;
      top: -2px;
      width: 2px;
      height: 14px;
      background: var(--accent-color, red);
      transform: translateX(-50%);
      transition: left 0.3s ease;
    }
    .num {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .placeholder {
      color: var(--secondary-text-color);
      text-align: center;
      padding: 16px;
    }
  `;
}
