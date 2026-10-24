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
