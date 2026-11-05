import type { TFunction } from 'i18next';

import type { ProgrammeSummary, RoleAssignment, ScopeType } from '../api/types';

/** "5 November 2026, 11:42": a moment, in the reader's time. */
export function formatWhen(iso: string, language: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const locale = language.startsWith('en') ? 'en-GB' : language;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeStyle: 'short' }).format(date);
}

/** A day, without a time ("5 November 2026"), as the server stores it. */
export function formatDay(iso: string, language: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const locale = language.startsWith('en') ? 'en-GB' : language;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(date);
}

/** Where a role is held, in words: the institution, a faculty or programme by name, or a module
 * or session (named on the curriculum screens, not here). */
export function scopeLabel(
  t: TFunction,
  assignment: Pick<RoleAssignment, 'scope_type' | 'scope_id'>,
  programmes: readonly ProgrammeSummary[]
): string {
  const { scope_type: type, scope_id: id } = assignment;
  if (type === 'instance') return t('admin.scope.instance');
  if (type === 'faculty') {
    const faculty = programmes.find((p) => p.faculty_id === id);
    return t('admin.scope.faculty', { name: faculty?.faculty_name ?? id?.slice(0, 8) ?? '' });
  }
  if (type === 'programme') {
    const programme = programmes.find((p) => p.id === id);
    return t('admin.scope.programme', { name: programme?.name ?? id?.slice(0, 8) ?? '' });
  }
  return t(`admin.scope.${type}`, { id: id?.slice(0, 8) ?? '' });
}

/** The places the admin screen can choose for a new assignment (modules and sessions are
 * assigned on the curriculum screens, where they can be named). */
export const ASSIGNABLE_SCOPES: ScopeType[] = ['instance', 'faculty', 'programme'];
