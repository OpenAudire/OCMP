import { api } from './client';
import type {
  AiConnectionTest,
  AiSettings,
  AiUpdate,
  AssessableObjective,
  Assessment,
  AssessmentInput,
  AssessmentItemInput,
  AssessmentMethod,
  AuthOptions,
  BulkAcceptRequest,
  BulkAcceptResult,
  CopyForwardPreview,
  CurriculumVersion,
  FrameworkItemDetail,
  FrameworkItemPage,
  FrameworkLibrary,
  FrameworkSearchPage,
  InheritancePreview,
  Institution,
  MappingWorkspace,
  LearningEventDetail,
  LinkInput,
  LearningEventInput,
  ModuleDetail,
  ModuleCopyInput,
  ModuleInput,
  NearDuplicates,
  Objective,
  ObjectiveInput,
  ObjectiveOption,
  PhaseCopyInput,
  PhaseInput,
  Programme,
  ProgrammeSummary,
  QualityCheck,
  QualityCheckInput,
  ReviewCounts,
  ReviewQueue,
  ReviewQueueParams,
  ReviewRequest,
  ReviewResult,
  RoleAssignment,
  SavedLearningEvent,
  SavedModule,
  SavedObjective,
  SavedPhase,
  TagApplied,
  TaggableKind,
  PackImportResult,
  PackPreview,
  PackTemplate,
  TagList,
  TagListInput,
  TagListPlaces,
  TagValue,
  TagValueInput,
  TaxonomyScale,
  TeachingFormat,
  User,
  VersionChecks,
  VersionCreditCheck,
  VersionDiff,
  VersionStatus,
  VersionStructure,
  WhereMapped,
  WorkspaceLink,
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

/** Values that can be chosen as an assessment's method. */
export async function fetchAssessmentMethods(): Promise<AssessmentMethod[]> {
  return (await api.get<AssessmentMethod[]>('/assessment-methods')).data;
}

/** The objectives of a module and its sessions that its assessment items may assess. */
export async function fetchAssessableObjectives(moduleId: string): Promise<AssessableObjective[]> {
  return (await api.get<AssessableObjective[]>(`/modules/${moduleId}/assessable-objectives`)).data;
}

export async function createAssessment(
  moduleId: string,
  input: AssessmentInput
): Promise<Assessment> {
  return (await api.post<Assessment>(`/modules/${moduleId}/assessments`, input)).data;
}

export async function updateAssessment(
  id: string,
  input: Partial<AssessmentInput>
): Promise<Assessment> {
  return (await api.patch<Assessment>(`/assessments/${id}`, input)).data;
}

export async function deleteAssessment(id: string): Promise<void> {
  await api.delete(`/assessments/${id}`);
}

/** Adds an item; the whole assessment comes back. */
export async function createAssessmentItem(
  assessmentId: string,
  input: AssessmentItemInput
): Promise<Assessment> {
  return (await api.post<Assessment>(`/assessments/${assessmentId}/items`, input)).data;
}

export async function updateAssessmentItem(
  id: string,
  input: Partial<AssessmentItemInput>
): Promise<Assessment> {
  return (await api.patch<Assessment>(`/assessment-items/${id}`, input)).data;
}

export async function deleteAssessmentItem(id: string): Promise<void> {
  await api.delete(`/assessment-items/${id}`);
}

/** Planned hours against credits for every module, per year and per NQF level. */
export async function fetchCreditCheck(versionId: string): Promise<VersionCreditCheck> {
  return (await api.get<VersionCreditCheck>(`/curriculum-versions/${versionId}/credit-check`)).data;
}

/** Taxonomy scales (Bloom, Miller...) with their levels. */
export async function fetchTaxonomyScales(): Promise<TaxonomyScale[]> {
  return (await api.get<TaxonomyScale[]>('/taxonomy-scales')).data;
}

/** Programme outcomes a module outcome can link to (those the user sees). */
export async function fetchModuleLinkOptions(moduleId: string): Promise<ObjectiveOption[]> {
  return (await api.get<ObjectiveOption[]>(`/modules/${moduleId}/outcome-link-options`)).data;
}

/** Outcomes a session objective can link to (those the user sees). */
export async function fetchEventLinkOptions(eventId: string): Promise<ObjectiveOption[]> {
  return (await api.get<ObjectiveOption[]>(`/learning-events/${eventId}/objective-link-options`))
    .data;
}

export async function createProgrammeOutcome(
  versionId: string,
  input: ObjectiveInput
): Promise<SavedObjective> {
  return (await api.post<SavedObjective>(`/curriculum-versions/${versionId}/outcomes`, input))
    .data;
}

export async function createModuleOutcome(
  moduleId: string,
  input: ObjectiveInput
): Promise<SavedObjective> {
  return (await api.post<SavedObjective>(`/modules/${moduleId}/outcomes`, input)).data;
}

export async function createEventObjective(
  eventId: string,
  input: ObjectiveInput
): Promise<SavedObjective> {
  return (await api.post<SavedObjective>(`/learning-events/${eventId}/objectives`, input)).data;
}

/** Only the fields sent are changed. */
export async function updateObjective(
  id: string,
  input: Partial<ObjectiveInput>
): Promise<SavedObjective> {
  return (await api.patch<SavedObjective>(`/objectives/${id}`, input)).data;
}

export async function deleteObjective(id: string): Promise<void> {
  await api.delete(`/objectives/${id}`);
}

/** Publish, return to draft, archive or unarchive a version. */
export async function changeVersionStatus(
  versionId: string,
  status: VersionStatus,
  reason?: string
): Promise<CurriculumVersion> {
  return (
    await api.post<CurriculumVersion>(`/curriculum-versions/${versionId}/status`, {
      status,
      ...(reason === undefined ? {} : { reason }),
    })
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

/** Check wording as typed (live); `path` is the owner's checking address. */
export async function checkObjectiveText(
  path: string,
  input: QualityCheckInput
): Promise<QualityCheck> {
  return (await api.post<QualityCheck>(path, input)).data;
}

/** Check every objective of a version that the user sees. */
export async function fetchVersionChecks(versionId: string): Promise<VersionChecks> {
  return (await api.get<VersionChecks>(`/curriculum-versions/${versionId}/objective-checks`)).data;
}

/** Near-duplicate objectives of a version, for the objective cards (editors only). */
export async function fetchNearDuplicates(versionId: string): Promise<NearDuplicates> {
  return (await api.get<NearDuplicates>(`/curriculum-versions/${versionId}/near-duplicates`)).data;
}

/** Tag lists with their values (everyone: active ones; managers: all, with usage). */
export async function fetchTagLists(): Promise<TagList[]> {
  return (await api.get<TagList[]>('/tag-lists')).data;
}

/** Where the user may create tag lists: the institution and/or some faculties. */
export async function fetchTagListPlaces(): Promise<TagListPlaces> {
  return (await api.get<TagListPlaces>('/tag-lists/places')).data;
}

export async function createTagList(input: TagListInput): Promise<TagList> {
  return (await api.post<TagList>('/tag-lists', input)).data;
}

/** Only the fields sent are changed; the key and kind cannot change. */
export async function updateTagList(
  id: string,
  input: Partial<Pick<TagListInput, 'description' | 'entity_types'>> & {
    name?: string;
    is_active?: boolean;
  }
): Promise<TagList> {
  return (await api.patch<TagList>(`/tag-lists/${id}`, input)).data;
}

/** Only a list nothing uses can be deleted (409 otherwise). */
export async function deleteTagList(id: string): Promise<void> {
  await api.delete(`/tag-lists/${id}`);
}

export async function createTagValue(listId: string, input: TagValueInput): Promise<TagValue> {
  return (await api.post<TagValue>(`/tag-lists/${listId}/values`, input)).data;
}

/** Only the fields sent are changed; `code: null` clears the code. */
export async function updateTagValue(
  id: string,
  input: Partial<TagValueInput> & { is_active?: boolean }
): Promise<TagValue> {
  return (await api.patch<TagValue>(`/tag-values/${id}`, input)).data;
}

/** Only a tag nothing uses can be deleted (409 otherwise). */
export async function deleteTagValue(id: string): Promise<void> {
  await api.delete(`/tag-values/${id}`);
}

/** Every item that tagging this one would reach, before saving. */
export async function fetchTagPreview(
  kind: TaggableKind,
  itemId: string,
  tagValueId: string
): Promise<InheritancePreview> {
  return (
    await api.get<InheritancePreview>(`/curriculum-items/${kind}/${itemId}/tag-preview`, {
      params: { tag_value_id: tagValueId },
    })
  ).data;
}

/** Items below a directly tagged item that the tag has not reached yet; `new` ones would get it. */
export async function fetchPassOnPreview(taggingId: string): Promise<InheritancePreview> {
  return (await api.get<InheritancePreview>(`/taggings/${taggingId}/pass-on-preview`)).data;
}

/** Gives the tag to the items the preview lists as new. */
export async function passTagOn(taggingId: string): Promise<TagApplied> {
  return (await api.post<TagApplied>(`/taggings/${taggingId}/pass-on`)).data;
}

/** Tags the item; with `inherit` the tag also goes to the items the preview lists as new. */
export async function addTag(
  kind: TaggableKind,
  itemId: string,
  tagValueId: string,
  inherit: boolean
): Promise<TagApplied> {
  return (
    await api.post<TagApplied>(`/curriculum-items/${kind}/${itemId}/tags`, {
      tag_value_id: tagValueId,
      inherit,
    })
  ).data;
}

/** Removes a tag that was set directly; what it passed on goes with it. */
export async function removeTagging(taggingId: string): Promise<void> {
  await api.delete(`/taggings/${taggingId}`);
}

/** TanStack Query keys, in one place so invalidation stays consistent. */
/** Check a framework pack file (JSON). Problems in the file come back in the result. */
export async function previewFrameworkPack(file: File): Promise<PackPreview> {
  // The file is the request body, not a form: large files stream, and nothing is parsed here.
  return (
    await api.post<PackPreview>('/framework-packs/preview', file, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 300_000,
    })
  ).data;
}

/** Import the pack of a valid preview. */
export async function importFrameworkPack(
  token: string,
  activate: boolean
): Promise<PackImportResult> {
  return (
    await api.post<PackImportResult>(
      '/framework-packs/import',
      { token, activate },
      { timeout: 600_000 }
    )
  ).data;
}

export async function fetchPackTemplates(): Promise<PackTemplate[]> {
  return (await api.get<PackTemplate[]>('/framework-packs/templates')).data;
}

/** Address of a template download (a plain link; the session cookie authorises it). */
export function packTemplateUrl(name: string): string {
  return `/api/v1/framework-packs/templates/${encodeURIComponent(name)}`;
}

export async function fetchFrameworkLibrary(): Promise<FrameworkLibrary> {
  return (await api.get<FrameworkLibrary>('/frameworks')).data;
}

/** A window of the children of `parentId` (the top level without it). */
export async function fetchFrameworkItems(
  frameworkId: string,
  params: { parentId?: string | null; offset?: number; limit?: number } = {}
): Promise<FrameworkItemPage> {
  return (
    await api.get<FrameworkItemPage>(`/frameworks/${frameworkId}/items`, {
      params: {
        parent_id: params.parentId ?? undefined,
        offset: params.offset ?? 0,
        limit: params.limit ?? 100,
      },
    })
  ).data;
}

export async function searchFramework(
  frameworkId: string,
  query: string,
  offset = 0
): Promise<FrameworkSearchPage> {
  return (
    await api.get<FrameworkSearchPage>(`/frameworks/${frameworkId}/search`, {
      params: { q: query, offset, limit: 50 },
    })
  ).data;
}

export async function fetchFrameworkItem(
  frameworkId: string,
  itemId: string
): Promise<FrameworkItemDetail> {
  return (await api.get<FrameworkItemDetail>(`/frameworks/${frameworkId}/items/${itemId}`)).data;
}

export async function fetchWhereMapped(frameworkId: string, itemId: string): Promise<WhereMapped> {
  return (
    await api.get<WhereMapped>(`/frameworks/${frameworkId}/items/${itemId}/mappings`)
  ).data;
}

/** The objectives of a version with their links, and what the user may do to each. */
export async function fetchMappingWorkspace(versionId: string): Promise<MappingWorkspace> {
  return (await api.get<MappingWorkspace>(`/curriculum-versions/${versionId}/mapping`)).data;
}

export async function addMappingLink(
  objectiveId: string,
  itemId: string,
  input: LinkInput
): Promise<WorkspaceLink> {
  return (
    await api.post<WorkspaceLink>(`/objectives/${objectiveId}/mapping-links`, {
      framework_item_id: itemId,
      ...input,
    })
  ).data;
}

export async function updateMappingLink(linkId: string, input: LinkInput): Promise<WorkspaceLink> {
  return (await api.patch<WorkspaceLink>(`/mapping-links/${linkId}`, input)).data;
}

/** `deleted` is false when the link was rejected instead (a suggestion of the system). */
export async function removeMappingLink(linkId: string): Promise<{ deleted: boolean }> {
  return (await api.delete<{ deleted: boolean }>(`/mapping-links/${linkId}`)).data;
}

export async function confirmMappingRecheck(linkId: string): Promise<WorkspaceLink> {
  return (await api.post<WorkspaceLink>(`/mapping-links/${linkId}/recheck`)).data;
}

/** One page of the links waiting for this user (ADR 040). */
export async function fetchReviewQueue(params: ReviewQueueParams): Promise<ReviewQueue> {
  return (
    await api.get<ReviewQueue>('/mapping/review-queue', {
      params: {
        stage: params.stage,
        sort: params.sort,
        offset: params.offset,
        version_id: params.versionId,
        framework_id: params.frameworkId,
        module_id: params.moduleId,
        min_confidence: params.minConfidence,
        max_confidence: params.maxConfidence,
      },
    })
  ).data;
}

/** How many links wait for this user, for the sidebar. */
export async function fetchReviewCount(): Promise<ReviewCounts> {
  return (await api.get<ReviewCounts>('/mapping/review-queue/count')).data;
}

export async function reviewMappingLink(
  linkId: string,
  request: ReviewRequest
): Promise<ReviewResult> {
  return (await api.post<ReviewResult>(`/mapping-links/${linkId}/review`, request)).data;
}

export async function bulkAcceptReview(request: BulkAcceptRequest): Promise<BulkAcceptResult> {
  return (await api.post<BulkAcceptResult>('/mapping/review-queue/bulk-accept', request)).data;
}

export async function deleteFramework(frameworkId: string): Promise<void> {
  await api.delete(`/frameworks/${frameworkId}`);
}

/** The AI settings, usage this month and what would happen to a call now (no keys). */
export async function fetchAiSettings(): Promise<AiSettings> {
  return (await api.get<AiSettings>('/ai/settings')).data;
}

/** Only the fields sent change. API keys are write-only. */
export async function updateAiSettings(input: AiUpdate): Promise<AiSettings> {
  return (await api.patch<AiSettings>('/ai/settings', input)).data;
}

/** Sends one fixed, harmless prompt through the chosen provider. */
export async function testAiConnection(): Promise<AiConnectionTest> {
  return (await api.post<AiConnectionTest>('/ai/test-connection')).data;
}

export const queryKeys = {
  aiSettings: ['ai-settings'] as const,
  frameworks: ['frameworks'] as const,
  frameworkItem: (frameworkId: string, itemId: string) =>
    ['frameworks', frameworkId, 'items', itemId] as const,
  frameworkMappings: (frameworkId: string, itemId: string) =>
    ['frameworks', frameworkId, 'items', itemId, 'mappings'] as const,
  frameworkSearch: (frameworkId: string, query: string) =>
    ['frameworks', frameworkId, 'search', query] as const,
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
  assessmentMethods: ['assessment-methods'] as const,
  assessableObjectives: (moduleId: string) =>
    ['modules', moduleId, 'assessable-objectives'] as const,
  creditCheck: (id: string) => ['curriculum-versions', id, 'credit-check'] as const,
  tagLists: ['tag-lists'] as const,
  packTemplates: ['framework-pack-templates'] as const,
  tagListPlaces: ['tag-list-places'] as const,
  passOnPreview: (taggingId: string) => ['tag-preview', 'pass-on', taggingId] as const,
  tagPreview: (kind: string, itemId: string, valueId: string) =>
    ['tag-preview', kind, itemId, valueId] as const,
  taxonomyScales: ['taxonomy-scales'] as const,
  linkOptions: (kind: 'module' | 'event', id: string) => ['link-options', kind, id] as const,
  copyForward: (id: string) => ['curriculum-versions', id, 'copy-forward'] as const,
  reviewQueue: (params: ReviewQueueParams) => ['review-queue', params] as const,
  reviewCount: ['review-queue', 'count'] as const,
  mappingWorkspace: (versionId: string) => ['curriculum-versions', versionId, 'mapping'] as const,
  versionChecks: (id: string) => ['curriculum-versions', id, 'objective-checks'] as const,
  nearDuplicates: (id: string) => ['curriculum-versions', id, 'near-duplicates'] as const,
  versionDiff: (id: string, base: string) => ['curriculum-versions', id, 'diff', base] as const,
};
