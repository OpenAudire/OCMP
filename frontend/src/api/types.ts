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

export type ItemKind = 'phase' | 'module' | 'learning_event' | 'objective';
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
}

export interface VersionChecks {
  version_id: string;
  rules_language: string;
  rules_version: number;
  objectives: CheckedObjective[];
}
