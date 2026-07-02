import { describe, it, expect } from 'vitest';
import {
  buildDecisionSentence,
  isKnownIntent,
  normalizeHandler,
} from '../src/lib/decision-summary';
import { HANDLER_LABELS, HANDLER_ORDER } from '../src/const';
import type { DecisionStep } from '../src/types';

// Note: the Pro-era helpers resolveCustomPositionPct / resolveActiveMinModeFloor /
// isWinningSlotSafety (custom-position slots, min-mode floors, safety priority)
// were removed with the move to the Adaptive Cover integration — those features
// do not exist in its engine, so their tests are gone too.

const step = (line: string, matched: boolean): DecisionStep => ({
  handler: line,
  matched,
  reason: line,
  position: null,
});

describe('normalizeHandler', () => {
  it('trims and lowercases raw intent strings', () => {
    expect(normalizeHandler('  Calculated ')).toBe('calculated');
    expect(normalizeHandler('CLIMATE_BLOCK_HEAT')).toBe('climate_block_heat');
  });

  it('passes through already-normalized intents unchanged', () => {
    for (const intent of HANDLER_ORDER) {
      expect(normalizeHandler(intent)).toBe(intent);
    }
  });

  it('is defensive about null-ish input', () => {
    expect(normalizeHandler('')).toBe('');
    expect(normalizeHandler(undefined as unknown as string)).toBe('');
  });
});

describe('isKnownIntent', () => {
  it('accepts every engine intent in HANDLER_ORDER', () => {
    for (const intent of HANDLER_ORDER) {
      expect(isKnownIntent(intent)).toBe(true);
    }
  });

  it('rejects unknown and legacy Pro handler names', () => {
    expect(isKnownIntent('solar')).toBe(false);
    expect(isKnownIntent('motion')).toBe(false);
    expect(isKnownIntent('custom_position')).toBe(false);
    expect(isKnownIntent('')).toBe(false);
  });
});

describe('buildDecisionSentence', () => {
  it('renders "<IntentLabel> — <reason>" for a known intent', () => {
    const sentence = buildDecisionSentence(
      [step('sun in view: tracking', true)],
      { reason: 'sun in view: tracking' },
      'calculated',
    );
    expect(sentence).toBe('Sun tracking — sun in view: tracking');
  });

  it('appends the position percentage to the intent label when provided', () => {
    const sentence = buildDecisionSentence(
      [step('sun in view: tracking', true)],
      { reason: 'sun in view: tracking' },
      'calculated',
      HANDLER_LABELS,
      63,
    );
    expect(sentence).toBe('Sun tracking 63% — sun in view: tracking');
  });

  it('rounds a fractional position via formatPercent', () => {
    const sentence = buildDecisionSentence([], { reason: 'r' }, 'default', HANDLER_LABELS, 41.6);
    expect(sentence).toBe('Default 42% — r');
  });

  it('renders a 0% position (not dropped as falsy)', () => {
    const sentence = buildDecisionSentence([], { reason: 'closed' }, 'privacy', HANDLER_LABELS, 0);
    expect(sentence).toBe('Privacy 0% — closed');
  });

  it('omits the percent suffix when position is null', () => {
    const sentence = buildDecisionSentence(
      [step('sunset default', true)],
      { reason: 'sunset default' },
      'sunset',
      HANDLER_LABELS,
      null,
    );
    expect(sentence).toBe('Sunset — sunset default');
  });

  it('falls back to the last trace line when attrs.reason is nullish', () => {
    const sentence = buildDecisionSentence(
      [step('first line', false), step('winning line', true)],
      { reason: undefined as unknown as string },
      'calculated',
    );
    expect(sentence).toBe('Sun tracking — winning line');
  });

  it('does NOT fall back to the trace for an empty-string reason (label only)', () => {
    // readTraceAttrs always emits a string reason ('' when the trace is empty),
    // and buildDecisionSentence only falls back on nullish.
    const sentence = buildDecisionSentence(
      [step('first line', false), step('winning line', true)],
      { reason: '' },
      'calculated',
    );
    expect(sentence).toBe('Sun tracking');
  });

  it('returns just the label when there is no reason and no trace', () => {
    expect(buildDecisionSentence([], { reason: '' }, 'default')).toBe('Default');
    expect(buildDecisionSentence([], { reason: '' }, 'default', HANDLER_LABELS, 50)).toBe(
      'Default 50%',
    );
  });

  it('normalizes the winner intent before looking up its label', () => {
    expect(buildDecisionSentence([], { reason: 'r' }, ' CALCULATED ')).toBe('Sun tracking — r');
  });

  it('falls back to the raw winner string for an unknown intent', () => {
    expect(buildDecisionSentence([], { reason: 'r' }, 'mystery_intent')).toBe(
      'mystery_intent — r',
    );
  });

  it('respects a custom labels override', () => {
    const sentence = buildDecisionSentence(
      [],
      { reason: 'suivi' },
      'calculated',
      { calculated: 'Suivi solaire' },
      80,
    );
    expect(sentence).toBe('Suivi solaire 80% — suivi');
  });

  it('has an EN label for every intent in HANDLER_ORDER', () => {
    for (const intent of HANDLER_ORDER) {
      const sentence = buildDecisionSentence([], { reason: 'x' }, intent);
      expect(sentence).toBe(`${HANDLER_LABELS[intent]} — x`);
    }
  });
});
