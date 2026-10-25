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
export type ObjectiveStatus = 'draft' | 'approved' | 'retired';
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
  contact_minutes: number;
  self_study_minutes: number;
  objective_count: number;
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
}

export interface Objective {
  id: string;
  text: string;
  domain: ObjectiveDomain | null;
  status: ObjectiveStatus;
  position: number;
  parent_ids: string[];
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
}

export interface LearningEventDetail {
  id: string;
  module_id: string;
  title: string;
  format: string | null;
  contact_minutes: number;
  self_study_minutes: number;
  week: number | null;
  position: number;
  description: string;
  external_lms_ref: string | null;
  objectives: Objective[];
}
