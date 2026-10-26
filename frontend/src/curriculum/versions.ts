import { useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';

import { queryKeys } from '../api/endpoints';
import type { CurriculumVersion, ProgrammeSummary, VersionStatus } from '../api/types';

/** A status change offered for a version, named as in the API's audit labels. */
export type StatusAction = 'publish' | 'unpublish' | 'archive' | 'unarchive';

/** The status changes each status allows (the API checks them too). */
export const STATUS_ACTIONS: Record<VersionStatus, { action: StatusAction; to: VersionStatus }[]> =
  {
    draft: [{ action: 'publish', to: 'published' }],
    published: [
      { action: 'unpublish', to: 'draft' },
      { action: 'archive', to: 'archived' },
    ],
    archived: [{ action: 'unarchive', to: 'published' }],
  };

/** "2027 draft": a version's name in a sentence. */
export function versionName(t: TFunction, version: CurriculumVersion): string {
  return t('curriculum.versions.name', {
    year: version.academic_year,
    status: t(`curriculum.versionStatus.${version.status}`).toLocaleLowerCase(),
  });
}

/** "2027 · Draft": a version's name in a list or heading. */
export function versionLabel(t: TFunction, version: CurriculumVersion): string {
  return t('curriculum.versionLabel', {
    year: version.academic_year,
    status: t(`curriculum.versionStatus.${version.status}`),
  });
}

/**
 * The version to compare with by default: the one it was copied from, otherwise the
 * newest older version, otherwise any other version of the programme.
 */
export function defaultBase(
  programme: ProgrammeSummary,
  version: CurriculumVersion
): CurriculumVersion | null {
  const others = programme.versions.filter((v) => v.id !== version.id);
  return (
    others.find((v) => v.id === version.based_on_id) ??
    others.find((v) => v.academic_year < version.academic_year) ??
    others[0] ??
    null
  );
}

/** Refetch what a version change affects: the version lists and this version. */
export function useRefreshVersions() {
  const client = useQueryClient();
  return (versionId: string) =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.programmes }),
      client.invalidateQueries({ queryKey: ['curriculum-versions', versionId] }),
      client.invalidateQueries({ queryKey: ['modules'] }),
      client.invalidateQueries({ queryKey: ['learning-events'] }),
    ]);
}

/** A notice carried to the next page in the router's location state. */
export interface NoticeState {
  notice?: string;
}
