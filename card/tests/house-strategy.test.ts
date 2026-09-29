/// <reference types="node" />
// The dashboard strategy `custom:adaptive-cover` (element
// ll-strategy-dashboard-adaptive-cover): one panel view with the house card.
import { describe, expect, it } from 'vitest';

import { generateDashboard } from '../src/adaptive-cover-strategy';
import { houseFixture, type HouseTestHass } from './fixtures/house-hass';

type StrategyClass = {
  generate(config: Record<string, unknown>, hass: HouseTestHass): Promise<unknown>;
};

describe('dashboard strategy', () => {
  it('registers the element and lists itself in customStrategies', () => {
    expect(customElements.get('ll-strategy-dashboard-adaptive-cover')).toBeTruthy();
    expect(window.customStrategies).toContainEqual(
      expect.objectContaining({ type: 'adaptive-cover', strategyType: 'dashboard' }),
    );
  });

  it('generate(): the real house (3 floors, 15 windows) → one view with the house card', async () => {
    const fx = houseFixture();
    const Strategy = customElements.get(
      'll-strategy-dashboard-adaptive-cover',
    ) as unknown as StrategyClass;
    const dashboard = await Strategy.generate({ type: 'custom:adaptive-cover' }, fx.hass);
    expect(dashboard).toMatchSnapshot();
    expect(dashboard).toEqual(generateDashboard({ type: 'custom:adaptive-cover' }, fx.hass));
  });

  it('passes title, floors and areas to the card', () => {
    const fx = houseFixture();
    const dash = generateDashboard(
      { type: 'custom:adaptive-cover', title: 'Blinds', floors: ['upstairs'], areas: ['den'] },
      fx.hass,
    );
    expect(dash.title).toBe('Blinds');
    expect(dash.views[0].cards).toEqual([
      {
        type: 'custom:adaptive-cover-house-card',
        title: 'Blinds',
        floors: ['upstairs'],
        areas: ['den'],
      },
    ]);
  });

  it('a house without windows gets a hint instead of the card', () => {
    const fx = houseFixture();
    const dash = generateDashboard({ type: 'custom:adaptive-cover' }, {
      ...fx.hass,
      entities: {},
    } as HouseTestHass);
    expect(dash.views[0].cards).toEqual([
      { type: 'markdown', content: expect.stringMatching(/No Adaptive Cover windows found/) },
    ]);
  });

  it('keeps the card when only the full registry can find the windows', () => {
    const legacy = houseFixture({ surface: 'legacy' });
    const dash = generateDashboard({ type: 'custom:adaptive-cover' }, legacy.hass);
    expect(dash.views[0].cards).toEqual([{ type: 'custom:adaptive-cover-house-card' }]);
  });
});
