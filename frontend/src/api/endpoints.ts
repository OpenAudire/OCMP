import { api } from './client';
import type {
  AuthOptions,
  Institution,
  LearningEventDetail,
  LearningEventInput,
  ModuleDetail,
  ModuleInput,
  Objective,
  PhaseInput,
  Programme,
  ProgrammeSummary,
  RoleAssignment,
  SavedLearningEvent,
  SavedModule,
  SavedPhase,
  TeachingFormat,
  User,
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

/** Values that can be chosen as a session's teaching format. */
export async function fetchTeachingFormats(): Promise<TeachingFormat[]> {
  return (await api.get<TeachingFormat[]>('/teaching-formats')).data;
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
};
