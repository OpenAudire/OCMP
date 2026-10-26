import { api } from './client';
import type {
  AuthOptions,
  CopyForwardPreview,
  CurriculumVersion,
  Institution,
  LearningEventDetail,
  LearningEventInput,
  ModuleDetail,
  ModuleCopyInput,
  ModuleInput,
  Objective,
  PhaseCopyInput,
  PhaseInput,
  Programme,
  ProgrammeSummary,
  RoleAssignment,
  SavedLearningEvent,
  SavedModule,
  SavedPhase,
  TeachingFormat,
  User,
  VersionDiff,
  VersionStatus,
  VersionStructure,
} from './types';

export async function fetchMe(): Promise<User> {
  return (await api.get<User>('/auth/me')).data;
}

export async function fetchMyRoles(): Promise<RoleAssignment[]> {
  return (await api.get<RoleAssignment[]>('/auth/me/roles')).data;
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout');
}

export async function fetchAuthOptions(): Promise<AuthOptions> {
  return (await api.get<AuthOptions>('/auth/options')).data;
}

export async function login(email: string, password: string): Promise<void> {
  await api.post('/auth/login', { email, password });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await api.post('/auth/password-reset/request', { email });
}

export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  await api.post('/auth/password-reset/confirm', { token, new_password: newPassword });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export async function fetchSetupStatus(): Promise<{ needs_setup: boolean }> {
  return (await api.get<{ needs_setup: boolean }>('/setup/status')).data;
}

export interface SetupInput {
  token: string;
  institution_name: string;
  institution_short_code: string;
  country: string;
  health_profile: boolean;
  admin_display_name: string;
  admin_email: string;
  admin_password: string;
}

/** First-run setup: creates the institution and first admin, and signs the admin in. */
export async function runSetup(input: SetupInput): Promise<void> {
  await api.post('/setup', input);
}

/** Where the browser goes to start SSO sign-in (a full page navigation, not an API call). */
export function ssoLoginUrl(next: string): string {
  return `/api/v1/auth/oidc/login?next=${encodeURIComponent(next)}`;
}

export async function fetchInstitution(): Promise<Institution> {
  return (await api.get<Institution>('/institution')).data;
}

/** Programmes the user may see, each with its visible versions (newest first). */
export async function fetchProgrammes(): Promise<ProgrammeSummary[]> {
  return (await api.get<ProgrammeSummary[]>('/programmes')).data;
}

export async function fetchProgramme(id: string): Promise<Programme> {
  return (await api.get<Programme>(`/programmes/${id}`)).data;
}

/** The tree of a version, as far as the user may see it. */
export async function fetchVersionStructure(versionId: string): Promise<VersionStructure> {
  return (await api.get<VersionStructure>(`/curriculum-versions/${versionId}/structure`)).data;
}

export async function fetchProgrammeOutcomes(versionId: string): Promise<Objective[]> {
  return (await api.get<Objective[]>(`/curriculum-versions/${versionId}/outcomes`)).data;
}

export async function fetchModule(id: string): Promise<ModuleDetail> {
  return (await api.get<ModuleDetail>(`/modules/${id}`)).data;
}

export async function fetchLearningEvent(id: string): Promise<LearningEventDetail> {
  return (await api.get<LearningEventDetail>(`/learning-events/${id}`)).data;
}

export async function createPhase(versionId: string, input: PhaseInput): Promise<SavedPhase> {
  return (await api.post<SavedPhase>(`/curriculum-versions/${versionId}/phases`, input)).data;
}

export async function updatePhase(id: string, input: Partial<PhaseInput>): Promise<SavedPhase> {
  return (await api.patch<SavedPhase>(`/phases/${id}`, input)).data;
}

export async function deletePhase(id: string): Promise<void> {
  await api.delete(`/phases/${id}`);
}

export async function createModule(versionId: string, input: ModuleInput): Promise<SavedModule> {
  return (await api.post<SavedModule>(`/curriculum-versions/${versionId}/modules`, input)).data;
}

/** Only the fields sent are changed. */
export async function updateModule(id: string, input: Partial<ModuleInput>): Promise<SavedModule> {
  return (await api.patch<SavedModule>(`/modules/${id}`, input)).data;
}

/** Deletes the module with its sessions and their objectives. */
export async function deleteModule(id: string): Promise<void> {
  await api.delete(`/modules/${id}`);
}

export async function createLearningEvent(
  moduleId: string,
  input: LearningEventInput
): Promise<SavedLearningEvent> {
  return (await api.post<SavedLearningEvent>(`/modules/${moduleId}/learning-events`, input)).data;
}

