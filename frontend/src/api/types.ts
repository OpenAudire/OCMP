/** Shapes returned by the OCMP API (see /api/docs). */

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  last_login_at: string | null;
  has_password: boolean;
}

export interface AuthOptions {
  password_min_length: number;
  password_max_length: number;
  sso_enabled: boolean;
  sso_provider_name: string;
}

export type ScopeType = 'instance' | 'faculty' | 'programme' | 'module' | 'learning_event';

export interface RoleAssignment {
  id: string;
  user_id: string;
  role: { key: string; name: string; permissions: string[] };
  scope_type: ScopeType;
  scope_id: string | null;
  expires_at: string | null;
  created_at: string;
}

export type Term =
  | 'programme'
  | 'curriculum_version'
  | 'phase'
  | 'module'
  | 'learning_event'
  | 'objective'
  | 'framework'
  | 'framework_item';

export interface TermOverride {
  singular: string;
  plural: string;
}

export type Feature = 'role_balance_report' | 'council_evidence_pack' | 'clinical_placements';

export interface Institution {
  id: string;
  name: string;
  short_code: string;
  country: string;
  terminology: Partial<Record<Term, TermOverride>>;
  profiles: string[];
  features: Feature[];
  default_taxonomy_scale: string | null;
  mapping: { four_eyes: boolean; second_review_for_rejects: boolean };
  credits?: CreditPolicy;
  quality?: { near_duplicate_min_percent: number };
}

/** Credits and notional hours settings (advice only; ADR 035). */
export interface CreditPolicy {
  hours_per_credit: number;
  tolerance_percent: number;
  credits_per_year: number;
  min_exit_level_credits: number | null;
}

export type VersionStatus = 'draft' | 'published' | 'archived';
export type PhaseKind = 'year' | 'phase' | 'block' | 'longitudinal_thread';
export type ObjectiveDomain = 'knowledge' | 'skill' | 'attitude';
export type ObjectiveStatus = 'draft' | 'ready_for_review' | 'approved' | 'retired';
export type AccreditationStatus =
  'not_applicable' | 'in_progress' | 'accredited' | 'conditional' | 'withdrawn';

export interface CurriculumVersion {
  id: string;
  academic_year: number;
  status: VersionStatus;
  published_at: string | null;
  based_on_id: string | null;
}

/** A programme with the versions the user may see, newest academic year first. */
export interface ProgrammeSummary {
  id: string;
  code: string;
  name: string;
  faculty_id: string;
  faculty_name: string;
  status: string;
  versions: CurriculumVersion[];
}

export interface Programme extends ProgrammeSummary {
  qualification_type: {
    key: string;
    name: string;
    nqf_exit_level: number;
    min_total_credits: number;
    /** Credits wanted at the type's own exit level, when it has such a rule. */
    min_exit_level_credits: number | null;
  } | null;
  nqf_exit_level: number | null;
  saqa_id: string | null;
  total_credits: number | null;
  /** Decimal, sent as a string. */
  minimum_duration_years: string | null;
  che_accreditation_status: AccreditationStatus;
  council_name: string | null;
  council_accreditation_status: AccreditationStatus;
}

export interface StructureEvent {
  id: string;
  title: string;
  position: number;
  week: number | null;
  format: string | null;
  format_value_id: string | null;
  contact_minutes: number;
  self_study_minutes: number;
  objective_count: number;
  /** The user may edit this session. */
  can_edit: boolean;
}

export interface StructureModule {
  id: string;
  code: string;
  name: string;
  phase_id: string | null;
  position: number;
  /** Decimal, sent as a string. */
  credits: string | null;
  nqf_level: number | null;
  /** Shown only to place the user's sessions; its details are not available to them. */
  context_only: boolean;
  objective_count: number;
  /** The user may edit the module and add or delete its sessions. */
  can_edit: boolean;
  events: StructureEvent[];
}

export interface StructurePhase {
  id: string;
  name: string;
  kind: PhaseKind;
  position: number;
  modules: StructureModule[];
}

