import type { i18n as I18n } from 'i18next';

import type { Term, TermOverride } from '../api/types';

type Terms = Record<string, string>;

const defaults = new Map<string, Terms>();

function defaultTerms(i18n: I18n, language: string): Terms {
  if (!defaults.has(language)) {
    const bundle = i18n.getResourceBundle(language, 'translation') as { terms?: Terms } | undefined;
    defaults.set(language, { ...(bundle?.terms ?? {}) });
  }
  return defaults.get(language)!;
}

/**
 * Layer an institution's terminology over the translations in every loaded
 * language. Defaults are restored first, so removing an override takes effect.
 */
export function applyTerminology(
  i18n: I18n,
  overrides: Partial<Record<Term, TermOverride>>
): void {
  for (const language of Object.keys(i18n.store.data)) {
    const terms: Terms = { ...defaultTerms(i18n, language) };
    for (const [term, words] of Object.entries(overrides)) {
      if (!words) continue;
      terms[`${term}_one`] = words.singular;
      terms[`${term}_other`] = words.plural;
    }
    i18n.addResourceBundle(language, 'translation', { terms }, true, true);
  }
}
