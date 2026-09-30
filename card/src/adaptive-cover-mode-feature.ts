import { LitElement, html, css, nothing, type PropertyValues, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { MODE_FEATURE_EDITOR_NAME, MODE_FEATURE_TYPE } from './const';
import { entityStateChanged } from './lib/hass-change';
import {
  canHold,
  groupMode,
  hubCanHold,
  planHouseMode,
  planWindowsMode,
  runCalls,
  windowMode,
  type ServiceCall,
} from './lib/house-actions';
import {
  discoverHouse,
  type GroupMode,
  type HouseHass,
  type HouseModel,
  type HouseWindow,
  type WindowMode,
} from './lib/house-model';
import { t } from './lib/i18n';
import { getCachedRegistry } from './lib/registry-store';

/*
 * Mode chips as a tile card feature (refactor plan "UI": "Mode chips are a
 * custom tile card feature, so stock tile cards can show them").
 *
 *   type: tile
 *   entity: select.office_north_mode      # or the window's cover
 *   features:
 *     - type: custom:adaptive-cover-mode
 *
 * The tile's entity picks what the chips act on:
 *
 * - a window's Mode select, its physical cover or any other entity on the
 *   window device: that window (Auto / Off: select.select_option; Hold:
 *   adaptive_cover.hold, with the window's own override duration);
 * - the house select or the house cover: every window (the house select).
 *
 * The mapping is the house card's (lib/house-actions.ts), so older entity
 * surfaces work too (there Hold is off until a hand move).
 */

const MODES: WindowMode[] = ['auto', 'hold', 'off'];

export interface ModeFeatureConfig {
  type: string;
}

/** What a tile's entity controls. */
export type ModeTarget =
  | { kind: 'window'; window: HouseWindow; model: HouseModel }
  | { kind: 'house'; model: HouseModel };

// One discovery per `hass.states` object, shared by every feature on a view.
const modelCache = new WeakMap<object, HouseModel>();

function houseModel(hass: HomeAssistant): HouseModel {
  const key = hass.states as object;
  let model = modelCache.get(key);
  if (!model) {
    model = discoverHouse(hass, getCachedRegistry());
    modelCache.set(key, model);
  }
  return model;
}

/** The window (or the house) an entity belongs to, or null. */
export function modeTarget(
  hass: HomeAssistant | undefined,
  entityId: string | undefined,
): ModeTarget | null {
  if (!hass?.states || !entityId) return null;
  const model = houseModel(hass);
  if (entityId === model.hub.modeSelect || entityId === model.hub.cover) {
    return { kind: 'house', model };
  }
  let w = model.windows.find(
    (x) => Object.values(x.entities).includes(entityId) || x.covers.includes(entityId),
  );
  if (!w) {
    const device = (hass as HouseHass).entities?.[entityId]?.device_id;
    if (device) w = model.windows.find((x) => x.deviceId === device);
  }
  return w ? { kind: 'window', window: w, model } : null;
}

type StateLike = { entity_id?: string; attributes?: Record<string, unknown> };

/**
 * Whether the feature fits a tile. HA calls it with the tile's state object
 * (older frontends) or with (hass, context); both work.
 */
export function modeFeatureSupported(a: unknown, b?: unknown): boolean {
  if (a && typeof a === 'object' && 'states' in a) {
    const context = b as { entity_id?: string } | undefined;
    return modeTarget(a as HomeAssistant, context?.entity_id) !== null;
  }
  const st = a as StateLike | undefined;
  const id = st?.entity_id;
  if (!id) return false;
  const domain = id.slice(0, id.indexOf('.'));
  if (domain === 'cover') return true;
  if (domain !== 'select') return false;
  const options = st?.attributes?.options;
  return (
    Array.isArray(options) &&
    ['auto', 'hold', 'off'].every((o) => options.some((x) => String(x).toLowerCase() === o))
  );
}

@customElement(MODE_FEATURE_TYPE)
export class AdaptiveCoverModeFeature extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  /** HA 2025.3+: the tile's context. */
  @property({ attribute: false }) public context?: { entity_id?: string };
  /** Older HA: the tile's state object. */
  @property({ attribute: false }) public stateObj?: { entity_id: string };

  @state() private _config?: ModeFeatureConfig;

  private _watched: string[] = [];

  public static getStubConfig(): ModeFeatureConfig {
    return { type: `custom:${MODE_FEATURE_TYPE}` };
  }

  public static async getConfigElement(): Promise<HTMLElement> {
    return document.createElement(MODE_FEATURE_EDITOR_NAME);
  }

  public setConfig(config: ModeFeatureConfig): void {
    if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
    this._config = config;
  }

  private _entityId(): string | undefined {
    return this.context?.entity_id ?? this.stateObj?.entity_id;
  }

  protected shouldUpdate(changed: PropertyValues): boolean {
    if (!this._config) return false;
    if (!(changed.size === 1 && changed.has('hass'))) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    if (!old || !this.hass) return true;
    if ((old as HouseHass).entities !== (this.hass as HouseHass).entities) return true;
    return entityStateChanged(old, this.hass, this._watched);
  }

  private async _pick(calls: ServiceCall[]): Promise<void> {
    if (!this.hass || calls.length === 0) return;
    try {
      await runCalls(this.hass, calls);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.dispatchEvent(
        new CustomEvent('hass-notification', {
          detail: { message: t('house.action_failed', { message }) },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this._config || !this.hass) return nothing;
    const hass = this.hass;
    const target = modeTarget(hass, this._entityId());
    if (!target) {
      this._watched = [];
      return nothing;
    }
    let current: GroupMode | null;
    let holdEnabled: boolean;
    let plan: (m: WindowMode) => ServiceCall[];
    if (target.kind === 'window') {
      const w = target.window;
      current = windowMode(hass, w);
      holdEnabled = canHold(hass, [w]);
      plan = (m) => planWindowsMode(hass, [w], m);
      this._watched = [w.entities.mode, w.entities.manualOverride, w.entities.controlSwitch].filter(
        (id): id is string => !!id,
      );
    } else {
      const { model } = target;
      current = groupMode(model.windows.map((w) => windowMode(hass, w)));
      holdEnabled = hubCanHold(hass, model.hub);
      plan = (m) =>
        planHouseMode(hass, { hub: model.hub, windows: model.windows, useHub: true }, m);
      this._watched = [
        model.hub.modeSelect,
        ...model.windows.flatMap((w) => [
          w.entities.mode,
          w.entities.manualOverride,
          w.entities.controlSwitch,
        ]),
      ].filter((id): id is string => !!id);
    }
    return html`<div class="chips" role="group" aria-label=${t('mode_feature.label')}>
      ${MODES.map((m) => {
        const pressed = current === m;
        const disabled = m === 'hold' && !holdEnabled;
        return html`<button
          type="button"
          class="chip ${m} ${pressed ? 'on' : ''}"
          data-mode=${m}
          aria-pressed=${pressed ? 'true' : 'false'}
          aria-disabled=${disabled ? 'true' : 'false'}
          title=${disabled ? t('house.hold_disabled') : nothing}
          @click=${(e: Event) => {
            e.stopPropagation();
            if (!disabled && !pressed) void this._pick(plan(m));
          }}
        >
          ${t(`house.mode.${m}`)}
        </button>`;
      })}
    </div>`;
  }

  public static styles = css`
    :host {
      display: block;
    }
    .chips {
      display: flex;
      gap: var(--feature-button-spacing, 8px);
      height: var(--feature-height, 42px);
    }
    .chip {
      flex: 1 1 0;
      min-width: 0;
      border: none;
      border-radius: var(--feature-border-radius, 12px);
      background: rgba(127, 127, 127, 0.15);
      background: color-mix(in srgb, var(--primary-text-color, #000) 9%, transparent);
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .chip.on.auto {
      background: var(--tile-color, var(--primary-color, #03a9f4));
      color: var(--text-primary-color, #fff);
    }
    .chip.on.hold {
      background: var(--warning-color, #ffa600);
      color: #1f1f1f;
    }
    .chip.on.off {
      background: var(--secondary-text-color, #727272);
      color: var(--card-background-color, #fff);
    }
    .chip[aria-disabled='true'] {
      cursor: not-allowed;
      opacity: 0.5;
    }
    .chip:focus-visible {
      outline: 3px solid var(--primary-color, #03a9f4);
      outline-offset: 2px;
    }
  `;
}

/** The feature's editor: it has no options, so it only says what it does. */
@customElement(MODE_FEATURE_EDITOR_NAME)
export class AdaptiveCoverModeFeatureEditor extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @property({ attribute: false }) public context?: { entity_id?: string };
  @state() private _config?: ModeFeatureConfig;

  public setConfig(config: ModeFeatureConfig): void {
    this._config = config;
  }

  protected render(): TemplateResult | typeof nothing {
    if (!this._config) return nothing;
    const found = modeTarget(this.hass, this.context?.entity_id);
    return html`<p class="note">${t('mode_feature.editor_note')}</p>
      ${this.hass && this.context?.entity_id && !found
        ? html`<p class="warn">${t('mode_feature.not_found')}</p>`
        : nothing}`;
  }

  public static styles = css`
    .note,
    .warn {
      margin: 0 0 8px;
      line-height: 1.45;
      color: var(--secondary-text-color);
    }
    .warn {
      color: var(--warning-color, #ffa600);
    }
  `;
}

interface CustomCardFeatureEntry {
  type: string;
  name?: string;
  supported?: (a: unknown, b?: unknown) => boolean;
  configurable?: boolean;
}

declare global {
  interface Window {
    customCardFeatures?: CustomCardFeatureEntry[];
  }
}

window.customCardFeatures = window.customCardFeatures || [];
if (!window.customCardFeatures.some((f) => f.type === MODE_FEATURE_TYPE)) {
  window.customCardFeatures.push({
    type: MODE_FEATURE_TYPE,
    name: t('mode_feature.name'),
    supported: modeFeatureSupported,
    configurable: true,
  });
}