export interface VersionStructure {
  version: CurriculumVersion;
  programme: { id: string; code: string; name: string };
  /** The user sees only some modules or sessions (a narrower role). */
  partial: boolean;
  outcome_count: number | null;
  phases: StructurePhase[];
  modules_without_phase: StructureModule[];
  /** The user may add, change and delete phases and modules (drafts only). */
  can_edit: boolean;
  /** The user may publish, unpublish, archive and unarchive the version. */
  can_change_status: boolean;
  /** The user may copy the version forward, and delete it while it is a draft. */
  can_copy_forward: boolean;
  /** The user may add, change and delete programme outcomes (drafts only). */
  can_edit_outcomes: boolean;
  /** The user may set programme outcomes to approved or retired. */
  can_approve_outcomes: boolean;
  /** The user may return a published version to draft (with a reason). */
  can_unpublish: boolean;
  /** The user may tag programme outcomes (drafts only). */
  can_edit_outcome_tags?: boolean;
}

export interface Objective {
  id: string;
  text: string;
  domain: ObjectiveDomain | null;
  taxonomy_level_id: string | null;
  status: ObjectiveStatus;
  position: number;
  parent_ids: string[];
  /** Accepted mapping links whose objective text changed after they were reviewed. */
  mappings_to_recheck?: number;
  tags?: ItemTag[];
}

/** Fields of an objective that can be saved; `parent_ids` replaces the links on offer. */
export interface ObjectiveInput {
  text: string;
  domain: ObjectiveDomain | null;
  taxonomy_level_id: string | null;
  status: ObjectiveStatus;
  parent_ids: string[];
}

export interface SavedObjective extends Objective {
  level: 'programme' | 'module' | 'learning_event';
}

/** A broader objective that can be chosen as an upward link. */
export interface ObjectiveOption {
  id: string;
  level: 'programme' | 'module';
  text: string;
  /** Code of the module the outcome belongs to; null for programme outcomes. */
  module_code: string | null;
}

export interface TaxonomyLevel {
  id: string;
  name: string;
  position: number;
  description: string;
}

export interface TaxonomyScale {
  key: string;
  name: string;
  description: string;
  levels: TaxonomyLevel[];
}

export interface ModuleDetail {
  id: string;
  version_id: string;
  phase_id: string | null;
  code: string;
  name: string;
  credits: string | null;
  nqf_level: number | null;
  description: string;
  external_lms_ref: string | null;
  event_count: number;
  contact_minutes: number;
  self_study_minutes: number;
  outcomes: Objective[];
  /** The user may add, change and delete the module's outcomes (drafts only). */
  can_edit_objectives: boolean;
  /** The user may set them to approved or retired. */
  can_approve_objectives: boolean;
  tags?: ItemTag[];
  /** The user may tag the module and its outcomes (drafts only). */
  can_edit_tags?: boolean;
  assessments?: Assessment[];
  /** The user may add, change and delete assessments (drafts only). */
  can_edit_assessments?: boolean;
  /** Planned hours against credits (advice). */
  hours?: ModuleHours | null;
}

export interface AssessmentItem {
  id: string;
  label: string;
  marks: string | null;
  position: number;
  /** Objectives of the module or its sessions that this item assesses. */
  objective_ids: string[];
}

export interface Assessment {
  id: string;
  module_id: string;
  name: string;
  method_value_id: string | null;
  method: string | null;
  weight: string | null;
  timing: string;
  time_minutes: number;
  position: number;
  items: AssessmentItem[];
}

export interface AssessmentInput {
  name: string;
  method_value_id: string | null;
  weight: number | null;
  timing: string;
  time_minutes: number;
}

export interface AssessmentItemInput {
  label: string;
  marks: number | null;
  objective_ids: string[];
}

export interface AssessmentMethod {
  id: string;
  label: string;
  list_name: string;
}

export interface AssessableObjective {
  id: string;
  level: 'module' | 'learning_event';
  text: string;
  /** The session that owns it; null for module outcomes. */
  event_title: string | null;
}

export type HoursStatus = 'ok' | 'under' | 'over' | 'no_credits';

export interface ModuleHours {
  module_id: string;
  code: string;
  name: string;
  phase_id: string | null;
  credits: string | null;
  nqf_level: number | null;
  contact_hours: string;
  self_study_hours: string;
  assessment_hours: string;
  planned_hours: string;
  expected_hours: string | null;
  difference_percent: string | null;
  status: HoursStatus;
}

