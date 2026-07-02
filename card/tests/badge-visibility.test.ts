import { describe, it, expect } from 'vitest';
import {
  buildSolarActiveContext,
  isAutoControlActive,
  isSolarActive,
  resolveTileBadgeKind,
  selectVisibleBadges,
  winnerBadgeKind,
} from '../src/lib/badge-visibility';
import type { BadgeKind } from '../src/const';

describe('isSolarActive', () => {
  it('is true when the winning intent is calculated (solarMatched)', () => {
    expect(isSolarActive({ solarMatched: true })).toBe(true);
  });

  it('is false when solar did not match', () => {
    expect(isSolarActive({ solarMatched: false })).toBe(false);
  });
});

describe('buildSolarActiveContext', () => {
  it('marks solarMatched when the winner intent is calculated', () => {
    expect(buildSolarActiveContext([], 'calculated')).toEqual({ solarMatched: true });
  });

  it('normalizes the raw winner string (trim + lowercase)', () => {
    expect(buildSolarActiveContext(undefined, '  Calculated ')).toEqual({ solarMatched: true });
  });

  it('is not solarMatched for any other intent', () => {
    expect(buildSolarActiveContext([], 'default').solarMatched).toBe(false);
    expect(buildSolarActiveContext([], 'sunset').solarMatched).toBe(false);
    expect(buildSolarActiveContext(undefined, '').solarMatched).toBe(false);
  });
});

describe('selectVisibleBadges', () => {
  const active = { solarMatched: true };
  const inactive = { solarMatched: false };

  it('keeps solar when it is active and badges.solar is not false', () => {
    expect(selectVisibleBadges(['solar'], undefined, active)).toEqual(['solar']);
    expect(selectVisibleBadges(['solar'], { solar: true }, active)).toEqual(['solar']);
  });

  it('drops solar when it is not active even if badges.solar is on', () => {
    expect(selectVisibleBadges(['solar'], { solar: true }, inactive)).toEqual([]);
  });

  it('drops solar when badges.solar is false even though it is active', () => {
    expect(selectVisibleBadges(['solar'], { solar: false }, active)).toEqual([]);
  });

  it('gates each of the other configurable kinds by its own flag', () => {
    const kinds: BadgeKind[] = ['manual', 'climate', 'glare_zone', 'privacy', 'sunset'];
    expect(selectVisibleBadges(kinds, undefined, active)).toEqual(kinds);
    expect(selectVisibleBadges(kinds, { privacy: false, sunset: false }, active)).toEqual([
      'manual',
      'climate',
      'glare_zone',
    ]);
    expect(selectVisibleBadges(kinds, { manual: false, glare_zone: false }, active)).toEqual([
      'climate',
      'privacy',
      'sunset',
    ]);
  });

  it('keeps auto by default but lets badges.auto hide it; off is never filtered', () => {
    // Unrelated flags off → auto still shows.
    expect(selectVisibleBadges(['auto', 'off'], { solar: false, privacy: false }, inactive)).toEqual(
      ['auto', 'off'],
    );
    // badges.auto === false hides auto, but off survives.
    expect(selectVisibleBadges(['auto', 'off'], { auto: false }, inactive)).toEqual(['off']);
    expect(selectVisibleBadges(['auto'], { auto: true }, inactive)).toEqual(['auto']);
  });

  it('preserves input order of the surviving kinds', () => {
    const kinds: BadgeKind[] = ['solar', 'manual', 'privacy'];
    expect(selectVisibleBadges(kinds, undefined, active)).toEqual(['solar', 'manual', 'privacy']);
  });
});

