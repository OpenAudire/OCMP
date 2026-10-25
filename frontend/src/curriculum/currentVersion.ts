import { useQuery } from '@tanstack/react-query';

import { fetchProgrammes, queryKeys } from '../api/endpoints';
import type { CurriculumVersion, ProgrammeSummary } from '../api/types';

const STORAGE_KEY = 'cic.curriculumVersion';

/** The version last opened in this browser (a convenience; may be gone or hidden now). */
export function rememberedVersion(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function rememberVersion(versionId: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, versionId);
  } catch {
    // Storage blocked: the choice is simply not remembered.
  }
}

/** The programme and version with this id, if the user may see it. */
export function findVersion(
  programmes: readonly ProgrammeSummary[],
  versionId: string | null | undefined
): { programme: ProgrammeSummary; version: CurriculumVersion } | null {
  for (const programme of programmes) {
    const version = programme.versions.find((v) => v.id === versionId);
    if (version) return { programme, version };
  }
  return null;
}

/**
 * The version to open when none is named: the remembered one while it is still
 * visible, otherwise the newest version of the first programme.
 */
export function defaultVersionId(
  programmes: readonly ProgrammeSummary[],
  remembered: string | null
): string | null {
  if (findVersion(programmes, remembered)) return remembered;
  return programmes[0]?.versions[0]?.id ?? null;
}

export function useProgrammes() {
  return useQuery({ queryKey: queryKeys.programmes, queryFn: fetchProgrammes });
}