export type YearStatus = 'ok' | 'under' | 'over' | 'not_checked';

export interface YearCredits {
  phase_id: string;
  name: string;
  kind: PhaseKind;
  credits: string;
  modules: number;
  modules_without_credits: number;
  expected_credits: number | null;
  status: YearStatus;
}

export interface LevelCredits {
  level: number | null;
  credits: string;
  modules: number;
}

export interface CreditFinding {
  code: string;
  params: Record<string, string | number>;
}

/** Credits and notional hours for a whole version (advice, never blocks saving). */
export interface VersionCreditCheck {
  policy: CreditPolicy;
  modules: ModuleHours[];
  years: YearCredits[];
  unphased_credits: string;
  unphased_modules: number;
  levels: LevelCredits[];
  total_credits: string;
  programme_total_credits: number | null;
  qualification_name: string | null;
  qualification_min_credits: number | null;
  /** Credits wanted at the exit level (the institution's figure, else the qualification type's). */
  exit_level_minimum: number | null;
  exit_level: number | null;
  findings: CreditFinding[];
}

export interface LearningEventDetail {
  id: string;
  module_id: string;
  title: string;
  format: string | null;
  format_value_id: string | null;
  contact_minutes: number;
  self_study_minutes: number;
  week: number | null;
  position: number;
  description: string;
  external_lms_ref: string | null;
  objectives: Objective[];
  /** The user may add, change and delete the session's objectives (drafts only). */
  can_edit_objectives: boolean;
  /** The user may set them to approved or retired. */
  can_approve_objectives: boolean;
  tags?: ItemTag[];
  /** The user may tag the session and its objectives (drafts only). */
  can_edit_tags?: boolean;
}

export interface PhaseInput {
  name: string;
  kind: PhaseKind;
}

export interface SavedPhase extends PhaseInput {
  id: string;
  version_id: string;
  position: number;
}

export interface ModuleInput {
  code: string;
  name: string;
  /** Null: a longitudinal module that spans phases. */
  phase_id: string | null;
  /** Decimal, sent as a string. */
  credits: string | null;
  nqf_level: number | null;
  description: string;
  external_lms_ref: string | null;
}

export interface SavedModule extends ModuleInput {
  id: string;
  version_id: string;
  position: number;
}

export interface LearningEventInput {
  title: string;
  format_value_id: string | null;
  contact_minutes: number;
  self_study_minutes: number;
  week: number | null;
  description: string;
  external_lms_ref: string | null;
}

export interface SavedLearningEvent extends LearningEventInput {
  id: string;
  module_id: string;
  position: number;
}

export interface TeachingFormat {
  id: string;
  label: string;
  list_name: string;
}

export interface PhaseCopyInput {
  name: string;
  /** A new, unused code for each module of the phase, by module id. */
  module_codes: Record<string, string>;
}

export interface ModuleCopyInput {
  code: string;
  name: string;
  /** Leave out to keep the module's phase; null puts the copy across phases. */
  phase_id?: string | null;
}

export type SkipReason = 'expired' | 'account_inactive' | 'account_deleted' | 'not_allowed';

/** A role assignment at a module or session of the version being copied forward. */
export interface RoleAssignmentCopy {
  id: string;
  user_name: string;
  role_name: string;
  scope_type: 'module' | 'learning_event';
  /** The module or session it is held at. */
  item: string;
  expires_at: string | null;
  /** Why it cannot be copied; null when it is copied unless unticked. */
  skip_reason: SkipReason | null;
}

export interface CopyForwardPreview {
  /** Suggested: the year after the programme's newest version. */
  academic_year: number;
  taken_years: number[];
  phases: number;
  modules: number;
  learning_events: number;
  objectives: number;
  mappings: number;
  /** False when the user may not assign roles in the programme: none are copied. */
  can_copy_roles: boolean;
  role_assignments: RoleAssignmentCopy[];
}

export type ItemKind = 'phase' | 'module' | 'learning_event' | 'assessment' | 'objective';
export type ChangeType = 'added' | 'removed' | 'changed';

export interface FieldChange {
  field: string;
  before: string | number | null;
  after: string | number | null;
}

