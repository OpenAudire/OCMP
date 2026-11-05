import { describe, expect, it } from 'vitest';

import { collectPermissions, Permission } from '../session/permissions';
import { activeNavKey, NAV_ITEMS, visibleNavItems } from './navigation';

function navFor(...permissions: string[]): string[] {
  return visibleNavItems(collectPermissions(permissions)).map((item) => item.key);
}

describe('navigation by permission', () => {
  it('shows students the explorer and search only', () => {
    expect(navFor(Permission.CurriculumViewPublished)).toEqual(['explorer', 'search']);
  });

  it('shows external reviewers the explorer, reports and search', () => {
    expect(
      navFor(Permission.CurriculumViewPublished, Permission.ReportsView, Permission.EvidenceView)
    ).toEqual(['reports', 'explorer', 'search']);
  });

  it('shows lecturers the staff curriculum views and the explorer', () => {
    // curriculum.view implies view_published, as on the server.
    expect(navFor(Permission.CurriculumView, Permission.ObjectivesEdit)).toEqual([
      'curriculum',
      'frameworks',
      'explorer',
      'search',
    ]);
  });

  it('shows reviewers the mapping workspace and the review queue', () => {
    const items = navFor(Permission.CurriculumView, Permission.MappingReview);
    expect(items).toContain('mapping');
    expect(items).toContain('review');
  });

  it('shows mappers who do not review the workspace without the queue', () => {
    const items = navFor(Permission.CurriculumView, Permission.MappingEdit);
    expect(items).toContain('mapping');
    expect(items).not.toContain('review');
  });

  it('shows import and export to people who edit what can be imported', () => {
    expect(navFor(Permission.CurriculumView, Permission.CurriculumEdit)).toContain('import');
    expect(navFor(Permission.CurriculumView)).not.toContain('import');
  });

  it('shows administrators everything, in sidebar order', () => {
    expect(navFor(...Object.values(Permission))).toEqual([
      'dashboard',
      'curriculum',
      'mapping',
      'review',
      'frameworks',
      'reports',
      'import',
      'explorer',
      'search',
      'admin',
    ]);
  });

  it('shows nothing to accounts without roles', () => {
    expect(navFor()).toEqual([]);
  });
});

describe('active navigation item', () => {
  it('matches a section and the pages inside it', () => {
    expect(activeNavKey(NAV_ITEMS, '/curriculum')).toBe('curriculum');
    expect(activeNavKey(NAV_ITEMS, '/curriculum/modules/7')).toBe('curriculum');
  });

  it('prefers the most specific item, so the review queue is not also "mapping"', () => {
    expect(activeNavKey(NAV_ITEMS, '/mapping')).toBe('mapping');
    expect(activeNavKey(NAV_ITEMS, '/mapping/review')).toBe('review');
    expect(activeNavKey(NAV_ITEMS, '/mapping/review/12')).toBe('review');
  });

  it('matches whole path segments only', () => {
    expect(activeNavKey(NAV_ITEMS, '/mapping-help')).toBeUndefined();
    expect(activeNavKey(NAV_ITEMS, '/account')).toBeUndefined();
  });
});
