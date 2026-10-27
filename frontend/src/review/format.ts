import type { ReviewLink } from '../api/types';

/** Where the objective sits, in words: the module, its session, or the programme. */
export function objectiveWhere(
  t: (key: string, options?: Record<string, unknown>) => string,
  link: ReviewLink
): string {
  const { objective } = link;
  if (objective.level === 'programme') return t('mapping.where.programme');
  const module = [objective.module_code, objective.module_name].filter(Boolean).join(' ');
  return objective.learning_event_title ? `${module} · ${objective.learning_event_title}` : module;
}

/** The bar colour: from 80% good, from 65% worth a look, below that check carefully. */
export function confidenceLevel(confidence: number): 'high' | 'middle' | 'low' {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.65) return 'middle';
  return 'low';
}