export interface ItemChange {
  kind: ItemKind;
  change: ChangeType;
  id: string | null;
  base_id: string | null;
  label: string;
  /** The module of a session, the owner of an objective. */
  context: string | null;
  level: 'programme' | 'module' | 'learning_event' | null;
  fields: FieldChange[];
}

/** What changed from `base` to `version`. */
export interface VersionDiff {
  programme: { id: string; code: string; name: string };
  base: CurriculumVersion;
  version: CurriculumVersion;
  summary: Record<ItemKind, { added: number; removed: number; changed: number }>;
  changes: ItemChange[];
}

/** Objective quality checker (rule based, advisory; ADR 033). */
export type FindingSeverity = 'warning' | 'info';

export interface QualityFinding {
  code: string;
  severity: FindingSeverity;
  message_key: string;
  suggestion_key: string | null;
  params: Record<string, string>;
}

/** A taxonomy level the leading verb points to; offered, never applied. */
export interface LevelSuggestion {
  taxonomy_level_id: string;
  level_name: string;
  scale_key: string;
  scale_name: string;
}

export interface QualityCheck {
  findings: QualityFinding[];
  detected_verb: string | null;
  suggestions: LevelSuggestion[];
}

export interface QualityCheckInput {
  text: string;
  domain: ObjectiveDomain | null;
  taxonomy_level_id: string | null;
  has_parent_links: boolean | null;
}

/** Another objective of the same version and level that reads almost the same (ADR 044). */
export interface NearDuplicate {
  objective_id: string;
  percent: number;
  level: 'programme' | 'module' | 'learning_event';
  text: string;
  module_id: string | null;
  module_code: string | null;
  event_id: string | null;
  event_title: string | null;
}

export interface CheckedObjective extends QualityCheck {
  objective_id: string;
  level: 'programme' | 'module' | 'learning_event';
  text: string;
  status: ObjectiveStatus;
  domain: ObjectiveDomain | null;
  module_id: string | null;
  module_code: string | null;
  event_id: string | null;
  event_title: string | null;
  can_edit: boolean;
  near_duplicates: NearDuplicate[];
}

export interface VersionChecks {
  version_id: string;
  rules_language: string;
  rules_version: number;
  /** False while embeddings are off: the list has no near-duplicate findings then. */
  near_duplicates_checked: boolean;
  objectives: CheckedObjective[];
}

/** What the objective cards show; `enabled` is false while embeddings are off. */
export interface NearDuplicates {
  version_id: string;
  enabled: boolean;
  threshold_percent: number;
  objectives: { objective_id: string; matches: NearDuplicate[] }[];
}

/** Tag lists and tagging (ADR 034). */
export type TaggableKind = 'module' | 'learning_event' | 'objective';

export type TagListKind =
  | 'teaching_method'
  | 'assessment_method'
  | 'theme'
  | 'thread'
  | 'keyword'
  | 'resource'
  | 'epa'
  | 'custom';

export interface TagValue {
  id: string;
  label: string;
  code: string | null;
  description: string;
  position: number;
  is_active: boolean;
  /** Taggings and sessions using it; only filled in for people who manage tag lists. */
  usage_count: number;
}

export interface TagList {
  id: string;
  key: string;
  name: string;
  kind: TagListKind;
  description: string;
  /** Item types the list may tag: programme, module, learning_event, objective. */
  entity_types: string[];
  is_active: boolean;
  /** Null: an institution-wide list; otherwise the faculty it belongs to. */
  faculty_id: string | null;
  faculty_name: string | null;
  /** The user may change this list and its tags. */
  can_manage: boolean;
  values: TagValue[];
}

/** Where the user may create tag lists. */
export interface TagListPlaces {
  institution: boolean;
  faculties: { id: string; name: string }[];
}

export interface TagListInput {
  key: string;
  name: string;
  kind: TagListKind;
  description: string;
  entity_types: string[];
  /** Omitted or null: an institution-wide list. */
  faculty_id?: string | null;
}

export interface TagValueInput {
  label: string;
  code: string | null;
  description: string;
}

/** The item an inherited tag came from. */
export interface TagSource {
  item_type: 'programme' | TaggableKind;
  item_id: string;
  name: string;
}

