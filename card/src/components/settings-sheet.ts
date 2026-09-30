import { LitElement, html, css, nothing, type PropertyValues, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { t } from '../lib/i18n';
import type { ProfileScope, SettingRow, WindowExceptions } from '../lib/profile-model';
import {
  FOLDED_SECTIONS,
  SECTIONS,
  formatValue,
  normalizeValue,
  numberShape,
  optionLabel,
  sameValue,
  settingHint,
  settingLabel,
  type ProfileSetting,
} from '../lib/profile-settings';

/*
 * The body of a settings sheet: the house, a floor or a room (the house
 * card draws the sheet frame around it). One row per setting: its name,
 * whether this level sets its own value or uses a wider one, the house
 * value, an editor, and the narrower levels that set their own value.
 *
 * The house sheet folds the rarely changed sections (movement limits,
 * weather and light sensors) and offers Clear for optional values.
 *
 * It only reports what the viewer does:
 *
 * - `acp-setting-set` {key, value}: store `value` (the card form: durations
 *   in minutes, times "HH:MM:SS"; null clears a house value) at this level;
 * - `acp-setting-reset` {key}: remove this level's value (floor and room);
 * - `acp-open-window` {key}: the viewer picked a window exception.
 */

const ENTITY_ID = /^[a-z_]+\.[a-z0-9_]+$/;

@customElement('acp-settings-sheet')
export class SettingsSheet extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public scope!: ProfileScope;
  @property({ attribute: false }) public rows: SettingRow[] = [];
  /** Windows with their own values (room and floor sheets). */
  @property({ attribute: false }) public windows: WindowExceptions[] = [];
  /** A save is running: the editors wait. */
  @property({ type: Boolean }) public busy = false;
  /** Nothing can be stored (the house has no layered settings yet). */
  @property({ type: Boolean }) public locked = false;

  /** Typed but not saved values, by setting key. */
  @state() private _drafts: Record<string, string> = {};

  protected willUpdate(changed: PropertyValues): void {
    const old = changed.get('scope') as ProfileScope | undefined;
    if (old && (old.level !== this.scope?.level || old.id !== this.scope?.id)) this._drafts = {};
  }

  private _emit(type: string, detail: Record<string, unknown>): void {
    this.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
  }

  private _set(key: string, value: unknown): void {
    const drafts = { ...this._drafts };
    delete drafts[key];
    this._drafts = drafts;
    this._emit('acp-setting-set', { key, value });
  }

  private _levelWord(): string {
    return t(`settings.level.${this.scope.level}`);
  }

  /** The editors wait (a save is running) or cannot store anything. */
  private get _off(): boolean {
    return this.busy || this.locked;
  }

  /** The value in effect at this level (own, else inherited). */
  private _effective(row: SettingRow): unknown {
    if (this.scope.level === 'house' || row.own) return row.value;
    return row.inherited?.value;
  }

  protected render(): TemplateResult {
    const sections = SECTIONS.map((section) => ({
      section,
      rows: this.rows.filter((r) => r.setting.section === section),
    })).filter((s) => s.rows.length > 0);
    return html`${this.windows.length > 0 ? this._renderWindows() : nothing}
    ${sections.map((s) =>
      FOLDED_SECTIONS.has(s.section)
        ? html`<details class="section folded" data-section=${s.section}>
            <summary class="eyebrow">${t(`settings.section.${s.section}`)}</summary>
            ${s.rows.map((r) => this._renderRow(r))}
          </details>`
        : html`<section class="section" data-section=${s.section}>
            <h3 class="eyebrow">${t(`settings.section.${s.section}`)}</h3>
            ${s.rows.map((r) => this._renderRow(r))}
          </section>`,
    )}`;
  }

  private _renderWindows(): TemplateResult {
    return html`<section class="windows">
      <h3 class="eyebrow">${t('settings.window_exceptions')}</h3>
      <p class="muted small">${t('settings.window_exceptions_hint')}</p>
      ${this.windows.map(
        (we) =>
          html`<button
            type="button"
            class="win"
            data-window=${we.window.key}
            @click=${() => this._emit('acp-open-window', { key: we.window.key })}
          >
            <span class="strong">${we.window.deviceName}</span>
            <span class="muted small"
              >${we.settings
                .map((s) =>
                  s.legacy
                    ? t('settings.legacy_setting', { name: settingLabel(s.key) })
                    : settingLabel(s.key),
                )
                .join(', ')}</span
            >
          </button>`,
      )}
    </section>`;
  }

  private _stateText(row: SettingRow): TemplateResult | typeof nothing {
    if (this.scope.level === 'house') return nothing;
    const s = row.setting;
    const level = this._levelWord();
    let text: string;
    let cls: string;
    if (row.own === true) {
      cls = 'own';
      text =
        row.value === undefined
          ? t('settings.state.own_unknown', { level })
          : t('settings.state.own', { level, value: formatValue(this.hass, s, row.value) });
    } else if (row.own === false && row.inherited) {
      cls = 'inherit';
      const from =
        row.inherited.level === 'floor'
          ? t('settings.state.from_floor', { floor: row.inherited.name ?? '' })
          : t('settings.state.from_house');
      text =
        row.inherited.value === undefined
          ? from
          : `${from}: ${formatValue(this.hass, s, row.inherited.value)}`;
    } else {
      cls = 'unknown';
      text = t('settings.state.unknown');
    }
    return html`<span class="state ${cls}">${text}</span>`;
  }

  private _houseText(row: SettingRow): TemplateResult | typeof nothing {
    if (this.scope.level === 'house') return nothing;
    const s = row.setting;
    const text = !s.levels.includes('house')
      ? t('settings.house_per_floor')
      : row.houseValue === undefined
        ? t('settings.house_unknown')
        : t('settings.house_value', { value: formatValue(this.hass, s, row.houseValue) });
    return html`<span class="house muted small">${text}</span>`;
  }

  private _renderRow(row: SettingRow): TemplateResult {
    const s = row.setting;
    const hint = settingHint(s.key);
    const canReset = this.scope.level !== 'house' && row.own === true;
    // The house may store "none" for an optional value (an entity, quiet hours).
    const canClear =
      this.scope.level === 'house' &&
      !!s.clearable &&
      row.value !== null &&
      row.value !== undefined;
    const resetLabel =
      row.inherited?.level === 'floor'
        ? t('settings.reset_floor', { floor: row.inherited.name ?? '' })
        : t('settings.reset');
    return html`<div class="row ${row.own === true ? 'is-own' : ''}" data-key=${s.key}>
      <div class="row-head">
        <span class="label">
          <span class="strong">${settingLabel(s.key)}</span>
          ${hint ? html`<span class="muted small">${hint}</span>` : nothing}
        </span>
        ${this._stateText(row)}
      </div>
      ${this._houseText(row)}
      <div class="edit">
        ${this._renderEditor(row)}
        ${canReset
          ? html`<button
              type="button"
              class="btn reset"
              ?disabled=${this._off}
              @click=${() => this._emit('acp-setting-reset', { key: s.key })}
            >
              ${resetLabel}
            </button>`
          : nothing}
        ${canClear
          ? html`<button
              type="button"
              class="btn clear"
              ?disabled=${this._off}
              @click=${() => this._set(s.key, null)}
            >
              ${t('settings.clear')}
            </button>`
          : nothing}
      </div>
      ${this._renderExceptions(row)}
    </div>`;
  }

  private _renderExceptions(row: SettingRow): TemplateResult | typeof nothing {
    if (row.exceptions.length === 0) return nothing;
    return html`<div class="exceptions" aria-label=${t('settings.exceptions')}>
      ${row.exceptions.map((e) => {
        const value =
          e.value === undefined ? '' : ` · ${formatValue(this.hass, row.setting, e.value)}`;
        const legacy = e.legacy ? ` ${t('settings.legacy_mark')}` : '';
        return html`<span class="exc ${e.level}" data-level=${e.level} data-id=${e.id}
          >${e.name}${value}${legacy}</span
        >`;
      })}
    </div>`;
  }

  private _renderEditor(row: SettingRow): TemplateResult {
    const s = row.setting;
    const effective = this._effective(row);
    if (s.kind === 'bool') {
      const current = effective === true ? 'on' : effective === false ? 'off' : null;
      return html`<div class="seg" role="group" aria-label=${settingLabel(s.key)}>
        ${(['on', 'off'] as const).map((v) => {
          const pressed = current === v;
          return html`<button
            type="button"
            class="seg-btn ${pressed ? 'on' : ''}"
            data-value=${v}
            aria-pressed=${pressed ? 'true' : 'false'}
            ?disabled=${this._off}
            @click=${() => {
              const value = v === 'on';
              // Pressing the value in effect stores it here only when this
              // level uses a wider one (it pins the value).
              if (pressed && (this.scope.level === 'house' || row.own)) return;
              this._set(s.key, value);
            }}
          >
            ${t(`settings.value.${v}`)}
          </button>`;
        })}
      </div>`;
    }
    if (s.kind === 'list') return this._renderList(row, effective);
    const draft = this._drafts[s.key];
    const shown =
      draft ?? (effective === undefined || effective === null ? '' : this._inputText(s, effective));
    const parsed = draft === undefined ? undefined : this._parse(s, draft);
    const valid = parsed !== undefined && parsed !== null;
    const unchanged =
      valid && (this.scope.level === 'house' || row.own) && sameValue(parsed, row.value);
    const canSave = !this._off && valid && !unchanged;
    // A room or floor that uses a wider value can store the shown value as is.
    const pin = !this._off && draft === undefined && this.scope.level !== 'house' && !row.own;
    const save = () => {
      if (canSave) this._set(s.key, parsed);
      else if (pin && effective !== undefined && effective !== null) this._set(s.key, effective);
    };
    const saveEnabled = canSave || (pin && effective !== undefined && effective !== null);
    const onInput = (e: Event) => {
      this._drafts = { ...this._drafts, [s.key]: (e.target as HTMLInputElement).value };
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') save();
    };
    let input: TemplateResult;
    if (s.kind === 'time') {
      input = html`<input
        type="time"
        class="input"
        aria-label=${settingLabel(s.key)}
        .value=${shown}
        ?disabled=${this._off}
        @input=${onInput}
        @keydown=${onKey}
      />`;
    } else if (s.kind === 'entity') {
      const listId = `acp-entities-${s.key}`;
      input = html`<input
          type="text"
          class="input entity"
          list=${listId}
          aria-label=${settingLabel(s.key)}
          placeholder=${(s.domains ?? []).map((d) => `${d}.…`).join(' / ')}
          .value=${shown}
          ?disabled=${this._off}
          @input=${onInput}
          @keydown=${onKey}
        />
        <datalist id=${listId}>
          ${this._entityOptions(s).map((id) => html`<option value=${id}></option>`)}
        </datalist>`;
    } else {
      const shape = numberShape(this.hass, s);
      input = html`<span class="num">
        <input
          type="number"
          class="input"
          aria-label=${settingLabel(s.key)}
          min=${shape.min ?? nothing}
          max=${shape.max ?? nothing}
          step=${shape.step ?? 'any'}
          .value=${shown}
          ?disabled=${this._off}
          @input=${onInput}
          @keydown=${onKey}
        />
        ${shape.unit ? html`<span class="unit muted">${shape.unit}</span>` : nothing}
      </span>`;
    }
    const saveLabel =
      this.scope.level === 'house'
        ? t('settings.save')
        : t('settings.save_here', { level: this._levelWord() });
    return html`${input}
      <button type="button" class="btn save" ?disabled=${!saveEnabled} @click=${save}>
        ${saveLabel}
      </button>`;
  }

  /** A `list` setting: one toggle per option, then Save. */
  private _renderList(row: SettingRow, effective: unknown): TemplateResult {
    const s = row.setting;
    const draft = this._drafts[s.key];
    const current: string[] =
      draft !== undefined
        ? draft.split('|').filter(Boolean)
        : Array.isArray(effective)
          ? effective.filter((x): x is string => typeof x === 'string')
          : [];
    const changed = draft !== undefined && !sameValue(current, row.value);
    const pin =
      draft === undefined && this.scope.level !== 'house' && !row.own && current.length > 0;
    const saveEnabled = !this._off && (changed || pin);
    const toggle = (option: string) => {
      const next = current.includes(option)
        ? current.filter((x) => x !== option)
        : (s.options ?? []).filter((o) => o === option || current.includes(o));
      this._drafts = { ...this._drafts, [s.key]: next.join('|') };
    };
    return html`<div class="options" role="group" aria-label=${settingLabel(s.key)}>
        ${(s.options ?? []).map((option) => {
          const on = current.includes(option);
          return html`<button
            type="button"
            class="opt ${on ? 'on' : ''}"
            data-option=${option}
            aria-pressed=${on ? 'true' : 'false'}
            ?disabled=${this._off}
            @click=${() => toggle(option)}
          >
            ${optionLabel(option)}
          </button>`;
        })}
      </div>
      <button
        type="button"
        class="btn save"
        ?disabled=${!saveEnabled}
        @click=${() => this._set(s.key, current)}
      >
        ${this.scope.level === 'house'
          ? t('settings.save')
          : t('settings.save_here', { level: this._levelWord() })}
      </button>`;
  }

  /** The editor text of a card value. */
  private _inputText(s: ProfileSetting, value: unknown): string {
    if (s.kind === 'time') return String(value).slice(0, 5);
    if (typeof value === 'number') return String(Math.round(value * 100) / 100);
    return String(value);
  }

  /** A typed value in card form; null when it is not valid. */
  private _parse(s: ProfileSetting, text: string): unknown {
    const trimmed = text.trim();
    if (s.kind === 'entity') return ENTITY_ID.test(trimmed) ? trimmed : null;
    const value = normalizeValue(s, trimmed);
    if (typeof value === 'number') {
      const shape = numberShape(this.hass, s);
      if (shape.min !== undefined && value < shape.min) return null;
      if (shape.max !== undefined && value > shape.max) return null;
    }
    return value;
  }

  private _entityOptions(s: ProfileSetting): string[] {
    const domains = new Set(s.domains ?? []);
    return Object.keys(this.hass?.states ?? {})
      .filter((id) => domains.has(id.slice(0, id.indexOf('.'))))
      .sort();
  }

  public static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      gap: 18px;
      color: var(--primary-text-color);
    }
    .eyebrow {
      margin: 0 0 4px;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .muted {
      color: var(--secondary-text-color);
    }
    .small {
      font-size: 0.85rem;
    }
    .strong {
      font-weight: 600;
    }
    .section,
    .windows {
      display: flex;
      flex-direction: column;
      gap: 0;
    }
    .windows p {
      margin: 0 0 6px;
    }
    .win {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
      padding: 10px 0;
      border: none;
      border-bottom: 1px solid var(--acp-line, var(--divider-color));
      background: transparent;
      color: var(--primary-text-color);
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 12px 0;
      border-bottom: 1px solid var(--acp-line, var(--divider-color));
    }
    .row-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }
    .label {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .state {
      flex-shrink: 0;
      max-width: 55%;
      text-align: right;
      font-size: 0.8rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--acp-track, #efefef);
    }
    .state.own {
      color: var(--primary-text-color);
      background: rgba(255, 166, 0, 0.3);
      background: color-mix(in srgb, var(--acp-hold, #ffa600) 30%, transparent);
    }
    .state.inherit,
    .state.unknown {
      font-weight: 600;
      color: var(--secondary-text-color);
    }
    .edit {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .num {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .input {
      box-sizing: border-box;
      min-height: 40px;
      width: 110px;
      padding: 0 10px;
      border: 1px solid var(--acp-line, var(--divider-color));
      border-radius: 10px;
      background: var(--acp-surface, var(--card-background-color));
      color: var(--primary-text-color);
      font: inherit;
    }
    .input.entity {
      width: 240px;
      max-width: 100%;
    }
    .btn {
      min-height: 40px;
      padding: 0 14px;
      border: 1px solid var(--acp-line, var(--divider-color));
      border-radius: 10px;
      background: var(--acp-surface, var(--card-background-color));
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .btn[disabled] {
      cursor: default;
      opacity: 0.5;
    }
    .btn.reset {
      border-style: dashed;
    }
    .seg {
      display: inline-flex;
      gap: 3px;
      padding: 3px;
      border-radius: 10px;
      background: var(--acp-track, #efefef);
    }
    .seg-btn {
      min-height: 36px;
      padding: 0 16px;
      border: none;
      border-radius: 8px;
      background: transparent;
      color: var(--primary-text-color);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .seg-btn.on {
      background: var(--acp-auto, var(--primary-color));
      color: var(--acp-on-auto, #fff);
    }
    .options {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .opt {
      min-height: 36px;
      padding: 0 12px;
      border: 1px solid var(--acp-line, var(--divider-color));
      border-radius: 999px;
      background: transparent;
      color: var(--primary-text-color);
      font: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
    }
    .opt.on {
      background: var(--acp-auto, var(--primary-color));
      border-color: var(--acp-auto, var(--primary-color));
      color: var(--acp-on-auto, #fff);
    }
    details.folded > summary {
      cursor: pointer;
      padding: 6px 0;
    }
    .exceptions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .exc {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: var(--acp-track, #efefef);
    }
    .exc.area {
      background: rgba(255, 166, 0, 0.22);
      background: color-mix(in srgb, var(--acp-hold, #ffa600) 22%, transparent);
    }
    .exc.floor {
      background: rgba(3, 169, 244, 0.16);
      background: color-mix(in srgb, var(--acp-auto, #03a9f4) 16%, transparent);
    }
    button:focus-visible,
    input:focus-visible {
      outline: 3px solid var(--acp-auto, var(--primary-color));
      outline-offset: 2px;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    'acp-settings-sheet': SettingsSheet;
  }
}