describe('winnerBadgeKind', () => {
  const base = { integrationEnabled: true, manualActive: false };

  it('returns off when the integration (Toggle Control) is disabled', () => {
    expect(
      winnerBadgeKind({ winner: 'calculated', integrationEnabled: false, manualActive: false }),
    ).toBe('off');
    // Off outranks even an active manual override.
    expect(
      winnerBadgeKind({ winner: 'calculated', integrationEnabled: false, manualActive: true }),
    ).toBe('off');
  });

  it('returns manual when the manual-override binary is on', () => {
    expect(winnerBadgeKind({ ...base, winner: 'calculated', manualActive: true })).toBe('manual');
  });

  it('maps each intent to its badge kind', () => {
    expect(winnerBadgeKind({ ...base, winner: 'calculated' })).toBe('solar');
    expect(winnerBadgeKind({ ...base, winner: 'admit_no_glare' })).toBe('glare_zone');
    expect(winnerBadgeKind({ ...base, winner: 'privacy' })).toBe('privacy');
    expect(winnerBadgeKind({ ...base, winner: 'sunset' })).toBe('sunset');
    expect(winnerBadgeKind({ ...base, winner: 'climate_open_heat' })).toBe('climate');
    expect(winnerBadgeKind({ ...base, winner: 'climate_block_heat' })).toBe('climate');
    expect(winnerBadgeKind({ ...base, winner: 'climate_tilt_preset' })).toBe('climate');
    expect(winnerBadgeKind({ ...base, winner: 'climate_default' })).toBe('climate');
  });

  it('falls back to auto for default, unmapped, and unknown intents', () => {
    expect(winnerBadgeKind({ ...base, winner: 'default' })).toBe('auto');
    expect(winnerBadgeKind({ ...base, winner: 'shaded_by_overhang' })).toBe('auto');
    expect(winnerBadgeKind({ ...base, winner: 'mystery_intent' })).toBe('auto');
    expect(winnerBadgeKind({ ...base, winner: '' })).toBe('auto');
  });

  it('normalizes the raw winner string before mapping', () => {
    expect(winnerBadgeKind({ ...base, winner: '  CALCULATED ' })).toBe('solar');
  });
});

describe('resolveTileBadgeKind', () => {
  const base = { integrationEnabled: true, manualActive: false, badges: undefined };

  it('passes ordinary winners straight through', () => {
    expect(resolveTileBadgeKind({ ...base, winner: 'calculated' })).toBe('solar');
    expect(resolveTileBadgeKind({ ...base, winner: 'default' })).toBe('auto');
  });

  it('returns off_schedule when inTimeWindow is false and an automatic kind would show', () => {
    expect(resolveTileBadgeKind({ ...base, winner: 'default', inTimeWindow: false })).toBe(
      'off_schedule',
    );
    expect(resolveTileBadgeKind({ ...base, winner: 'calculated', inTimeWindow: false })).toBe(
      'off_schedule',
    );
  });

  it('does not show off_schedule when inTimeWindow is true or undefined', () => {
    expect(resolveTileBadgeKind({ ...base, winner: 'calculated', inTimeWindow: true })).toBe(
      'solar',
    );
    expect(resolveTileBadgeKind({ ...base, winner: 'calculated' })).toBe('solar');
  });

  it('off_schedule does not override the integration-disabled Off badge', () => {
    expect(
      resolveTileBadgeKind({
        winner: 'calculated',
        integrationEnabled: false,
        manualActive: false,
        badges: undefined,
        inTimeWindow: false,
      }),
    ).toBe('off');
  });

  it('off_schedule does not override an active manual override', () => {
    expect(
      resolveTileBadgeKind({
        winner: 'calculated',
        integrationEnabled: true,
        manualActive: true,
        badges: undefined,
        inTimeWindow: false,
      }),
    ).toBe('manual');
  });

  it('is hidden when badges.off_schedule is false (falls back to the intent kind)', () => {
    expect(
      resolveTileBadgeKind({
        ...base,
        winner: 'calculated',
        badges: { off_schedule: false },
        inTimeWindow: false,
      }),
    ).toBe('solar');
  });
});

describe('isAutoControlActive', () => {
  const base = {
    integrationEnabled: true,
    automaticControl: true,
    manualActive: false,
  };

  // Every intent keeps Auto visible: the indicator is independent of *which*
  // intent won — only the switches / manual override matter.
  const intents = [
    'privacy',
    'climate_open_heat',
    'climate_block_heat',
    'climate_tilt_preset',
    'climate_default',
    'admit_no_glare',
    'shaded_by_overhang',
    'sunset',
    'calculated',
    'default',
  ];
  for (const winner of intents) {
    it(`is true for the ${winner} intent under automatic control`, () => {
      expect(isAutoControlActive({ ...base, winner })).toBe(true);
    });
  }

  it('is false when a manual override is active', () => {
    expect(isAutoControlActive({ ...base, winner: 'calculated', manualActive: true })).toBe(false);
  });

  it('is false when the integration is disabled', () => {
    expect(
      isAutoControlActive({ ...base, winner: 'calculated', integrationEnabled: false }),
    ).toBe(false);
  });

  it('is false when automatic control is off', () => {
    expect(isAutoControlActive({ ...base, winner: 'calculated', automaticControl: false })).toBe(
      false,
    );
  });
});