/** A tag on an item: set directly (removable), inherited from sources, or both. */
export interface ItemTag {
  tag_value_id: string;
  label: string;
  list_id: string;
  list_name: string;
  direct_tagging_id: string | null;
  sources: TagSource[];
  /** Items below that this tag has not reached yet (added or linked after it was set). */
  not_reached?: number;
}

export type PreviewStatus = 'new' | 'has_tag' | 'not_applicable';

export interface PreviewItem {
  item_type: 'programme' | TaggableKind;
  item_id: string;
  name: string;
  level: 'programme' | 'module' | 'learning_event' | null;
  module_code: string | null;
  status: PreviewStatus;
}

export interface InheritancePreview {
  tag_value_id: string;
  label: string;
  list_name: string;
  item_has_tag: boolean;
  items: PreviewItem[];
}

export interface TagApplied {
  tags: ItemTag[];
  inherited_count: number;
}

export interface PackProblem {
  /** Where in the file, such as `items[3].title`; empty for the whole file. */
  path: string;
  message: string;
}

export interface PackMetadata {
  key: string;
  name: string;
  version: string;
  publisher: string;
  licence: string;
  profile: 'core' | 'health' | 'other';
  description: string;
  url: string | null;
  template: boolean;
}

export interface PackCounts {
  items: number;
  levels: number;
  root_items: number;
  cross_references: number;
  external_references: number;
  crosswalks: number;
  crosswalk_entries: number;
  taxonomy_scales: number;
  tag_lists: number;
  tag_values: number;
}

export interface PackSampleItem {
  code: string;
  title: string;
  depth: number;
}

export interface PackPreview {
  valid: boolean;
  errors: PackProblem[];
  warnings: string[];
  format_version: number | null;
  metadata: PackMetadata | null;
  counts: PackCounts | null;
  sample: PackSampleItem[];
  sample_truncated: boolean;
  token: string | null;
  expires_in: number | null;
}

export interface PackImportResult {
  framework_id: string;
  key: string;
  name: string;
  version: string;
  status: 'draft' | 'active' | 'superseded' | 'retired';
  items: number;
  cross_references: number;
  external_references: number;
  crosswalks: number;
  crosswalk_entries: number;
  scales_created: number;
  tag_lists_created: number;
  tag_values_added: number;
  superseded_versions: number;
}

export interface PackTemplate {
  name: string;
  title: string;
  description: string;
  items: number;
}

// --- Frameworks (library, tree, where mapped) ---

export type FrameworkStatus = 'draft' | 'active' | 'superseded' | 'retired';
export type FrameworkProfile = 'core' | 'health' | 'other';

export interface FrameworkSummary {
  id: string;
  key: string;
  name: string;
  version_label: string;
  publisher: string;
  licence_note: string;
  description: string;
  url: string | null;
  profile: FrameworkProfile;
  status: FrameworkStatus;
  item_count: number;
  top_level_count: number;
  level_count: number;
}

export interface FrameworkLibrary {
  frameworks: FrameworkSummary[];
  can_manage: boolean;
}

export interface FrameworkTreeItem {
  id: string;
  code: string;
  title: string;
  depth: number;
  child_count: number;
  /** Mapping links (not rejected) the user may see. */
  mapped_count: number;
}

/** A window of the children of one parent: `offset` is the place of its first item. */
export interface FrameworkItemPage {
  parent_id: string | null;
  offset: number;
  total: number;
  items: FrameworkTreeItem[];
}

export interface FrameworkAncestor {
  id: string;
  code: string;
  title: string;
}

export interface FrameworkDetailAncestor extends FrameworkAncestor {
  sibling_index: number;
}

export interface FrameworkSearchHit extends FrameworkTreeItem {
  path: FrameworkAncestor[];
}

export interface FrameworkSearchPage {
  query: string;
  offset: number;
  total: number;
  hits: FrameworkSearchHit[];
}

export interface FrameworkItemDetail {
  id: string;
  framework_id: string;
  code: string;
  title: string;
  description: string;
  depth: number;
  child_count: number;
  mapped_count: number;
  path: FrameworkDetailAncestor[];
  sibling_index: number;
}

