import { LitElement, html, css, nothing, type TemplateResult } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { BADGE_I18N_KEYS, BADGE_ICONS, BADGE_TOKENS, type BadgeKind } from '../const';
import { winnerBadgeKind } from '../lib/badge-visibility';
import { t } from '../lib/i18n';
import { tooltip } from '../lib/tooltip';

/**
 * Compact contextual badge for the tile card.
 *
 * One badge per cover summarising what the integration is doing right now:
 * `Auto`, `Manual`, `Solar tracking`, `Privacy`, etc.
 *
 * The kind is derived from the winning intent; the caller can override it via
 * `kindOverride` after reading the relevant entities/attributes.
 */
@customElement('acp-tile-badge')
export class TileBadge extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property() public winner: string = 'default';

  @property({ type: Boolean, reflect: true }) public compact = false;

  /** When false, the badge renders an "Off" pill regardless of `winner`. */
  @property({ type: Boolean, attribute: 'integration-enabled' })
  public integrationEnabled = true;

  /** When true, the badge renders "Manual" regardless of `winner`. */
  @property({ type: Boolean, attribute: 'manual-active' })
  public manualActive = false;

  /** Explicit badge kind that overrides the winner-derived kind. */
  @property({ attribute: 'kind-override' }) public kindOverride?: BadgeKind;

  /** When true, the badge becomes a tappable button that emits `acp-resume`
   *  (used to resume automatic control while a manual override is active). The
   *  badge stays presentational — it dispatches the event; the host runs the
   *  actual service call. A trailing ↺ icon signals the affordance. */
  @property({ type: Boolean, reflect: true }) public resumable = false;

  protected render(): TemplateResult {
    const kind = this._kind();
    const tokens = BADGE_TOKENS[kind];
    const label = this.hass ? t(BADGE_I18N_KEYS[kind], this.hass) : BADGE_TOKENS[kind].label;
    const icon = BADGE_ICONS[kind];
    const inner = html`${icon
      ? html`<ha-icon class="badge-icon" icon=${icon}></ha-icon>`
      : nothing}${label}${this.resumable
      ? html`<ha-icon class="resume-icon" icon="mdi:restore"></ha-icon>`
      : nothing}`;
    if (this.resumable) {
      const hint = this.hass ? t('tile.resume_aria', this.hass) : 'Resume automatic control';
      return html`<button
        class="badge kind-${kind} resumable"
        style="background:${tokens.bg};color:${tokens.fg};"
        part="badge"
        type="button"
        ${tooltip(hint)}
        aria-label=${hint}
        @click=${this._onResumeClick}
        @pointerdown=${this._stop}
      >
        ${inner}
      </button>`;
    }
    return html`<span
      class="badge kind-${kind}"
      style="background:${tokens.bg};color:${tokens.fg};"
      part="badge"
      >${inner}</span
    >`;
  }

  private _stop(e: Event): void {
    e.stopPropagation();
  }

  private _onResumeClick(e: Event): void {
    e.stopPropagation();
    this.dispatchEvent(new CustomEvent('acp-resume', { bubbles: true, composed: true }));
  }

  private _kind(): BadgeKind {
    return (
      this.kindOverride ??
      winnerBadgeKind({
        winner: this.winner,
        integrationEnabled: this.integrationEnabled,
        manualActive: this.manualActive,
      })
    );
  }

  public static styles = css`
    :host {
      display: inline-flex;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 500;
      white-space: nowrap;
      line-height: 1.4;
    }
    .badge-icon {
      --mdc-icon-size: 14px;
      line-height: 0;
      flex: 0 0 auto;
    }
    button.badge {
      /* Inherit only the family — the font shorthand would reset font-size to
         the page value and make the resumable (manual) badge larger than the
         span badges, which keep the .badge 0.75rem size. */
      font-family: inherit;
      border: none;
      cursor: pointer;
    }
    button.badge:hover {
      filter: brightness(0.92);
    }
    .resume-icon {
      --mdc-icon-size: 14px;
      line-height: 0;
      flex: 0 0 auto;
      opacity: 0.85;
    }
    :host([compact]) .resume-icon {
      --mdc-icon-size: 12px;
    }
    :host([compact]) .badge {
      padding: 1px 6px;
      font-size: 0.7rem;
    }
    :host([compact]) .badge-icon {
      --mdc-icon-size: 12px;
    }
  `;
}
