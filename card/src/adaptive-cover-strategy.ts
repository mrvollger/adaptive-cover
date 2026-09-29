import type { HomeAssistant } from 'custom-card-helpers';

import { HOUSE_CARD_NAME, STRATEGY_ELEMENT_NAME, STRATEGY_TYPE } from './const';
import { discoverHouse } from './lib/house-model';
import { t } from './lib/i18n';
import type { AdaptiveCoverHouseCardConfig } from './types';

/*
 * Dashboard strategy `custom:adaptive-cover` (refactor plan P6, "UI"): a
 * dashboard with one panel view holding the house card.
 *
 *   strategy:
 *     type: custom:adaptive-cover
 *     title: Shades        # optional
 *     floors: [upstairs]   # optional, passed to the card
 *     areas: [office]      # optional, passed to the card
 *
 * Windows come from `hass.entities` (platform adaptive_cover, hidden and
 * disabled entities left out). A house without windows gets a short hint
 * instead of an empty card.
 */

export interface AdaptiveCoverStrategyConfig {
  type: string;
  title?: string;
  floors?: string[];
  areas?: string[];
}

export interface GeneratedDashboard {
  title: string;
  views: Array<Record<string, unknown>>;
}

/** The dashboard for `config` (pure; exported for tests). */
export function generateDashboard(
  config: AdaptiveCoverStrategyConfig | undefined,
  hass: HomeAssistant,
): GeneratedDashboard {
  const title = config?.title || t('house.title');
  const card: AdaptiveCoverHouseCardConfig = { type: `custom:${HOUSE_CARD_NAME}` };
  if (config?.title) card.title = config.title;
  if (config?.floors?.length) card.floors = [...config.floors];
  if (config?.areas?.length) card.areas = [...config.areas];

  const model = discoverHouse(hass, null, { floors: card.floors, areas: card.areas });
  // No window found: show a hint, unless discovery could not classify rows
  // without the full registry (the card itself fetches it).
  const empty = model.windows.length === 0 && !model.needsRegistry;
  const cards = empty ? [{ type: 'markdown', content: t('house.empty') }] : [card];

  return {
    title,
    views: [
      {
        title,
        path: 'shades',
        icon: 'mdi:blinds-horizontal',
        type: 'panel',
        cards,
      },
    ],
  };
}

class AdaptiveCoverDashboardStrategy extends HTMLElement {
  static async generate(
    config: AdaptiveCoverStrategyConfig,
    hass: HomeAssistant,
  ): Promise<GeneratedDashboard> {
    return generateDashboard(config, hass);
  }
}

if (!customElements.get(STRATEGY_ELEMENT_NAME)) {
  customElements.define(STRATEGY_ELEMENT_NAME, AdaptiveCoverDashboardStrategy);
}

interface CustomStrategyEntry {
  type: string;
  strategyType: 'dashboard' | 'view' | 'section';
  name?: string;
  description?: string;
  documentationURL?: string;
}

declare global {
  interface Window {
    customStrategies?: CustomStrategyEntry[];
  }
}

// Lists the strategy in HA's "Add dashboard" dialog (HA 2026.5+). Older HA
// ignores the array; `strategy: { type: custom:adaptive-cover }` still works.
window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((s) => s.type === STRATEGY_TYPE)) {
  window.customStrategies.push({
    type: STRATEGY_TYPE,
    strategyType: 'dashboard',
    name: t('house.strategy_name'),
    description: t('house.strategy_description'),
    documentationURL: 'https://github.com/mrvollger/adaptive-cover',
  });
}
