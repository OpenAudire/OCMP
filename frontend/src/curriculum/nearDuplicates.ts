import type { TFunction } from 'i18next';

import type { NearDuplicate } from '../api/types';

/** Where the other objective is: "HSC201 outcome", "HSC201, Skills lab" or the programme. */
export function placeOf(t: TFunction, match: NearDuplicate): string {
  if (match.level === 'programme') {
    return t('curriculum.quality.page.programmeOutcome', {
      programme: t('terms.programme', { count: 1 }),
    });
  }
  const module = match.module_code ?? '';
  if (match.level === 'module') return t('curriculum.quality.page.moduleOutcome', { module });
  return t('curriculum.quality.page.sessionObjective', {
    module,
    session: match.event_title ?? '',
  });
}
