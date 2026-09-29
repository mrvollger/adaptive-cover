import { LitElement, html, css, nothing, type PropertyValues, type TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { HomeAssistant } from 'custom-card-helpers';

import { HOUSE_CARD_NAME, INTEGRATION_DOMAIN } from './const';
import { entityStateChanged } from './lib/hass-change';
import { t } from './lib/i18n';
import { startMinuteTimer } from './lib/minute-timer';
import { loadEntityRegistry } from './lib/registry-store';
import type { EntityRegistryEntry } from './lib/entity-registry';
import { windowSettingsPath, windowSettingsTarget } from './lib/settings-link';
import {
  discoverHouse,
  watchedEntityIds,
  type GroupMode,
  type HouseFloor,
  type HouseHass,
  type HouseModel,
  type HouseRoom,
  type HouseWindow,
  type WindowMode,
} from './lib/house-model';
import {
  canHold,
  climateState,
  countModes,
  dominantClimateMethod,
  groupMode,
  hubCanHold,
  planClimate,
  planCovers,
  planHouseCovers,
  planHouseMode,
  planReturnAll,
  planWindowsMode,
  runCalls,
  windowStatus,
  type CoverCommand,
  type HouseScope,
  type ServiceCall,
  type WindowStatus,
} from './lib/house-actions';
import {
  chipText,
  countLabel,
  facesText,
  formatTimeOfDay,
  nextText,
  positionText,
  sunText,
  whyText,
} from './lib/house-format';
import type { AdaptiveCoverHouseCardConfig } from './types';

/*
 * The whole-house shade card (refactor plan P6, "UI"): header with the sun,
 * a "Whole house" bar, filter chips, then floors → rooms → window rows. A row
 * opens a detail sheet. Below 600 px it switches to the phone layout (one
 * column, collapsible rooms).
 *
 * Discovery and the mode mapping live in lib/house-model.ts and
 * lib/house-actions.ts; this file only renders and dispatches.
 */

type Filter = 'all' | 'sun' | 'hold' | 'off';
const FILTERS: Filter[] = ['all', 'sun', 'hold', 'off'];
const MODES: WindowMode[] = ['auto', 'hold', 'off'];
const NARROW_MAX_PX = 600;
const UPCOMING_LIMIT = 5;
const DAY_MS = 24 * 60 * 60 * 1000;
const SETTINGS_PATH = `/config/integrations/integration/${INTEGRATION_DOMAIN}`;

interface WindowView {
  w: HouseWindow;
  s: WindowStatus;
  floor: HouseFloor;
  room: HouseRoom;
}

interface RoomView {
  room: HouseRoom;
  key: string;
  all: WindowView[];
  shown: WindowView[];
  mode: GroupMode | null;
  sunCount: number;
}

interface FloorView {
  floor: HouseFloor;
  rooms: RoomView[];
  total: number;
}

interface UpcomingItem {
  time: string;
  what: string;
  detail: string;
}

function sunVisible(v: WindowView): boolean {
  return v.s.mode === 'auto' && v.s.sunOnGlass;
}

function keep(v: WindowView, filter: Filter): boolean {
  switch (filter) {
    case 'sun':
      return sunVisible(v);
    case 'hold':
      return v.s.mode === 'hold';
    case 'off':
      return v.s.mode === 'off';
    default:
      return true;
  }
}

function roomKey(floor: HouseFloor, room: HouseRoom): string {
  return `${floor.id ?? ''}|${room.id ?? ''}`;
}

@customElement(HOUSE_CARD_NAME)
export class AdaptiveCoverHouseCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;

  @state() private _config?: AdaptiveCoverHouseCardConfig;
  @state() private _filter: Filter = 'all';
  /** Window key of the open detail sheet. */
  @state() private _selected: string | null = null;
  @state() private _width = 0;
  /** Phone layout: rooms the viewer opened or closed (default: open when a
   *  window needs attention). */
  @state() private _expanded: Record<string, boolean> = {};
  @state() private _registry: EntityRegistryEntry[] | null = null;

  private _watched: string[] = [];
  private _registryFor: unknown = null;
  private _resizeObserver: ResizeObserver | null = null;
  private _cancelMinuteTimer: (() => void) | null = null;
  private _focusSheet = false;

  public setConfig(config: AdaptiveCoverHouseCardConfig): void {
    if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
    for (const key of ['floors', 'areas'] as const) {
      const v = config[key];
      if (v !== undefined && !(Array.isArray(v) && v.every((x) => typeof x === 'string'))) {
        throw new Error(`adaptive-cover-house-card: \`${key}\` must be a list of ids`);
      }
    }
    this._config = { ...config };
  }

  public static getStubConfig(): AdaptiveCoverHouseCardConfig {
    return { type: `custom:${HOUSE_CARD_NAME}` };
  }

  /** The card editor: HA renders this schema with ha-form. */
  public static getConfigForm() {
    const layoutOptions = (['auto', 'wide', 'narrow'] as const).map((value) => ({
      value,
      label: t(`editor.house.layout_${value}`),
    }));
    return {
      schema: [
        { name: 'title', selector: { text: {} } },
        { name: 'floors', selector: { floor: { multiple: true } } },
        { name: 'areas', selector: { area: { multiple: true } } },
        {
          name: 'layout',
          selector: { select: { mode: 'dropdown', options: layoutOptions } },
        },
        { name: 'show_upcoming', selector: { boolean: {} } },
      ],
      computeLabel: (s: { name: string }) => t(`editor.house.${s.name}`),
      computeHelper: (s: { name: string }) => {
        const key = `editor.house.${s.name}_help`;
        const text = t(key);
        return text === key ? undefined : text;
      },
    };
  }

  public getCardSize(): number {
    return 12;
  }

  public getGridOptions() {
    return { columns: 'full', rows: 'auto', min_columns: 6 };
  }

  public connectedCallback(): void {
    super.connectedCallback();
    this._cancelMinuteTimer ??= startMinuteTimer(() => this.requestUpdate());
    if (typeof ResizeObserver !== 'undefined' && !this._resizeObserver) {
      this._resizeObserver = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width ?? 0;
        if (Math.abs(width - this._width) >= 1) this._width = width;
      });
      this._resizeObserver.observe(this);
    }
  }

  public disconnectedCallback(): void {
    super.disconnectedCallback();
    this._cancelMinuteTimer?.();
    this._cancelMinuteTimer = null;
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
    window.removeEventListener('keydown', this._onKeydown);
  }

  protected shouldUpdate(changed: PropertyValues): boolean {
    if (!this._config) return false;
    if (!(changed.size === 1 && changed.has('hass'))) return true;
    const old = changed.get('hass') as HomeAssistant | undefined;
    if (!old || !this.hass) return true;
    const a = old as HouseHass;
    const b = this.hass as HouseHass;
    if (
      a.entities !== b.entities ||
      a.devices !== b.devices ||
      a.areas !== b.areas ||
      a.floors !== b.floors ||
      (a as unknown as { locale?: unknown }).locale !==
        (b as unknown as { locale?: unknown }).locale
    ) {
      return true;
    }
    return entityStateChanged(old, this.hass, this._watched);
  }

  protected updated(changed: PropertyValues): void {
    if (changed.has('_selected')) {
      if (this._selected) {
        window.addEventListener('keydown', this._onKeydown);
        this._focusSheet = true;
      } else {
        window.removeEventListener('keydown', this._onKeydown);
      }
    }
    if (this._focusSheet) {
      const btn = this.renderRoot.querySelector<HTMLElement>('.sheet .close');
      if (btn) {
        this._focusSheet = false;
        btn.focus();
      }
    }
  }

  private _onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this._selected = null;
  };

  // ---------------------------------------------------------------- model

  private _model(): HouseModel {
    const cfg = this._config!;
    const model = discoverHouse(this.hass, this._registry, {
      floors: cfg.floors,
      areas: cfg.areas,
    });
    // An integration without translation keys: classify by unique_id.
    const entities = (this.hass as HouseHass).entities;
    if (model.needsRegistry && this._registryFor !== entities) {
      this._registryFor = entities;
      loadEntityRegistry(this.hass, this._registry !== null)
        .then((rows) => {
          this._registry = Array.isArray(rows) ? rows : [];
        })
        .catch(() => {
          /* keep what the display registry gave */
        });
    }
    return model;
  }

  private _filtered(): boolean {
    const cfg = this._config!;
    return (cfg.floors?.length ?? 0) > 0 || (cfg.areas?.length ?? 0) > 0;
  }

  private _scope(model: HouseModel): HouseScope {
    return { hub: model.hub, windows: model.windows, useHub: !this._filtered() };
  }

  private _narrow(): boolean {
    const layout = this._config?.layout ?? 'auto';
    if (layout === 'narrow') return true;
    if (layout === 'wide') return false;
    return this._width > 0 && this._width < NARROW_MAX_PX;
  }

  private _views(model: HouseModel): FloorView[] {
    return model.floors.map((floor) => {
      const rooms = floor.rooms.map((room) => {
        const all = room.windows.map((w) => ({ w, s: windowStatus(this.hass, w), floor, room }));
        return {
          room,
          key: roomKey(floor, room),
          all,
          shown: all.filter((v) => keep(v, this._filter)),
          mode: groupMode(all.map((v) => v.s.mode)),
          sunCount: all.filter(sunVisible).length,
        };
      });
      return { floor, rooms, total: rooms.reduce((n, r) => n + r.all.length, 0) };
    });
  }

  // -------------------------------------------------------------- actions

  private async _run(calls: ServiceCall[]): Promise<void> {
    if (calls.length === 0) return;
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

  private _setWindows(windows: HouseWindow[], mode: WindowMode): void {
    void this._run(planWindowsMode(this.hass, windows, mode));
  }

  private _navigate(e: Event, path: string): void {
    e.preventDefault();
    history.pushState(null, '', path);
    window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } }));
    this._selected = null;
  }

  // --------------------------------------------------------------- render

  protected render(): TemplateResult | typeof nothing {
    if (!this._config || !this.hass) return nothing;
    const model = this._model();
    this._watched = watchedEntityIds(model);
    const now = Date.now();
    const floors = this._views(model);
    const views = floors.flatMap((f) => f.rooms.flatMap((r) => r.all));
    const narrow = this._narrow();

    if (views.length === 0) {
      return html`<ha-card>
        <div class="root ${narrow ? 'narrow' : 'wide'}">
          ${this._renderHeader(model, floors, narrow)}
          <p class="empty">${t('house.empty')}</p>
        </div>
      </ha-card>`;
    }

    const selected = this._selected ? views.find((v) => v.w.key === this._selected) : undefined;
    return html`<ha-card>
      <div class="root ${narrow ? 'narrow' : 'wide'}">
        ${this._renderHeader(model, floors, narrow)} ${this._renderHouseBar(model, views, narrow)}
        ${narrow
          ? floors.map((f) => this._renderPhoneFloor(f, now))
          : html`${this._renderFilters(views)} ${this._renderWide(floors, views, now)}`}
      </div>
      ${selected ? this._renderSheet(selected, now, narrow) : nothing}
    </ha-card>`;
  }

  private _renderHeader(model: HouseModel, floors: FloorView[], narrow: boolean): TemplateResult {
    const sun = sunText(this.hass, narrow);
    const rooms = floors.reduce((n, f) => n + f.rooms.length, 0);
    const realFloors = floors.filter((f) => f.floor.id !== null).length;
    const parts = [countLabel('window', model.windows.length), countLabel('room', rooms)];
    if (realFloors > 0) parts.push(countLabel('floor', realFloors));
    return html`<header class="top">
      <div class="titles">
        <h1>${this._config?.title || t('house.title')}</h1>
        ${narrow ? nothing : html`<div class="muted sub">${parts.join(' · ')}</div>`}
      </div>
      ${sun
        ? html`<div class="sun-pill">
            <ha-icon icon="mdi:white-balance-sunny"></ha-icon><span>${sun}</span>
          </div>`
        : nothing}
    </header>`;
  }

  private _houseLabel(modes: WindowMode[], narrow: boolean): string {
    const mode = groupMode(modes);
    if (mode === 'mixed') {
      const c = countModes(modes);
      return t(
        narrow ? 'house.mixed_short' : 'house.mixed_long',
        c as unknown as Record<string, unknown>,
      );
    }
    return t(`house.all_${mode ?? 'auto'}`);
  }

  private _renderHouseBar(model: HouseModel, views: WindowView[], narrow: boolean): TemplateResult {
    const scope = this._scope(model);
    const modes = views.map((v) => v.s.mode);
    const mode = groupMode(modes);
    const holdEnabled =
      scope.useHub && model.hub.modeSelect
        ? hubCanHold(this.hass, model.hub)
        : canHold(this.hass, model.windows);
    const heading = this._filtered() ? t('house.these_windows') : t('house.whole_house');
    const segs = this._segmented(
      mode,
      t('house.house_mode_label'),
      holdEnabled,
      (m) => void this._run(planHouseMode(this.hass, scope, m)),
      'lg',
    );
    const returnAll = html`<button
      type="button"
      class="btn return-all"
      @click=${() => void this._run(planReturnAll(this.hass, scope))}
    >
      ${t('house.return_all')}
    </button>`;
    const settings = html`<a
      class="link settings"
      href=${SETTINGS_PATH}
      @click=${(e: Event) => this._navigate(e, SETTINGS_PATH)}
      ><ha-icon icon="mdi:tune-variant"></ha-icon>${narrow
        ? t('house.settings_short')
        : t('house.settings')}</a
    >`;

    if (narrow) {
      return html`<section class="house-bar narrow-bar">
        <div class="bar-head">
          <span class="bar-title">${heading}</span>
          <span class="muted">${this._houseLabel(modes, true)}</span>
        </div>
        ${segs}
        <div class="bar-row">${returnAll} ${settings}</div>
      </section>`;
    }

    return html`<section class="house-bar">
      <div class="bar-label">
        <div class="eyebrow">${heading}</div>
        <div class="bar-state">${this._houseLabel(modes, false)}</div>
      </div>
      ${segs} ${returnAll}
      <div class="pair">
        <button
          type="button"
          class="btn open-all"
          @click=${() => void this._run(planHouseCovers(scope, 'open'))}
        >
          ${t('house.open_all')}
        </button>
        <button
          type="button"
          class="btn close-all"
          @click=${() => void this._run(planHouseCovers(scope, 'close'))}
        >
          ${t('house.close_all')}
        </button>
      </div>
      <div class="grow"></div>
      ${this._renderClimate(model.windows)} ${settings}
    </section>`;
  }

  private _renderClimate(windows: HouseWindow[]): TemplateResult | typeof nothing {
    const st = climateState(this.hass, windows);
    if (st === null) return nothing;
    let text: string;
    if (st === 'on') {
      const method = dominantClimateMethod(this.hass, windows);
      text = t(`house.climate_state.${method ?? 'on'}`);
    } else if (st === 'off') {
      text = t('house.climate_state.off');
    } else {
      const withSwitch = windows.filter((w) => w.entities.climateSwitch);
      const on = withSwitch.filter(
        (w) => this.hass.states[w.entities.climateSwitch!]?.state === 'on',
      ).length;
      text = t('house.climate_state.mixed', { on, total: withSwitch.length });
    }
    return html`<button
      type="button"
      class="btn climate ${st}"
      aria-pressed=${st === 'on' ? 'true' : st === 'off' ? 'false' : 'mixed'}
      @click=${() => void this._run(planClimate(windows, st !== 'on'))}
    >
      <span class="track"><span class="knob"></span></span>
      <span class="strong">${t('house.climate')}</span>
      <span class="muted">${text}</span>
    </button>`;
  }

  private _segmented(
    current: GroupMode | null,
    label: string,
    holdEnabled: boolean,
    onPick: (m: WindowMode) => void,
    size: 'lg' | 'sm',
  ): TemplateResult {
    return html`<div class="seg ${size}" role="group" aria-label=${label}>
      ${MODES.map((m) => {
        const pressed = current === m;
        const disabled = m === 'hold' && !holdEnabled;
        return html`<button
          type="button"
          class="seg-btn ${m} ${pressed ? 'on' : ''}"
          data-mode=${m}
          aria-pressed=${pressed ? 'true' : 'false'}
          aria-disabled=${disabled ? 'true' : 'false'}
          title=${disabled ? t('house.hold_disabled') : nothing}
          @click=${() => {
            if (!disabled && !pressed) onPick(m);
          }}
        >
          ${t(`house.mode.${m}`)}
        </button>`;
      })}
    </div>`;
  }

  private _renderFilters(views: WindowView[]): TemplateResult {
    const counts: Record<Filter, number> = {
      all: views.length,
      sun: views.filter(sunVisible).length,
      hold: views.filter((v) => v.s.mode === 'hold').length,
      off: views.filter((v) => v.s.mode === 'off').length,
    };
    return html`<div class="filters" role="group" aria-label=${t('house.filter.label')}>
      ${FILTERS.map(
        (f) =>
          html`<button
            type="button"
            class="chip-btn ${this._filter === f ? 'on' : ''}"
            data-filter=${f}
            aria-pressed=${this._filter === f ? 'true' : 'false'}
            @click=${() => (this._filter = f)}
          >
            ${t(`house.filter.${f}`, { n: counts[f] })}
          </button>`,
      )}
    </div>`;
  }

  /** Floors with several rooms get a full-width row; runs of one-room floors
   *  share a grid row (with "Coming up" at the end), as in the mockup. */
  private _renderWide(floors: FloorView[], views: WindowView[], now: number): TemplateResult {
    const visible = floors
      .map((f) => ({ ...f, rooms: f.rooms.filter((r) => r.shown.length > 0) }))
      .filter((f) => f.rooms.length > 0);
    const upcoming = this._config?.show_upcoming === false ? [] : this._upcoming(views, now);

    type Block = { wide: FloorView } | { pack: FloorView[] };
    const blocks: Block[] = [];
    for (const f of visible) {
      const last = blocks[blocks.length - 1];
      if (f.rooms.length > 1) blocks.push({ wide: f });
      else if (last && 'pack' in last) last.pack.push(f);
      else blocks.push({ pack: [f] });
    }
    const upcomingSection = upcoming.length > 0 ? this._renderUpcoming(upcoming) : nothing;
    const last = blocks[blocks.length - 1];
    const upcomingPacked = !!last && 'pack' in last;

    return html`${visible.length === 0
      ? html`<p class="empty">${t('house.empty_filter')}</p>`
      : nothing}
    ${blocks.map((b, i) =>
      'wide' in b
        ? html`<section class="floor">
            ${this._floorHead(b.wide)}
            <div class="grid">${b.wide.rooms.map((r) => this._renderRoom(r, now))}</div>
          </section>`
        : html`<div class="grid">
            ${b.pack.map(
              (f) =>
                html`<section class="floor">
                  ${this._floorHead(f)} ${f.rooms.map((r) => this._renderRoom(r, now))}
                </section>`,
            )}
            ${upcomingPacked && i === blocks.length - 1 ? upcomingSection : nothing}
          </div>`,
    )}
    ${upcomingPacked ? nothing : upcomingSection}`;
  }

  private _floorHead(f: FloorView): TemplateResult | typeof nothing {
    if (!f.floor.name) return nothing;
    return html`<div class="floor-head">
      <h2>${f.floor.name}</h2>
      <span class="muted">${countLabel('window', f.total)}</span>
    </div>`;
  }

  private _roomSummary(r: RoomView): string {
    const parts = [countLabel('window', r.all.length)];
    if (r.sunCount > 0) parts.push(t('house.room_sun', { n: r.sunCount }));
    if (r.mode === 'mixed') parts.push(t('house.room_mixed'));
    return parts.join(' · ');
  }

  private _roomSegments(r: RoomView, size: 'lg' | 'sm'): TemplateResult {
    const windows = r.all.map((v) => v.w);
    return this._segmented(
      r.mode,
      t('house.room_mode_label', { room: r.room.name }),
      canHold(this.hass, windows),
      (m) => this._setWindows(windows, m),
      size,
    );
  }

  private _renderRoom(r: RoomView, now: number): TemplateResult {
    return html`<div class="room" data-room=${r.room.id ?? ''}>
      <div class="room-head">
        <div class="room-title">
          <h3>${r.room.name}</h3>
          <span class="muted">${this._roomSummary(r)}</span>
        </div>
        ${this._roomSegments(r, 'sm')}
      </div>
      ${r.shown.map((v) => this._renderRow(v, now))}
    </div>`;
  }

  private _glyph(s: WindowStatus, big = false): TemplateResult {
    const fabric = s.position === null ? 0 : Math.max(0, Math.min(100, 100 - s.position));
    return html`<span
      class="glyph ${big ? 'big' : ''} ${s.sunOnGlass ? 'sun' : ''}"
      style="--fabric: ${fabric}%"
      aria-hidden="true"
      ><span class="fabric"></span
    ></span>`;
  }

  private _renderRow(v: WindowView, now: number): TemplateResult {
    const { w, s } = v;
    return html`<button
      type="button"
      class="row"
      data-window=${w.key}
      @click=${() => (this._selected = w.key)}
    >
      ${this._glyph(s)}
      <span class="row-main">
        <span class="row-name"
          >${w.name}${sunVisible(v)
            ? html`<ha-icon
                class="sun-icon"
                icon="mdi:white-balance-sunny"
                title=${t('house.sun_on_glass')}
              ></ha-icon>`
            : nothing}</span
        >
        <span class="row-next muted">${nextText(this.hass, s, now)}</span>
      </span>
      <span class="row-end">
        <span class="pos">${positionText(s)}</span>
        <span class="chip ${s.mode}">${chipText(s, now)}</span>
      </span>
    </button>`;
  }

  private _renderPhoneFloor(f: FloorView, now: number): TemplateResult | typeof nothing {
    if (f.rooms.length === 0) return nothing;
    return html`<section class="floor">
      ${f.floor.name ? html`<h2 class="phone-floor">${f.floor.name}</h2>` : nothing}
      ${f.rooms.map((r) => this._renderPhoneRoom(r, now))}
    </section>`;
  }

  private _renderPhoneRoom(r: RoomView, now: number): TemplateResult {
    const needsAttention = r.all.some((v) => v.s.mode !== 'auto');
    const expanded = this._expanded[r.key] ?? needsAttention;
    const chipMode = r.mode ?? 'auto';
    return html`<div class="room phone-room" data-room=${r.room.id ?? ''}>
      <button
        type="button"
        class="room-toggle"
        aria-expanded=${expanded ? 'true' : 'false'}
        @click=${() => (this._expanded = { ...this._expanded, [r.key]: !expanded })}
      >
        <span class="room-title">
          <span class="strong">${r.room.name}</span>
          <span class="muted">${this._roomSummary(r)}</span>
        </span>
        <span class="chip ${chipMode}">${t(`house.mode.${chipMode}`)}</span>
        <ha-icon class="chevron ${expanded ? 'open' : ''}" icon="mdi:chevron-right"></ha-icon>
      </button>
      ${expanded
        ? html`<div class="room-body">
            ${this._roomSegments(r, 'lg')} ${r.all.map((v) => this._renderRow(v, now))}
          </div>`
        : nothing}
    </div>`;
  }

  private _upcoming(views: WindowView[], now: number): UpcomingItem[] {
    interface Group {
      at: number;
      time: string;
      position: number | null;
      names: string[];
    }
    const groups: Group[] = [];
    for (const v of views) {
      if (v.s.mode !== 'auto' || !v.s.nextMove) continue;
      const at = Date.parse(v.s.nextMove.time);
      if (Number.isNaN(at) || at < now - 60_000 || at > now + DAY_MS) continue;
      const minute = Math.floor(at / 60_000);
      const g = groups.find(
        (x) => Math.floor(x.at / 60_000) === minute && x.position === v.s.nextMove!.position,
      );
      if (g) g.names.push(v.w.deviceName);
      else
        groups.push({
          at,
          time: v.s.nextMove.time,
          position: v.s.nextMove.position,
          names: [v.w.deviceName],
        });
    }
    const items: Array<{ at: number } & UpcomingItem> = groups.map((g) => ({
      at: g.at,
      time: formatTimeOfDay(this.hass, g.time),
      what: g.names.join(', '),
      detail:
        g.position === null
          ? t('house.upcoming.changes')
          : t('house.upcoming.follows', { position: `${Math.round(g.position)}%` }),
    }));
    const sun = this.hass.states['sun.sun'];
    const setting = sun?.state === 'above_horizon' ? sun.attributes?.next_setting : undefined;
    const setAt = typeof setting === 'string' ? Date.parse(setting) : NaN;
    if (!Number.isNaN(setAt) && setAt > now && setAt < now + DAY_MS) {
      items.push({
        at: setAt,
        time: formatTimeOfDay(this.hass, setting as string),
        what: t('house.upcoming.sunset'),
        detail: t('house.upcoming.sunset_detail'),
      });
    }
    items.sort((a, b) => a.at - b.at);
    return items.slice(0, UPCOMING_LIMIT);
  }

  private _renderUpcoming(items: UpcomingItem[]): TemplateResult {
    return html`<section class="floor upcoming">
      <div class="floor-head">
        <h2>${t('house.upcoming.title')}</h2>
        <span class="muted">${t('house.upcoming.today')}</span>
      </div>
      <div class="room upcoming-list">
        ${items.map(
          (u) =>
            html`<div class="up-row">
              <span class="up-time">${u.time}</span>
              <span class="up-main">
                <span class="strong">${u.what}</span>
                <span class="muted">${u.detail}</span>
              </span>
            </div>`,
        )}
      </div>
    </section>`;
  }

  private _renderSheet(v: WindowView, now: number, narrow: boolean): TemplateResult {
    const { w, s } = v;
    const where = [v.floor.name, v.room.name].filter(Boolean).join(' · ');
    const holdEnabled = canHold(this.hass, [w]);
    const setupPath = windowSettingsPath(
      windowSettingsTarget({
        window_key: w.key,
        config_entry_id: w.configEntryId,
        config_subentry_id: w.configSubentryId,
      }),
    );
    const faces = facesText(s);
    const cover = (cmd: CoverCommand) => () => void this._run(planCovers([w], cmd));
    const showTarget =
      s.target !== null && s.position !== null && Math.round(s.target) !== Math.round(s.position);
    return html`<div class="scrim" @click=${() => (this._selected = null)}></div>
      <aside
        class="sheet ${narrow ? 'bottom' : 'side'}"
        role="dialog"
        aria-modal="true"
        aria-label=${t('house.sheet.label')}
      >
        <div class="sheet-head">
          <div class="sheet-title">
            <span class="muted">${where}</span>
            <h2>${w.name}</h2>
          </div>
          <button
            type="button"
            class="close icon-btn"
            aria-label=${t('house.sheet.close')}
            @click=${() => (this._selected = null)}
          >
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <div class="sheet-pos">
          ${this._glyph(s, true)}
          <div class="sheet-pos-text">
            <span class="big-pos">${positionText(s)}</span>
            <span class="muted">${t('house.sheet.open_word')}</span>
            ${showTarget
              ? html`<span class="muted target"
                  >${t('house.sheet.target', { position: `${Math.round(s.target!)}%` })}</span
                >`
              : nothing}
            <span class="chip ${s.mode}">${chipText(s, now)}</span>
          </div>
        </div>
        <div class="cmds">
          <button type="button" class="btn cmd-open" @click=${cover('open')}>
            ${t('house.sheet.open')}
          </button>
          <button type="button" class="btn cmd-stop" @click=${cover('stop')}>
            ${t('house.sheet.stop')}
          </button>
          <button type="button" class="btn cmd-close" @click=${cover('close')}>
            ${t('house.sheet.close_cover')}
          </button>
        </div>
        <div class="mode-block">
          <span class="eyebrow">${t('house.sheet.mode')}</span>
          ${this._segmented(
            s.mode,
            t('house.window_mode_label'),
            holdEnabled,
            (m) => this._setWindows([w], m),
            'lg',
          )}
          ${holdEnabled ? nothing : html`<p class="hint muted">${t('house.sheet.hold_hint')}</p>`}
        </div>
        <div class="why">
          <span class="eyebrow">${t('house.why.title')}</span>
          <p class="why-text">${whyText(this.hass, s)}</p>
          <p class="muted">${nextText(this.hass, s, now)}</p>
          ${s.mode === 'auto' && s.trace.length > 1
            ? html`<details>
                <summary>${t('house.why.steps')}</summary>
                <ol>
                  ${s.trace.map((line) => html`<li>${line}</li>`)}
                </ol>
              </details>`
            : nothing}
        </div>
        <div class="grow"></div>
        <div class="sheet-foot">
          <span class="setup">
            <a class="link" href=${setupPath} @click=${(e: Event) => this._navigate(e, setupPath)}
              >${t('house.sheet.setup')}</a
            >
            <span class="muted">${t('house.sheet.setup_hint')}</span>
          </span>
          ${faces ? html`<span class="muted">${faces}</span>` : nothing}
        </div>
      </aside>`;
  }

  public static styles = css`
    :host {
      display: block;
      --acp-auto: var(--primary-color, #03a9f4);
      --acp-on-auto: var(--text-primary-color, #fff);
      --acp-hold: var(--warning-color, #ffa600);
      --acp-on-hold: #1f1f1f;
      --acp-off: var(--secondary-text-color, #727272);
      --acp-on-off: var(--card-background-color, #fff);
      --acp-sun: var(--amber-color, #ffc107);
      --acp-sun-strong: var(--orange-color, #ff9800);
      --acp-line: var(--divider-color, rgba(0, 0, 0, 0.12));
      --acp-surface: var(--card-background-color, var(--ha-card-background, #fff));
      --acp-track: var(--secondary-background-color, #efefef);
      --acp-radius: 14px;
    }
    .root {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 20px 24px 24px;
      color: var(--primary-text-color);
      font-variant-numeric: tabular-nums;
    }
    .root.narrow {
      gap: 14px;
      padding: 16px;
    }
    .muted {
      color: var(--secondary-text-color);
    }
    .strong {
      font-weight: 600;
    }
    .eyebrow {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .grow {
      flex-grow: 1;
    }
    .empty {
      margin: 0;
      color: var(--secondary-text-color);
    }
    button {
      font: inherit;
      cursor: pointer;
    }
    button:focus-visible,
    a:focus-visible {
      outline: 3px solid var(--acp-auto);
      outline-offset: 2px;
    }
    .link {
      color: var(--primary-color);
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .link ha-icon {
      --mdc-icon-size: 18px;
    }

    /* Header */
    .top {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      flex-wrap: wrap;
    }
    .narrow .top {
      align-items: center;
    }
    .titles {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    h1 {
      margin: 0;
      font-size: 2.2rem;
      font-weight: 600;
      letter-spacing: -0.5px;
      line-height: 1.1;
    }
    .narrow h1 {
      font-size: 1.8rem;
    }
    .sub {
      font-size: 0.95rem;
    }
    .sun-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 0.95rem;
      background: rgba(255, 193, 7, 0.16);
      background: color-mix(in srgb, var(--acp-sun) 18%, transparent);
    }
    .sun-pill ha-icon {
      --mdc-icon-size: 18px;
      color: var(--acp-sun-strong);
    }
    .narrow .sun-pill {
      padding: 6px 12px;
      font-size: 0.85rem;
    }

    /* Buttons */
    .btn {
      min-height: 44px;
      padding: 0 16px;
      border: 1px solid var(--acp-line);
      border-radius: 10px;
      background: var(--acp-surface);
      color: var(--primary-text-color);
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }
    .btn:hover {
      background: var(--acp-track);
    }
    .pair {
      display: flex;
      gap: 8px;
    }

    /* Whole-house bar */
    .house-bar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px 14px;
      padding: 16px 20px;
      border: 1px solid var(--acp-line);
      border-radius: 16px;
    }
    .bar-label {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 170px;
    }
    .house-bar:not(.narrow-bar) .settings {
      margin-left: auto;
    }
    .bar-state {
      font-size: 1.05rem;
      font-weight: 600;
    }
    .narrow-bar {
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
      padding: 14px;
    }
    .bar-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
    }
    .bar-title {
      font-size: 1.05rem;
      font-weight: 700;
    }
    .bar-row {
      display: flex;
      gap: 8px;
    }
    .bar-row .return-all {
      flex-grow: 1;
    }
    .bar-row .settings {
      min-height: 44px;
      padding: 0 12px;
      border: 1px solid var(--acp-line);
      border-radius: 10px;
    }
    .climate {
      padding-left: 8px;
    }
    .climate .track {
      width: 40px;
      height: 24px;
      border-radius: 999px;
      padding: 0 3px;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      background: var(--disabled-text-color, #bdbdbd);
    }
    .climate.on .track {
      justify-content: flex-end;
      background: var(--acp-auto);
    }
    .climate.mixed .track {
      justify-content: center;
      background: var(--acp-hold);
    }
    .climate .knob {
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: #fff;
    }
    .climate .muted {
      font-weight: 400;
    }

    /* Segmented Auto / Hold / Off */
    .seg {
      display: flex;
      gap: 4px;
      padding: 4px;
      border-radius: 12px;
      background: var(--acp-track);
    }
    .seg.sm {
      gap: 3px;
      padding: 3px;
      border-radius: 10px;
    }
    .seg-btn {
      flex-grow: 1;
      min-height: 44px;
      padding: 0 18px;
      border: none;
      border-radius: 9px;
      background: transparent;
      color: var(--primary-text-color);
      font-weight: 600;
    }
    .seg.sm .seg-btn {
      min-height: 36px;
      padding: 0 10px;
      border-radius: 8px;
      font-size: 0.85rem;
    }
    .seg-btn[aria-disabled='true'] {
      cursor: not-allowed;
      color: var(--disabled-text-color, #9e9e9e);
      opacity: 0.6;
    }
    .seg-btn.on[aria-disabled='true'] {
      opacity: 1;
    }
    .seg-btn.on.auto {
      background: var(--acp-auto);
      color: var(--acp-on-auto);
    }
    .seg-btn.on.hold {
      background: var(--acp-hold);
      color: var(--acp-on-hold);
    }
    .seg-btn.on.off {
      background: var(--acp-off);
      color: var(--acp-on-off);
    }

    /* Filter chips */
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip-btn {
      min-height: 40px;
      padding: 0 16px;
      border-radius: 999px;
      border: 1px solid var(--acp-line);
      background: var(--acp-surface);
      color: var(--primary-text-color);
      font-weight: 600;
      font-size: 0.9rem;
    }
    .chip-btn.on {
      background: var(--primary-text-color);
      color: var(--acp-surface);
      border-color: var(--primary-text-color);
    }

    /* Floors and rooms */
    .floor {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }
    .floor-head {
      display: flex;
      align-items: baseline;
      gap: 12px;
    }
    h2 {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 16px;
      align-items: start;
    }
    .room {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 14px;
      border: 1px solid var(--acp-line);
      border-radius: var(--acp-radius);
      background: var(--acp-surface);
      min-width: 0;
    }
    .room-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 2px 4px 8px;
      flex-wrap: wrap;
    }
    .room-title {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    h3 {
      margin: 0;
      font-size: 1.05rem;
      font-weight: 700;
    }
    .room-title .muted {
      font-size: 0.85rem;
    }

    /* Window rows */
    .row {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      min-height: 60px;
      padding: 8px;
      border: none;
      border-radius: 10px;
      background: transparent;
      color: var(--primary-text-color);
      text-align: left;
    }
    .row:hover {
      background: var(--acp-track);
    }
    .row-main {
      display: flex;
      flex-direction: column;
      flex-grow: 1;
      gap: 2px;
      min-width: 0;
    }
    .row-name {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
    }
    .sun-icon {
      --mdc-icon-size: 16px;
      color: var(--acp-sun-strong);
    }
    .row-next {
      font-size: 0.85rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .row-end {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 4px;
    }
    .pos {
      font-size: 1.05rem;
      font-weight: 700;
    }
    .chip {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 999px;
      white-space: nowrap;
    }
    .chip.auto {
      color: var(--acp-auto);
      background: rgba(3, 169, 244, 0.14);
      background: color-mix(in srgb, var(--acp-auto) 15%, transparent);
    }
    .chip.hold {
      color: var(--primary-text-color);
      background: rgba(255, 166, 0, 0.3);
      background: color-mix(in srgb, var(--acp-hold) 32%, transparent);
    }
    .chip.off,
    .chip.mixed {
      color: var(--primary-text-color);
      background: var(--acp-track);
    }

    /* Shade glyph: the fabric covers (100 - position)% from the top. */
    .glyph {
      width: 28px;
      height: 38px;
      flex-shrink: 0;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 2px solid var(--primary-text-color);
      border-radius: 3px;
      background: rgba(3, 155, 229, 0.16);
      background: color-mix(in srgb, var(--info-color, #039be5) 18%, var(--acp-surface));
    }
    .glyph.sun {
      background: rgba(255, 193, 7, 0.4);
      background: color-mix(in srgb, var(--acp-sun) 45%, var(--acp-surface));
    }
    .glyph .fabric {
      width: 100%;
      height: var(--fabric, 0%);
      box-sizing: border-box;
      background: var(--secondary-text-color);
      opacity: 0.55;
      border-bottom: 2px solid var(--primary-text-color);
    }
    .glyph.big {
      width: 96px;
      height: 128px;
      border-width: 3px;
      border-radius: 5px;
    }

    /* Coming up */
    .upcoming-list {
      padding: 6px 16px;
      gap: 0;
    }
    .up-row {
      display: flex;
      gap: 14px;
      align-items: baseline;
      padding: 10px 0;
      border-bottom: 1px solid var(--acp-line);
    }
    .up-row:last-child {
      border-bottom: none;
    }
    .up-time {
      width: 72px;
      flex-shrink: 0;
      font-weight: 700;
      font-size: 0.9rem;
    }
    .up-main {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: 0.9rem;
    }

    /* Phone */
    .phone-floor {
      margin: 4px 4px 0;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--secondary-text-color);
    }
    .phone-room {
      padding: 0;
      gap: 0;
      overflow: hidden;
    }
    .room-toggle {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      min-height: 60px;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      text-align: left;
    }
    .room-toggle .room-title {
      flex-grow: 1;
    }
    .chevron {
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
      transition: transform 0.15s;
    }
    .chevron.open {
      transform: rotate(90deg);
    }
    .room-body {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0 14px 12px;
    }
    .room-body .seg {
      margin-bottom: 6px;
    }
    .room-body .row {
      border-top: 1px solid var(--acp-line);
      border-radius: 0;
      padding: 8px 0;
    }

    /* Detail sheet */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 9998;
      background: rgba(0, 0, 0, 0.32);
    }
    .sheet {
      position: fixed;
      z-index: 9999;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 28px;
      overflow-y: auto;
      background: var(--acp-surface);
      color: var(--primary-text-color);
      box-shadow: -12px 0 40px rgba(0, 0, 0, 0.25);
    }
    .sheet.side {
      top: 0;
      right: 0;
      bottom: 0;
      width: min(440px, 100vw);
    }
    .sheet.bottom {
      left: 0;
      right: 0;
      bottom: 0;
      max-height: 92vh;
      padding: 20px 16px 24px;
      border-radius: 16px 16px 0 0;
      box-shadow: 0 -12px 40px rgba(0, 0, 0, 0.25);
    }
    .sheet-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }
    .sheet-title {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .sheet-title h2 {
      font-size: 1.8rem;
      font-weight: 600;
    }
    .icon-btn {
      width: 44px;
      height: 44px;
      flex-shrink: 0;
      border: none;
      border-radius: 10px;
      background: var(--acp-track);
      color: var(--primary-text-color);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .sheet-pos {
      display: flex;
      gap: 24px;
      align-items: center;
    }
    .sheet-pos-text {
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-start;
    }
    .big-pos {
      font-size: 2.8rem;
      font-weight: 700;
      line-height: 1;
    }
    .cmds {
      display: flex;
      gap: 8px;
    }
    .cmds .btn {
      flex-grow: 1;
      min-height: 48px;
    }
    .mode-block {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .hint {
      margin: 0;
      font-size: 0.85rem;
    }
    .why {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 16px;
      border-radius: 12px;
      background: var(--acp-track);
    }
    .why p {
      margin: 0;
      line-height: 1.5;
    }
    .why details {
      font-size: 0.85rem;
      color: var(--secondary-text-color);
    }
    .why ol {
      margin: 6px 0 0;
      padding-left: 20px;
    }
    .sheet-foot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding-top: 16px;
      border-top: 1px solid var(--acp-line);
    }
    .setup {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .setup .muted,
    .sheet-foot > .muted {
      font-size: 0.85rem;
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
if (!window.customCards.some((c) => c.type === HOUSE_CARD_NAME)) {
  window.customCards.push({
    type: HOUSE_CARD_NAME,
    name: t('house.card_name'),
    description: t('house.card_description'),
    preview: false,
    documentationURL: 'https://github.com/mrvollger/adaptive-cover',
  });
}