/** Only the fields sent are changed. */
export async function updateLearningEvent(
  id: string,
  input: Partial<LearningEventInput>
): Promise<SavedLearningEvent> {
  return (await api.patch<SavedLearningEvent>(`/learning-events/${id}`, input)).data;
}

export async function deleteLearningEvent(id: string): Promise<void> {
  await api.delete(`/learning-events/${id}`);
}

/** Moves a phase to `position` (0 is first) among the version's phases. */
export async function movePhase(id: string, position: number): Promise<SavedPhase> {
  return (await api.post<SavedPhase>(`/phases/${id}/move`, { position })).data;
}

/** Moves a module to `position` within its phase (or among the modules across phases). */
export async function moveModule(id: string, position: number): Promise<SavedModule> {
  return (await api.post<SavedModule>(`/modules/${id}/move`, { position })).data;
}

/** Moves a session to `position` within its module. */
export async function moveLearningEvent(id: string, position: number): Promise<SavedLearningEvent> {
  return (await api.post<SavedLearningEvent>(`/learning-events/${id}/move`, { position })).data;
}

/** Copies a phase with its modules (one new code per module id), right after it. */
export async function copyPhase(id: string, input: PhaseCopyInput): Promise<SavedPhase> {
  return (await api.post<SavedPhase>(`/phases/${id}/copy`, input)).data;
}

/** Copies a module with its sessions and objectives; leave out phase_id to keep its phase. */
export async function copyModule(id: string, input: ModuleCopyInput): Promise<SavedModule> {
  return (await api.post<SavedModule>(`/modules/${id}/copy`, input)).data;
}

/** Copies a session with its objectives, right after it. */
export async function copyLearningEvent(id: string, title: string): Promise<SavedLearningEvent> {
  return (await api.post<SavedLearningEvent>(`/learning-events/${id}/copy`, { title })).data;
}

/** Values that can be chosen as a session's teaching format. */
export async function fetchTeachingFormats(): Promise<TeachingFormat[]> {
  return (await api.get<TeachingFormat[]>('/teaching-formats')).data;
}

/** Publish, return to draft, archive or unarchive a version. */
export async function changeVersionStatus(
  versionId: string,
  status: VersionStatus
): Promise<CurriculumVersion> {
  return (
    await api.post<CurriculumVersion>(`/curriculum-versions/${versionId}/status`, { status })
  ).data;
}

/** Deletes a draft version with everything in it. */
export async function deleteVersion(versionId: string): Promise<void> {
  await api.delete(`/curriculum-versions/${versionId}`);
}

export async function fetchCopyForwardPreview(versionId: string): Promise<CopyForwardPreview> {
  return (await api.get<CopyForwardPreview>(`/curriculum-versions/${versionId}/copy-forward`))
    .data;
}

/** Copies the version to a new draft for `academicYear`, with the chosen role assignments. */
export async function copyForward(
  versionId: string,
  academicYear: number,
  roleAssignmentIds: string[]
): Promise<CurriculumVersion> {
  return (
    await api.post<CurriculumVersion>(`/curriculum-versions/${versionId}/copy-forward`, {
      academic_year: academicYear,
      role_assignment_ids: roleAssignmentIds,
    })
  ).data;
}

/** What changed from the `base` version to this one. */
export async function fetchVersionDiff(versionId: string, base: string): Promise<VersionDiff> {
  return (
    await api.get<VersionDiff>(`/curriculum-versions/${versionId}/diff`, { params: { base } })
  ).data;
}

/** TanStack Query keys, in one place so invalidation stays consistent. */
export const queryKeys = {
  session: ['session'] as const,
  institution: ['institution'] as const,
  authOptions: ['auth-options'] as const,
  setupStatus: ['setup-status'] as const,
  programmes: ['programmes'] as const,
  programme: (id: string) => ['programmes', id] as const,
  versionStructure: (id: string) => ['curriculum-versions', id, 'structure'] as const,
  programmeOutcomes: (id: string) => ['curriculum-versions', id, 'outcomes'] as const,
  module: (id: string) => ['modules', id] as const,
  learningEvent: (id: string) => ['learning-events', id] as const,
  teachingFormats: ['teaching-formats'] as const,
  copyForward: (id: string) => ['curriculum-versions', id, 'copy-forward'] as const,
  versionDiff: (id: string, base: string) => ['curriculum-versions', id, 'diff', base] as const,
};