export interface MappedObjective {
  link_id: string;
  status: 'suggested' | 'accepted' | 'rejected' | 'needs_second_review';
  source: 'ai' | 'human' | 'import' | 'migrated';
  coverage: number | null;
  depth_match: DepthMatch | null;
  needs_recheck: boolean;
  needs_discussion: boolean;
  objective_id: string;
  objective_text: string;
  level: 'programme' | 'module' | 'learning_event';
  programme_id: string;
  programme_name: string;
  version_id: string;
  academic_year: number;
  version_status: VersionStatus;
  module_id: string | null;
  module_code: string | null;
  module_name: string | null;
  learning_event_id: string | null;
  learning_event_title: string | null;
}

export interface WhereMapped {
  item_id: string;
  total: number;
  limit: number;
  mappings: MappedObjective[];
}

/** How the objective's level compares with the level the item expects (ADR 039). */
export type DepthMatch = 'below' | 'matches' | 'above' | 'not_applicable';

export type LinkStatus = 'suggested' | 'accepted' | 'rejected' | 'needs_second_review';

/** A mapping link as the mapping workspace shows it. */
export interface WorkspaceLink {
  id: string;
  framework_id: string;
  framework_name: string;
  framework_version_label: string;
  item_id: string;
  item_code: string;
  item_title: string;
  coverage: number | null;
  depth_match: DepthMatch | null;
  rationale: string;
  source: 'ai' | 'human' | 'import' | 'migrated';
  status: LinkStatus;
  accept_method: AcceptMethod | null;
  needs_recheck: boolean;
  needs_discussion: boolean;
}

export interface WorkspaceObjective {
  id: string;
  text: string;
  level: 'programme' | 'module' | 'learning_event';
  phase_id: string | null;
  phase_name: string | null;
  module_id: string | null;
  module_code: string | null;
  module_name: string | null;
  learning_event_id: string | null;
  learning_event_title: string | null;
  can_edit: boolean;
  can_review: boolean;
  links: WorkspaceLink[];
}

export interface MappingWorkspace {
  version_id: string;
  academic_year: number;
  version_status: VersionStatus;
  programme_id: string;
  programme_name: string;
  editable: boolean;
  four_eyes: boolean;
  objectives: WorkspaceObjective[];
}

export interface LinkInput {
  coverage: number;
  depth_match: DepthMatch;
  rationale: string;
}

/** Which pile of review work a link is in for the person (ADR 040). */
export type ReviewStage = 'first' | 'second' | 'recheck';

export type ReviewSort = 'confidence_desc' | 'confidence_asc' | 'module';

export type ReviewDecision = 'accept' | 'reject' | 'second_review';

/** A link in the review queue. No reviewer or author names are returned. */
export type AcceptMethod = 'individual' | 'bulk' | 'automatic' | 'imported';

export interface ReviewLink {
  id: string;
  stage: ReviewStage;
  status: LinkStatus;
  source: 'ai' | 'human' | 'import' | 'migrated';
  /** How an accepted link was accepted; "bulk" means Accept all, not looked at one by one. */
  accept_method: AcceptMethod | null;
  confidence: number | null;
  coverage: number | null;
  depth_match: DepthMatch | null;
  rationale: string;
  evidence_quote: string;
  needs_recheck: boolean;
  needs_discussion: boolean;
  /** What the first reviewer decided (second stage only), never who. */
  first_decision: ReviewDecision | null;
  version_id: string;
  academic_year: number;
  objective: {
    id: string;
    text: string;
    level: 'programme' | 'module' | 'learning_event';
    module_code: string | null;
    module_name: string | null;
    learning_event_title: string | null;
  };
  item: {
    id: string;
    code: string;
    title: string;
    group: string | null;
    framework_id: string;
    framework_name: string;
    framework_version_label: string;
  };
}

export interface ReviewProgress {
  total: number;
  accepted: number;
  rejected: number;
  second_review: number;
  waiting: number;
}

export interface ReviewCounts {
  first: number;
  second: number;
  recheck: number;
  /** Suggestions this person can act on now (first and second review): the sidebar number. */
  waiting: number;
  total: number;
}

