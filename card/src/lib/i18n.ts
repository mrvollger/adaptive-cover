// UI strings. The card is English-only (as is the integration), so there is
// no locale selection: every key resolves against the single `en` table.
import { en } from './i18n/en';

function lookup(key: string): string | undefined {
  let node: unknown = en;
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

function interpolate(template: string, params: Record<string, unknown> | undefined): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    if (Object.prototype.hasOwnProperty.call(params, name)) {
      return String(params[name]);
    }
    return match;
  });
}

/**
 * Resolve a dotted key (e.g. `handler.calculated`) to its UI string and fill
 * `{name}` placeholders from `params`. Unknown keys echo the key back so a
 * missing string is visible rather than blank.
 */
export function t(key: string, params?: Record<string, unknown>): string {
  const value = lookup(key);
  return value === undefined ? key : interpolate(value, params);
}
