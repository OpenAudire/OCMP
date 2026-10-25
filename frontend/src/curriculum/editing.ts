import { useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';

import { isApiError } from '../api/client';
import { queryKeys } from '../api/endpoints';
import { LONGITUDINAL_ID, ROOT_ID } from './treeModel';

/** What the builder does after a change: say what happened, select and reveal an item. */
export interface EditResult {
  message: string;
  /** Tree node id to select (a new item, or the parent of a deleted one). */
  select?: string;
  /** Tree node ids to open so the selected item shows. */
  reveal?: string[];
}

/** Tree node id of the group that holds a module: its phase, or "Across phases". */
export function moduleParentId(phaseId: string | null): string {
  return phaseId ? `phase:${phaseId}` : LONGITUDINAL_ID;
}

/** The ancestors of a module's node, root first. */
export function moduleAncestors(phaseId: string | null): string[] {
  return [ROOT_ID, moduleParentId(phaseId)];
}

/** Refetch everything a structure change can affect in this version. */
export function useRefreshCurriculum(versionId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.versionStructure(versionId) }),
      client.invalidateQueries({ queryKey: ['modules'] }),
      client.invalidateQueries({ queryKey: ['learning-events'] }),
    ]);
}

/** Lower-case curriculum nouns for sentences, from the institution's terminology. */
export function nounsFor(t: TFunction) {
  const noun = (term: string, count = 1) => t(`terms.${term}`, { count }).toLocaleLowerCase();
  return {
    phase: noun('phase'),
    phases: noun('phase', 2),
    module: noun('module'),
    modules: noun('module', 2),
    session: noun('learning_event'),
    sessions: noun('learning_event', 2),
    objectives: noun('objective', 2),
    noun,
  };
}

/** A plain-language message for a failed save or delete. */
export function editErrorMessage(t: TFunction, error: unknown, conflict?: string): string {
  if (isApiError(error, 409)) return conflict ?? t('curriculum.edit.errors.conflict');
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  if (isApiError(error, 404)) return t('curriculum.edit.errors.gone');
  if (isApiError(error, 422)) return t('curriculum.edit.errors.invalid');
  return t('curriculum.edit.errors.generic');
}

/** Empty text fields become null for optional values. */
export function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/** Mantine number inputs give '' when empty. */
export function optionalNumber(value: number | string): number | null {
  return value === '' || value === null ? null : Number(value);
}
