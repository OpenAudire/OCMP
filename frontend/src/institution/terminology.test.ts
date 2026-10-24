import { afterEach, describe, expect, it } from 'vitest';

import i18n from '../i18n';
import { applyTerminology } from './terminology';

describe('institution terminology', () => {
  afterEach(() => applyTerminology(i18n, {}));

  it('uses the default wording without overrides', () => {
    expect(i18n.t('terms.module', { count: 1 })).toBe('Module');
    expect(i18n.t('terms.learning_event', { count: 3 })).toBe('Sessions');
  });

  it('applies overrides for singular and plural', () => {
    applyTerminology(i18n, { module: { singular: 'Course', plural: 'Courses' } });

    expect(i18n.t('terms.module', { count: 1 })).toBe('Course');
    expect(i18n.t('terms.module', { count: 2 })).toBe('Courses');
    expect(i18n.t('terms.phase', { count: 1 })).toBe('Phase');
  });

  it('restores the default when an override is removed', () => {
    applyTerminology(i18n, { module: { singular: 'Course', plural: 'Courses' } });
    applyTerminology(i18n, {});

    expect(i18n.t('terms.module', { count: 1 })).toBe('Module');
  });
});
