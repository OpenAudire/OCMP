# ADR 019: Frontend Architecture

## Status

Accepted

## Context

ADR 002 chose React, TypeScript, Vite and Mantine with TanStack Query and React Router.
The brief (section 11) sets the main navigation (Dashboard · Curriculum · Mapping ·
Frameworks · Reports · Search · Admin; students see Explorer · Search only), WCAG 2.2 AA,
light and dark themes, phone-width layouts, translations for all text, and configurable
terminology and feature profiles (ADR 018).

## Decision

### Structure (`frontend/src`)
- `api/`: one axios client (`/api/v1`, cookies, `xsrfCookieName: ocmp_csrf`,
  `xsrfHeaderName: X-CSRF-Token` per ADR 009), typed endpoint functions, `ApiError` with
  status and server message, and all TanStack Query keys in `queryKeys`.
- `session/`: `useSession()` loads the user and role assignments (null when signed out);
  `collectPermissions` unions the permissions of all roles, applying the same implication
  as the server (`curriculum.view` ⇒ `curriculum.view_published`).
- `institution/`: `InstitutionProvider` loads the institution after sign-in and layers its
  terminology over the translations; `useInstitution()` and `useFeature()` expose settings
  and profile features.
- `layout/`: the Mantine `AppShell` (header, responsive navbar that collapses to a burger
  below `sm`, light/dark toggle, user menu, skip link) and the navigation rules.
- `routes/`: an auth guard (sign-in redirect with `next`), a start page that opens the first
  section the user may use, section guards, not-found and no-access pages.

### Navigation by permission
Each nav item has a visibility rule over the user's permissions at any scope: staff
sections need the matching permission; the Explorer is for people who may read the
published curriculum but not the staff view (students, external reviewers). Direct
addresses to hidden sections show "No access". This only shapes the UI: the API enforces
every permission (ADR 012). `/auth/me/roles` returns each role's permissions for this.

### Data fetching
TanStack Query with a 5-minute stale time; client errors (4xx) are not retried. 401 means
"signed out" rather than an error; 404 on the institution means "not set up yet".

### Translations and terminology
All UI text uses translation keys. Curriculum nouns use `terms.*` keys; institution
overrides are added to i18next on load (`bindI18nStore: 'added'` re-renders components).

### Accessibility
Landmarks (`header`, labelled `nav`, `main`), a skip-to-content link, labelled icon
buttons, Mantine's visible focus rings and colour scheme following the system by default.

### Tests
Vitest + Testing Library with the real i18n setup; API calls are mocked at the
`api/endpoints` module. jsdom stand-ins for `matchMedia` and `ResizeObserver` are plain
functions so tests that reset mocks cannot remove them.

## Consequences

- Sections are placeholders until their phase 1 features are built.
- The single bundle is about 155 kB gzipped; route-level code splitting should be added as
  sections grow (brief: slow connections).
- The sign-in form arrives in Slice 0.16, the setup wizard in 0.17.
