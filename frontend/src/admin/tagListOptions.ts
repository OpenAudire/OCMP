import type { TagListKind } from '../api/types';

export const LIST_KINDS: TagListKind[] = [
  'teaching_method',
  'assessment_method',
  'theme',
  'thread',
  'keyword',
  'resource',
  'epa',
  'custom',
];

/** The item types a list can be limited to, with the curriculum noun for each. */
export const ITEM_TYPES = [
  { value: 'module', term: 'module' },
  { value: 'learning_event', term: 'learning_event' },
  { value: 'objective', term: 'objective' },
] as const;
