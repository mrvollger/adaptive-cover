import { describe, expect, it } from 'vitest';

import { en } from '../src/lib/i18n/en';
import { t } from '../src/lib/i18n';
import { HANDLER_LABELS, HANDLER_ORDER, BADGE_I18N_KEYS } from '../src/const';

// The card is English-only (the integration is too): there is one string
// table and no locale selection.

const leaves = (o: unknown, prefix = ''): Array<[string, unknown]> =>
  typeof o === 'object' && o !== null && !Array.isArray(o)
    ? Object.entries(o as Record<string, unknown>).flatMap(([k, v]) =>
        leaves(v, prefix ? `${prefix}.${k}` : k),
      )
    : [[prefix, o]];

/** Assert `key` resolves to a real (non-echoed, non-empty) string. */
const expectResolves = (key: string): void => {
  const value = t(key);
  expect(value, key).not.toBe(key);
  expect(value.length, key).toBeGreaterThan(0);
};

describe('t', () => {
  it('returns the key when the table has no entry', () => {
    expect(t('does.not.exist')).toBe('does.not.exist');
    expect(t('handler.unknown_handler')).toBe('handler.unknown_handler');
  });

  it('returns the key for a path that stops at a branch, not a string', () => {
    expect(t('handler')).toBe('handler');
  });

  it('returns the EN value', () => {
    expect(t('handler.calculated')).toBe('Sun tracking');
  });

  it('ignores the viewer language (English-only)', () => {
    // No hass/locale argument exists any more; the same key always resolves
    // to the single EN table.
    expect(t('badge.manual')).toBe(en.badge.manual);
  });

  it('interpolates a string parameter', () => {
    expect(t('overrides.ends_in', { time: '5m' })).toBe('ends in 5m');
  });

  it('leaves placeholders intact when no params are passed', () => {
    expect(t('overrides.ends_in')).toBe('ends in {time}');
  });

  it('leaves placeholders intact when params is an empty object', () => {
    expect(t('overrides.ends_in', {})).toBe('ends in {time}');
  });

  it('coerces numeric params to strings', () => {
    expect(t('overrides.active_count', { count: 3 })).toBe('3 active');
  });
});

describe('string table', () => {
  it('every EN value is a non-empty string', () => {
    for (const [key, value] of leaves(en)) {
      expect(typeof value, key).toBe('string');
      expect((value as string).length, key).toBeGreaterThan(0);
    }
  });

  it('every EN key resolves through t()', () => {
    for (const [key, value] of leaves(en)) {
      expect(t(key), key).toBe(value);
    }
  });
});

describe('intent (handler.*) keys', () => {
  it('has a handler.* entry for each of the 10 engine intents', () => {
    expect(Object.keys(en.handler).sort()).toEqual([...HANDLER_ORDER].sort());
    for (const intent of HANDLER_ORDER) {
      expectResolves(`handler.${intent}`);
    }
  });

  it('HANDLER_LABELS carries the same strings as the handler.* table', () => {
    for (const intent of HANDLER_ORDER) {
      expect(HANDLER_LABELS[intent], intent).toBe(t(`handler.${intent}`));
    }
  });

  it('drops the legacy Pro handler names (solar, motion, custom_position, …)', () => {
    const handlers = en.handler as Record<string, string>;
    for (const legacy of ['solar', 'motion', 'custom_position', 'force', 'weather', 'cloud']) {
      expect(handlers[legacy], `handler.${legacy}`).toBeUndefined();
    }
  });
});

describe('badge.* keys', () => {
  it('has a badge.* entry for each of the 9 badge kinds', () => {
    const kinds = Object.values(BADGE_I18N_KEYS).map((k) => k.split('.')[1]);
    expect(Object.keys(en.badge).sort()).toEqual([...kinds].sort());
    for (const key of Object.values(BADGE_I18N_KEYS)) {
      expectResolves(key);
    }
  });

  it('drops the legacy Pro badge kinds (force, weather, motion, custom_position, cloud)', () => {
    const badges = en.badge as Record<string, string>;
    for (const legacy of ['force', 'weather', 'motion', 'custom_position', 'cloud']) {
      expect(badges[legacy], `badge.${legacy}`).toBeUndefined();
    }
  });
});

