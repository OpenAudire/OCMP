# ADR 018: Terminology and Feature Profiles

## Status

Accepted

## Context

The brief (sections 6–7) asks for configurable terminology (e.g. "module" vs "course") and
feature profiles (core, health sciences) stored in institution settings and used by the UI,
and a default taxonomy per institution. The platform must stay discipline-neutral, with
health-specific features (role balance report, council evidence packs, clinical
placements) available when the health profile is on.

## Decision

### Settings shape
`institutions.settings` (JSON) holds sections, each validated with defaults by
`app/services/institution_settings.py`:

- `terminology`: overrides per term, `{"module": {"singular": "Course", "plural": "Courses"}}`.
  Terms: programme, curriculum version, phase, module, learning event, objective, framework,
  framework item (`app/core/profiles.py`). Words are trimmed, 1–64 characters.
- `profiles`: `core` is always on; `health` is optional.
- `default_taxonomy_scale`: key of an existing taxonomy scale, or none.
- `mapping`: the review policy (ADR 016).

Updates replace whole sections and keep keys this version does not know, so settings added
by a newer version survive. Invalid values are refused and leave settings unchanged.
Changes are recorded in the audit log (institutions are audited).

### Wording lives in the frontend
Default wording is in the frontend translations (`terms.<term>_one` / `terms.<term>_other`,
i18next plural keys); institutions store overrides only, which the UI layers over its
translations. Overrides apply in every UI language. A test fails if the backend's terms and
the English translations drift apart.

### Profiles enable features
Profiles map to features in code (`PROFILE_FEATURES`). The core profile enables everything
discipline-neutral; `health` adds `role_balance_report`, `council_evidence_pack` and
`clinical_placements`. The API returns the enabled features so the UI shows or hides them,
and endpoints for those features will check them too.

### API
- `GET /api/v1/institution` (any signed-in user): name, terminology overrides, profiles,
  enabled features, default taxonomy, mapping policy.
- `PATCH /api/v1/institution/settings` (`settings.manage`): replace sections; `null`
  restores a section's default.

OCMP runs one institution per instance (created by the setup wizard, Slice 0.17); the
first live institution is used.

## Consequences

- The frontend scaffold (Slice 0.15) loads the institution after sign-in and adds its
  terminology overrides to i18next.
- Per-language overrides, more profiles (e.g. engineering) and framework visibility by
  profile can be added without schema changes.
