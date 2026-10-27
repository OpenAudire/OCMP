import type { TFunction } from 'i18next';

import type { WorkspaceObjective } from '../api/types';

/** Where an objective sits, in words: the programme, a module, or a session of a module. */
export function whereText(t: TFunction, objective: WorkspaceObjective): string {
  if (objective.level === 'programme') return t('mapping.where.programme');
  const module = `${objective.module_code ?? ''} ${objective.module_name ?? ''}`.trim();
  if (objective.level === 'module') return module;
  return `${module}: ${objective.learning_event_title ?? ''}`;
}

export interface Filters {
  /** '' = every module; 'programme' = programme outcomes only; otherwise a module id. */
  module: string;
  phase: string;
  unlinkedOnly: boolean;
}

export const NO_FILTERS: Filters = { module: '', phase: '', unlinkedOnly: false };

export function applyFilters(objectives: WorkspaceObjective[], filters: Filters) {
  return objectives.filter((o) => {
    if (filters.module === 'programme' && o.level !== 'programme') return false;
    if (filters.module && filters.module !== 'programme' && o.module_id !== filters.module) {
      return false;
    }
    if (filters.phase && o.phase_id !== filters.phase) return false;
    if (filters.unlinkedOnly && o.links.length > 0) return false;
    return true;
  });
}
