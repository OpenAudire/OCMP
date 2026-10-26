import type { TFunction } from 'i18next';

import type { TagSource } from '../api/types';

/** Where an inherited tag came from, in words: "module HSC201 Cardiology". */
export function sourceLabel(t: TFunction, source: TagSource): string {
  switch (source.item_type) {
    case 'module':
      return `${t('terms.module', { count: 1 }).toLocaleLowerCase()} ${source.name}`;
    case 'learning_event':
      return `${t('terms.learning_event', { count: 1 }).toLocaleLowerCase()} ${source.name}`;
    default:
      return `“${source.name}”`;
  }
}