export interface ReviewQueue {
  stage: ReviewStage;
  total: number;
  offset: number;
  limit: number;
  items: ReviewLink[];
  progress: ReviewProgress;
  counts: ReviewCounts;
  facets: {
    versions: { id: string; programme_name: string; academic_year: number }[];
    frameworks: { id: string; name: string; version_label: string }[];
    modules: { id: string; code: string; name: string }[];
  };
  four_eyes: boolean;
  bulk_min_confidence: number;
  bulk_max_links: number;
}

export interface ReviewQueueParams {
  stage: ReviewStage;
  versionId?: string;
  frameworkId?: string;
  moduleId?: string;
  minConfidence?: number;
  maxConfidence?: number;
  sort: ReviewSort;
  offset: number;
}

export interface ReviewRequest {
  decision: ReviewDecision;
  expected_status: LinkStatus;
  coverage?: number;
  depth_match?: DepthMatch;
}

export interface ReviewResult {
  id: string;
  status: LinkStatus;
  needs_discussion: boolean;
}

export interface BulkAcceptRequest {
  min_confidence: number;
  version_id?: string;
  framework_id?: string;
  module_id?: string;
  dry_run: boolean;
}

export interface BulkAcceptResult {
  eligible: number;
  processed: number;
  remaining: number;
  status_after: LinkStatus;
  dry_run: boolean;
}

// --- AI settings (Admin > AI settings) ---------------------------------------------

export type AiProviderKind = 'null' | 'anthropic' | 'openai_compatible' | 'ollama';
export type AiDataLocation = 'local' | 'south_africa' | 'outside_south_africa';
export type AiKeyStatus = 'not_set' | 'set' | 'unreadable';

export interface AiProvider {
  kind: Exclude<AiProviderKind, 'null'>;
  model: string | null;
  base_url: string | null;
  data_location: AiDataLocation;
  data_location_fixed: boolean;
  outside_south_africa: boolean;
  is_local: boolean;
  temperature: string | null;
  input_price_per_mtok: string | null;
  output_price_per_mtok: string | null;
  key_mode: 'required' | 'optional' | 'none';
  /** Whether a key is stored. The key itself is never returned. */
  key_status: AiKeyStatus;
  key_set_at: string | null;
  base_url_mode: 'fixed' | 'required';
  default_base_url: string | null;
  suggested_models: string[];
  /** Fields still to fill in: model, base_url, api_key. */
  missing: string[];
}

export interface AiBudget {
  monthly_cost_cap: string | null;
  monthly_token_cap: number | null;
  monthly_call_cap: number | null;
  max_calls_per_run: number;
  max_output_tokens: number;
}

export type AiStatusReason =
  | 'not_configured'
  | 'local_only'
  | 'acknowledgement_missing'
  | 'budget_exceeded';

export interface AiSettings {
  active_provider: AiProviderKind;
  local_only: boolean;
  on_personal_data: 'refuse' | 'redact';
  budget: AiBudget;
  acknowledgement: { acknowledged_at: string | null; current: boolean };
  usage: { period_start: string; period_end: string; calls: number; tokens: number; cost: string };
  status: { state: 'off' | 'ready' | 'blocked'; reasons: AiStatusReason[]; budget_message: string | null };
  providers: AiProvider[];
  /** Whether an API key can be stored: false in production without SECRETS_ENCRYPTION_KEYS. */
  encryption: { keys_stored_ok: boolean; rotation_needed: boolean };
}

export interface AiProviderUpdate {
  model?: string | null;
  base_url?: string | null;
  data_location?: AiDataLocation;
  temperature?: string | null;
  input_price_per_mtok?: string | null;
  output_price_per_mtok?: string | null;
  /** Write-only. */
  api_key?: string;
  clear_api_key?: boolean;
}

export interface AiUpdate {
  active_provider?: AiProviderKind;
  local_only?: boolean;
  on_personal_data?: 'refuse' | 'redact';
  monthly_cost_cap?: string | null;
  monthly_token_cap?: number | null;
  monthly_call_cap?: number | null;
  max_calls_per_run?: number;
  max_output_tokens?: number;
  acknowledge_outside_south_africa?: boolean;
  providers?: Partial<Record<Exclude<AiProviderKind, 'null'>, AiProviderUpdate>>;
}

export interface AiConnectionTest {
  ok: boolean;
  code: string;
  message: string;
  provider: AiProviderKind;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
}
