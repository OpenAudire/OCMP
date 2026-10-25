import { api } from './client';
import type {
  AuthOptions,
  Institution,
  LearningEventDetail,
  ModuleDetail,
  Objective,
  Programme,
  ProgrammeSummary,
  RoleAssignment,
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
};