describe('dialog keys for the Adaptive Cover sensor attributes', () => {
  it.each(['dialog.manual_detection', 'dialog.last_moves', 'dialog.move_blocked'])(
    '%s resolves',
    (key) => expectResolves(key),
  );

  it('dialog.move_blocked interpolates {gate}', () => {
    expect(t('dialog.move_blocked', { gate: 'position_delta' })).toContain('position_delta');
  });
});

describe('overrides panel keys', () => {
  it('kept the manual-override strings', () => {
    expect(en.overrides.manual.length).toBeGreaterThan(0);
    expect(en.overrides.reset_manual.length).toBeGreaterThan(0);
  });

  it('dropped the removed force/motion override strings', () => {
    const overrides = en.overrides as Record<string, string>;
    expect(overrides['force']).toBeUndefined();
    expect(overrides['motion']).toBeUndefined();
  });
});

describe('branding', () => {
  it('no EN string mentions "Adaptive Cover Pro"', () => {
    expect(JSON.stringify(en)).not.toContain('Adaptive Cover Pro');
  });
});

describe('climate inactive_reason + threshold i18n (issue #129)', () => {
  it.each([
    'outside_time_window',
    'thresholds_not_met',
    'other_mode_active',
    'readings_unavailable',
    'mode_off',
  ])('climate.reason.%s resolves', (slug) => expectResolves(`climate.reason.${slug}`));

  it.each(['threshold_low', 'threshold_high', 'threshold_summer_outside'])(
    'climate.%s resolves',
    (key) => expectResolves(`climate.${key}`),
  );
});

describe('version footer i18n', () => {
  it('root.footer_version is defined', () => {
    expect(en.root.footer_version).toBeDefined();
  });
});

describe('cover position i18n (issue #132)', () => {
  it.each([
    // compass.cover_position retired in #158 → cover_target / cover_held.
    'compass.cover_target',
    'compass.cover_held',
    'compass.cover_position_target',
    'compass.cover_position_target_awning',
    'compass.cover_position_actual',
  ])('%s resolves', (key) => expectResolves(key));

  it('the removed cover_closed / cover_extended keys are gone', () => {
    const compass = en.compass as Record<string, string>;
    expect(compass['cover_closed']).toBeUndefined();
    expect(compass['cover_extended']).toBeUndefined();
    expect(compass['cover_closed_tooltip']).toBeUndefined();
  });
});

describe('decision card editor i18n', () => {
  it.each([
    'editor.decision.title',
    'editor.decision.compact_label',
    'editor.decision.compact_desc',
    'editor.decision.hide_inactive_handlers_label',
    'editor.decision.hide_inactive_handlers_desc',
    'editor.decision.show_decision_summary_label',
    'editor.decision.show_decision_summary_desc',
  ])('%s resolves', (key) => expectResolves(key));
});

describe('outside-schedule i18n', () => {
  it.each(['decision.outside_schedule', 'decision.outside_schedule_tooltip', 'badge.off_schedule'])(
    '%s resolves',
    (key) => expectResolves(key),
  );
});

describe('elevation schedule i18n (issue #128)', () => {
  it.each([
    'elevation.schedule',
    'elevation.schedule_from',
    'elevation.schedule_until',
    'elevation.schedule_start_tooltip',
    'elevation.schedule_end_tooltip',
  ])('%s resolves', (key) => expectResolves(key));

  it('elevation.schedule interpolates {from} and {to}', () => {
    expect(t('elevation.schedule', { from: '07:30', to: '21:00' })).toBe('Schedule 07:30 – 21:00');
  });
});

describe('forecast.solar_only_note i18n', () => {
  it('resolves', () => expectResolves('forecast.solar_only_note'));
});
