import type { TFunction } from 'i18next';

import type { ExplorerSession } from '../api/types';

const WEEK_KEY = 'cic.explorerWeek';

/** The week last looked at in this browser (a convenience; there is no academic calendar). */
export function rememberedWeek(): number | null {
  try {
    const value = Number(window.localStorage.getItem(WEEK_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function rememberWeek(week: number): void {
  try {
    window.localStorage.setItem(WEEK_KEY, String(week));
  } catch {
    // Storage blocked: the week is simply not remembered.
  }
}

/** "60 min contact · 30 min self-study": the time of a session in words. */
export function minutesText(t: TFunction, session: Pick<ExplorerSession, 'contact_minutes' | 'self_study_minutes'>): string {
  const parts: string[] = [];
  if (session.contact_minutes > 0) {
    parts.push(t('explorer.contactMinutes', { count: session.contact_minutes }));
  }
  if (session.self_study_minutes > 0) {
    parts.push(t('explorer.selfStudyMinutes', { count: session.self_study_minutes }));
  }
  return parts.join(' · ');
}

/** Sessions grouped by week in the order given; sessions with no week come last. */
export function byWeek<T extends { week: number | null }>(sessions: T[]): [number | null, T[]][] {
  const groups = new Map<number | null, T[]>();
  for (const session of sessions) {
    const list = groups.get(session.week) ?? [];
    list.push(session);
    groups.set(session.week, list);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === null) return 1;
    if (b === null) return -1;
    return a - b;
  });
}
