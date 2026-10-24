import { describe, expect, it } from 'vitest';

import { collectPermissions, Permission } from '../session/permissions';
import { visibleNavItems } from './navigation';

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

  it('shows lecturers the staff curriculum views without the explorer', () => {
    // curriculum.view implies view_published, as on the server.
    expect(navFor(Permission.CurriculumView, Permission.ObjectivesEdit)).toEqual([
      'dashboard',
      'curriculum',
      'frameworks',
      'search',
    ]);
  });

  it('shows mappers the mapping workspace', () => {
    expect(navFor(Permission.CurriculumView, Permission.MappingReview)).toContain('mapping');
  });

  it('shows administrators everything except the student explorer', () => {
    expect(navFor(...Object.values(Permission))).toEqual([
      'dashboard',
      'curriculum',
      'mapping',
      'frameworks',
      'reports',
      'search',
      'admin',
    ]);
  });

  it('shows nothing to accounts without roles', () => {
    expect(navFor()).toEqual([]);
  });
});
