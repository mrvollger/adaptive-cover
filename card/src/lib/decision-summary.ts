import { HANDLER_LABELS, HANDLER_ORDER, type HandlerName } from '../const';
import type { DecisionStep, DecisionTraceAttributes } from '../types';
import { formatPercent } from './formatters';

/**
 * Normalize an intent string as emitted by the integration (`intent`
 * attribute) to the keys used in HANDLER_ORDER. The integration already emits
 * lower-snake values; this trims/lowers defensively for older builds.
 */
export function normalizeHandler(raw: string): string {
  return String(raw ?? '')
    .trim()
    .toLowerCase();
}

/** True when the intent is a known engine intent. */
export function isKnownIntent(intent: string): intent is HandlerName {
  return (HANDLER_ORDER as readonly string[]).includes(intent);
}

/**
 * Build a human-readable "Why this position?" summary.
 *
 * With the Adaptive Cover integration the decision trace is a list of prose
 * lines, so the sentence is simply the winning-intent label plus the final
 * trace line (which the integration already words as the immediate reason),
 * e.g. "Sun tracking — sun in view: tracking (position 63%)".
 *
 * `position` (when provided) is appended to the intent label.
 */
export function buildDecisionSentence(
  trace: readonly DecisionStep[],
  attrs: Pick<DecisionTraceAttributes, 'reason'>,
  winnerIntent: string,
  labels: Record<string, string> = HANDLER_LABELS,
  position: number | null = null,
): string {
  const key = normalizeHandler(winnerIntent);
  const label = labels[key] ?? winnerIntent;
  const pct = position !== null ? ` ${formatPercent(position)}` : '';
  const reason = attrs.reason ?? (trace.length > 0 ? trace[trace.length - 1].reason : '');
  if (!reason) return `${label}${pct}`.trimEnd();
  return `${label}${pct} — ${reason}`;
}
