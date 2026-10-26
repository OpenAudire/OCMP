/**
 * Permission keys (mirroring backend app/core/permissions.py).
 *
 * The UI uses them only to decide what to show; the API checks every
 * permission itself.
 */
export const Permission = {
  SettingsManage: 'settings.manage',
  UsersManage: 'users.manage',
  RolesManage: 'roles.manage',
  RolesAssign: 'roles.assign',
  AuditView: 'audit.view',
  CurriculumView: 'curriculum.view',
  CurriculumViewPublished: 'curriculum.view_published',
  CurriculumEdit: 'curriculum.edit',
  CurriculumPublish: 'curriculum.publish',
  CurriculumUnpublish: 'curriculum.unpublish',
  ObjectivesEdit: 'objectives.edit',
  ObjectivesApprove: 'objectives.approve',
  FrameworksManage: 'frameworks.manage',
  TaglistsManage: 'taglists.manage',
  TaggingEdit: 'tagging.edit',
  MappingEdit: 'mapping.edit',
  MappingReview: 'mapping.review',
  MappingSecondReview: 'mapping.second_review',
  AiRun: 'ai.run',
  ReportsView: 'reports.view',
  EvidenceView: 'evidence.view',
} as const;

export type Permission = (typeof Permission)[keyof typeof Permission];

/** Holding the key permission also grants the listed ones (as on the server). */
const IMPLIED: Partial<Record<string, string[]>> = {
  [Permission.CurriculumView]: [Permission.CurriculumViewPublished],
};

/** Every permission held at any scope, including implied ones. */
export function collectPermissions(granted: Iterable<string>): ReadonlySet<string> {
  const result = new Set<string>();
  for (const permission of granted) {
    result.add(permission);
    for (const implied of IMPLIED[permission] ?? []) result.add(implied);
  }
  return result;
}

export function hasAny(held: ReadonlySet<string>, ...permissions: string[]): boolean {
  return permissions.some((p) => held.has(p));
}
