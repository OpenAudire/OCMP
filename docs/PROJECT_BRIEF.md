# Claude Code Build Prompt — Open Curriculum Mapping Platform (OCMP)

## How to use this file

1. Create an empty GitHub repository (e.g. `ocmp`) and clone it to your computer.
2. Save this file in the repo as `docs/PROJECT_BRIEF.md` and commit it.
3. Open Claude Code in the repo folder and paste the **Kick-off prompt** below as your first message.
4. Work one phase at a time. When a phase's "Definition of done" is met, paste the next phase prompt (bottom of this file).
5. Review every plan Claude Code proposes before saying "go". You stay in charge of decisions.

---

## Kick-off prompt (paste this into Claude Code)

> Read `docs/PROJECT_BRIEF.md` in full. It is the specification for this project.
>
> Before writing any code:
> 1. Summarise the brief back to me in 10 bullet points so I can confirm you understood it.
> 2. List every assumption you would have to make and every question where the brief is ambiguous. Ask me those questions and wait for answers.
> 3. Propose the repository layout, the key architecture decisions (as short ADRs in `docs/adr/`), and a step-by-step plan for **Phase 0 only**, broken into small vertical slices that each end in passing tests and a commit.
>
> Wait for my approval before starting. Then build Phase 0 slice by slice. After each slice: run the tests and linters, fix failures, update `docs/PROGRESS.md`, and commit with a Conventional Commit message. Create and maintain a `CLAUDE.md` file with the project conventions you are following, so future sessions stay consistent.
>
> Rules for the whole project:
> - Never commit secrets. Use `.env.example` with placeholders.
> - Never include copyrighted framework text (HPCSA documents, CanMEDS, NKLM, etc.). Ship schemas, empty templates and a fictional demo framework only.
> - Never send personal information (names, emails, student numbers, grades) to any AI provider. Enforce this in code, not just by convention.
> - For any external API (Brightspace, AI providers, LTI), check the current official documentation before writing integration code. Do not guess endpoint paths or payloads; if you cannot verify, stub it behind an interface and tell me.
> - When the brief and good practice conflict, stop and ask me.

---

# PROJECT BRIEF

## 1. What we are building

An **open-source, self-hosted curriculum mapping platform** that any university can install on its own servers from GitHub. It is a better alternative to LOOOP (Learning Opportunities, Objectives and Outcomes Platform, Charité Berlin) and borrows the best features of One45 Curriculum (Acuity Insights).

It lets institutions:
- Build their curriculum structure: programme → phase/year → module → learning event (session) → learning objective, with outcomes at programme, module and session level linked upward.
- Map objectives to any number of **frameworks** (competency frameworks, qualification level descriptors, taxonomies, keyword vocabularies), imported as data.
- Use **AI to draft mappings**, which people then accept, edit or reject in a fast review queue.
- See **coverage, gaps, redundancies, workload and credits**, and produce accreditation evidence.
- Compare the **declared** curriculum with what is **delivered** in the LMS (Brightspace first).
- Give students and staff a clear, searchable view of the curriculum.

Primary market: **South African health sciences faculties** (HPCSA, CHE, SAQA/NQF, POPIA). The core must stay **discipline-neutral** so any programme (engineering, education, law, business, etc.) can use it.

## 2. Problems we must solve (LOOOP gaps) — each is a requirement

| # | Gap in LOOOP | Requirement for OCMP |
|---|---|---|
| G1 | Mapping is slow manual work (Charité: ~1,500 hours over 16 months for one framework) | AI-drafted mappings with confidence + reason; bulk review queue with keyboard shortcuts; reuse of earlier accepted mappings as hints |
| G2 | Framework cross-references skipped because of workload | Frameworks stored as a graph with cross-references; used automatically in coverage and search |
| G3 | Simple match counts overstate coverage (85% vs 52% by careful content comparison) | Each mapping link stores coverage (0–5) and depth match; reports show several coverage methods side by side, clearly labelled |
| G4 | Only the declared curriculum is captured | "Declared vs delivered" comparison against LMS content and schedules |
| G5 | Weak links to timetable, venues, staff and LMS | Scheduled sessions with date, venue, group, facilitator; Brightspace sync; LTI launch inside courses |
| G6 | No help writing good objectives; no text analysis | Objective quality checker (verbs, Bloom/Miller level, measurability, duplicates); similarity network view |
| G7 | Framework version changes force a full remap | Versioned frameworks with crosswalks; AI-assisted migration of links to the new version, confirmed by people |

Keep these LOOOP strengths: hierarchical outcome levels; knowledge/skills/attitudes domain; a combined Bloom + Miller depth scale; access for students, staff and accreditors; organisational views (what is on, when, by whom) given equal weight to content views.

## 3. One45 features to include

- Mapping at multiple levels (programme, phase, module, session, objective) to multiple frameworks and taxonomies.
- Configurable **tag lists** ("mapping lists"): assessment methods, instructional methods, resources, EPAs, examination frameworks, themes and threads, keywords, custom lists.
- **Inheritance**: a tag or mapping set on a module objective can flow down to every linked session. Always show a preview of every affected item before saving, and record the inheritance source.
- Support for different curriculum models: conventional years, phased curricula, longitudinal integrated clerkships; teaching formats such as PBL, CBL, TBL, small-group learning, lectures, practicals, clinical placements (all configurable).
- **Reports**: gaps and redundancies, assessment coverage, teaching types, programme objective traceability, contact hours; curriculum schedule report; curriculum relationship report (each item → its objectives → its tags, one row each).
- **Curriculum search**: keyword, "hot topic" and competency search, with advanced filters by any tag list or framework.
- **Custom roles and permissions**, scoped to faculty, programme or module.
- **LMS alignment**: sync learning events and facilitator names from the LMS (One45 does this for Canvas; we do it for Brightspace).
- **Curriculum schedule**: sessions, sections per group, copy-per-group, facilitator teaching-load report, curriculum calendar.
- **Accreditation reporting** (for us: HPCSA and CHE evidence packs, plus MedBiquitous Curriculum Inventory export).
- **CBME links**: assessments, assessment items and EPAs linked to objectives; blueprints (phase 3).
- **Mobile-friendly** responsive UI.
- **Committee dashboard** with key indicators.

Do NOT build: MSPE letters, admissions tools, or full learner evaluation workflows (out of scope).

## 4. Users and roles

| Role | Can do | Scope |
|---|---|---|
| Platform admin | Install settings, SSO, AI provider, integrations, budgets, terminology, profiles | Instance |
| Curriculum office | Manage frameworks, tag lists, curriculum versions, all reports | Faculty |
| Programme director | Programme outcomes, structure, coverage review, publish versions | Programme |
| Module coordinator | Modules, learning events, objectives, mapping, review AI suggestions | Module |
| Lecturer/facilitator | Edit objectives of own sessions, view own schedule | Own sessions |
| Mapper/reviewer | Create and review mappings (first and second review) | Assigned items |
| Student | Read-only curriculum explorer, search, "what is assessed in this exam" | Published content |
| External reviewer | Time-limited read-only access to evidence packs | Selected programmes |

Roles are assigned per scope (instance, faculty, programme, module). One person can hold several roles.

## 5. Technology stack (propose changes via ADR if you see a better option, but ask first)

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic migrations.
- **Database**: PostgreSQL 16 with `pgvector` (embeddings) and built-in full-text search.
- **Background jobs**: Redis + a worker library (Celery or Dramatiq — choose one in an ADR).
- **Frontend**: React + TypeScript + Vite; an accessible component library (e.g. Mantine or shadcn/ui on Radix); TanStack Query; React Router; react-i18next for translations; ECharts for charts; Cytoscape.js for network/graph views.
- **Auth**: local accounts (argon2 hashing) + OpenID Connect and SAML 2.0 for university SSO (e.g. Microsoft Entra ID). Session cookies, CSRF protection.
- **Files**: Excel via `openpyxl`; PDF reports via a server-side HTML-to-PDF renderer (e.g. WeasyPrint); document text extraction for PDF/DOCX uploads.
- **Deployment**: Docker Compose (services: `web`, `api`, `worker`, `db`, `redis`, `caddy`; optional `ollama` and `embeddings` profiles). Caddy for automatic HTTPS. Helm chart is a later item.
- **CI/CD**: GitHub Actions — lint (ruff, mypy, eslint, tsc), tests, build and push images to GitHub Container Registry on tagged releases; Dependabot; CodeQL.
- **Docs**: MkDocs Material published to GitHub Pages; OpenAPI docs auto-generated.
- **Licence**: ask me (MIT, Apache-2.0 or AGPL-3.0). Default to Apache-2.0 placeholder until I decide.

Suggested monorepo layout:
```
/backend        FastAPI app, models, services, AI, connectors, tests
/frontend       React app, tests
/packs          Framework/taxonomy pack schema, templates, demo packs
/deploy         docker-compose.yml, Caddyfile, .env.example, backup scripts
/docs           MkDocs site, ADRs, PROJECT_BRIEF.md, PROGRESS.md
/scripts        dev helpers, seed data, eval harness
```

## 6. Data model (minimum; refine in an ADR)

All tables: UUID primary keys, `created_at`, `updated_at`, `created_by`. Soft delete where history matters. Every change to curriculum, framework or mapping data writes an **AuditLog** entry (entity, action, before, after, actor, timestamp).

- **Institution**: name, short code, country, settings (terminology overrides, enabled profiles, default taxonomy).
- **Faculty**, **Department**.
- **Programme**: faculty, code, name, qualification type, NQF exit level, SAQA ID, total credits, minimum duration, status.
- **CurriculumVersion**: programme, academic year, status (draft / published / archived), based_on (for copying a year forward). Diff two versions.
- **Phase**: version, name, order, kind (year / phase / block / longitudinal thread).
- **Module**: version, phase (nullable for longitudinal), code, name, credits, NQF level, coordinators, description, external LMS reference.
- **LearningEvent** (session): module, title, format (from tag list), contact minutes, estimated self-study minutes, order/week, description, external LMS reference.
- **ScheduledSession** (phase 2): learning event, start, end, venue, group/section, facilitators.
- **Objective**: level (programme / module / event), owner (programme, module or event id), text, domain (knowledge / skill / attitude), taxonomy level, detected verb, quality flags, status. Many-to-many **ObjectiveLink** upward (event objective → module outcome → programme outcome).
- **TaxonomyScale** + **TaxonomyLevel**: e.g. Bloom revised, Miller, SOLO, Dreyfus, and a combined Bloom+Miller scale; each level has a name, order, description and verb list.
- **Framework**: key, name, publisher, version label, licence note, profile (core / health / other), status. **FrameworkItem**: framework, code, title, description, parent (tree), depth, order, metadata JSON. **FrameworkCrossRef**: from item, to item, type. **Crosswalk** + **CrosswalkEntry**: from-framework-version, to-framework-version, entries of type equivalent / split / merged / removed / new.
- **TagList** (kind: teaching method, assessment method, theme, thread, keyword, resource, EPA, custom) + **TagValue**; **Tagging**: entity type, entity id, tag value, inherited_from (nullable).
- **MappingLink**: objective, framework item, coverage (0–5), depth match (below / matches / above), rationale, evidence quote, source (ai / human / import / migrated), confidence (0–1), status (suggested / accepted / rejected / needs_second_review), first reviewer, second reviewer, ai_run id.
- **AIRun**: type (mapping, extraction, rewrite, migration, qa, classification), provider, model, prompt version, parameters, input/output token counts, estimated cost, status, timings. Store prompts and responses for audit (no personal data ever present).
- **Assessment** (phase 3 full; phase 1 minimal): module, name, type (tag), weight, timing. **AssessmentItem**: assessment, label, marks, linked objectives.
- **User**, **RoleAssignment** (role, scope type, scope id, expires_at), **ApiToken**.
- **ImportJob**, **SyncJob**, **ConnectorConfig** (secrets encrypted at rest with a key from the environment), **ReviewAssignment**.
- **Embedding**: entity type, entity id, model name, vector, text hash (re-embed only when text changes).

## 7. Feature specification by phase

### Phase 0 — Foundations

- Monorepo scaffold, linting, formatting, pre-commit hooks, GitHub Actions CI.
- Docker Compose stack that starts with `docker compose up -d` after copying `.env.example` to `.env`; first-run setup wizard creates the first admin and institution.
- Auth: local accounts, password reset by email (SMTP config), OIDC sign-in; SAML can follow in phase 2 but leave the interface ready.
- Roles and scoped permissions enforced in the API (not only the UI), with tests.
- Core data model + migrations + audit log.
- Configurable terminology (e.g. "module" vs "course") and feature profiles (core, health sciences) stored in institution settings and used by the UI.
- i18n framework with English strings extracted (no hard-coded UI text).
- Fictional **demo dataset**: "BSc Health Sciences (Demo)" with 3 modules, ~20 learning events, ~60 objectives, a fictional "Demo Graduate Competencies" framework (8 items in 2 levels), Bloom and Miller scales, tag lists. Load it with one command.
- Documentation site skeleton: install, upgrade, backup/restore (pg_dump script), admin basics.
- Health check endpoints; structured logging.

**Definition of done (phase 0):** a fresh Linux server with Docker can be set up by following the install guide; CI is green; demo data loads; role permissions are covered by tests.

### Phase 1 — Core mapping (the MVP)

**Curriculum builder**
- Tree editor for programme → phases → modules → learning events, with drag-and-drop reorder, copy, and "copy academic year forward".
- Objective editor at each level with upward links; domain (K/S/A) and taxonomy level selectors.
- Tag lists managed by the curriculum office; tagging with inheritance preview.

**Objective quality checker** (runs as you type and in bulk)
- Flags vague verbs (e.g. understand, know, appreciate, be aware of, learn about), multiple verbs in one objective, missing domain, missing upward link, very long objectives.
- Suggests a taxonomy level from the verb using the scale's verb lists (rule-based first; AI optional).
- Finds near-duplicate objectives using embeddings (configurable similarity threshold).
- Optional AI rewrite suggestion into a measurable objective, shown as a diff the user can accept.

**Framework library**
- Published **framework pack** format: YAML or JSON validated by a JSON Schema in `/packs/schema`. Includes metadata, items tree, cross-references, optional crosswalks, optional taxonomy scales and tag lists.
- Import from pack file or from Excel template (code, title, description, parent code).
- Browse framework as a tree with search; see where each item is mapped.
- Templates (structure only, no copyrighted text) for: HPCSA core competencies, SAQA NQF level descriptors, a university graduate-attributes list, MeSH subset import. Ship the demo framework as a full example.

**Mapping workspace**
- Split view: objectives (filterable by module/phase) on the left, framework tree on the right, links in the middle. Manual linking by drag or search.
- Each link records coverage 0–5 and depth match, with short help text explaining the scale.
- **AI mapping run** (see section 8) for a selected scope; results land as `suggested` links.
- **Review queue**: sorted by confidence; shows objective, framework item, rationale and evidence quote; keyboard shortcuts (A accept, R reject, E edit, S skip, 2 send to second review); bulk accept above a chosen confidence; progress counter.
- Optional **four-eyes mode**: links need a second reviewer before they count as accepted; disagreements are flagged for discussion.

**Search**
- Global search across objectives, events, modules, framework items: keyword (full-text) plus meaning-based (embeddings), with filters for phase, module, format, tag lists, frameworks, taxonomy level.
- "Where do we teach X?" returns events, objectives and their schedule position.

**Reports** (each viewable on screen and exportable to Excel and PDF; every report states its method and date)
- **Coverage report**: per framework item and rolled up per group, using four labelled methods: single match (≥1 accepted link), multiple match (≥N links, N configurable, default 3), subordinate match (share of child items covered), and **weighted content coverage** (from coverage scores, reduced when depth is below target). Heatmap of framework groups × phases.
- **Gap report**: framework items with no or low coverage; objectives with no mapping.
- **Redundancy report**: items covered by unusually many events; near-duplicate objectives across modules.
- **Traceability report**: programme outcome → module outcomes → session objectives → mapped framework items.
- **Teaching formats and contact hours** by module, phase and programme.
- **Curriculum relationship report** (One45-style): each event → objectives → tags, one row each.
- **Role balance report**: share of teaching time and objectives per top-level framework group per phase (e.g. HPCSA roles).
- **NQF credit and notional hours check** (section 9).
- Basic **assessment methods coverage** from tags (full blueprints in phase 3).

**Imports and exports**
- Excel templates with dropdowns and data validation for programmes, modules, events, objectives, tags, frameworks and mappings.
- Import preview with row-level errors, dry-run mode, upsert by external ID, and an import job history.
- Full round-trip export of everything in the same templates; matrix export (objectives × framework items); JSON export of a whole curriculum version.

**Student and staff views**
- Read-only curriculum explorer by year/phase/module, mobile-friendly.
- Search, and "what is covered in this module/assessment".
- Only published curriculum versions are visible to students.

**Committee dashboard (basic)**
- Mapping progress (% objectives reviewed), coverage summary, top gaps, credit warnings.

**Definition of done (phase 1):** the demo programme can be fully mapped using AI suggestions and the review queue; all phase 1 reports render and export; the eval harness (section 8) runs against a fictional gold set and reports Cohen's kappa (target for the real pilot: kappa ≥ 0.6 between AI and human mappers); end-to-end tests cover build → map → review → report; documentation covers each role's main tasks.

### Phase 2 — Integrate and accredit (build after phase 1 is approved)

- **Brightspace connector** (section 10): pull structure, content, calendar and instructors; declared vs delivered report; optional push of outcomes and alignments; LTI 1.3 launch showing the module's map inside a course.
- **Schedule**: scheduled sessions with venue, group/section, facilitators; copy rows per group; curriculum calendar view; facilitator teaching-load report.
- **Declared vs delivered**: flag mapped sessions with no LMS evidence and LMS content with no place in the map; optional "taught as planned?" confirmation by facilitators.
- **Framework versioning and migration**: import a new framework version; build or import a crosswalk; AI proposes how existing links move (keep, move, split, drop); people confirm; before/after coverage comparison.
- **Evidence packs**: one-click export for HPCSA and CHE reviews (programme overview, outcomes, mapping and coverage, credits and workload, assessment alignment, change history), as PDF and Excel bundle.
- **MedBiquitous Curriculum Inventory** XML export (check the current standard before implementing).
- **SAML 2.0** SSO.
- **Committee dashboard** extended: trends across academic years, version diffs.
- **Network view**: Cytoscape graph clustering objectives and events by similarity and by shared framework items.

### Phase 3 — Assess and share

- Assessment blueprints: assessments and items linked to objectives; blueprint matrix (objectives/framework groups × assessments); alerts for objectives never assessed.
- Clinical placements and patient/case availability per site (health profile only).
- Aggregated learner outcome import (no individual data required): e.g. item difficulty per objective to inform curriculum review.
- Community **framework pack registry** (a separate GitHub repo with pack validation in CI) and optional anonymised benchmarking export.
- Connectors for Moodle, Canvas and Blackboard behind the same connector interface.
- More UI languages (e.g. Afrikaans, isiZulu, isiXhosa) via community translation.
- Helm chart for Kubernetes.

## 8. AI subsystem specification

**Provider abstraction**
- Interface `LLMProvider` with `generate_structured(messages, json_schema, **options)` and `EmbeddingProvider` with `embed(texts)`.
- Adapters: Anthropic Claude; OpenAI-compatible (covers OpenAI, Azure OpenAI and many hosted models); Ollama and vLLM for local models; a `NullProvider` (AI disabled — the whole platform must work without AI).
- Default embeddings: a small open multilingual sentence-embedding model run in an optional `embeddings` container; configurable to use a provider instead.
- Admins configure provider, model, API key (encrypted), temperature, monthly budget cap and per-run limits in the admin UI. Test-connection button.

**Privacy guard (mandatory)**
- AI calls are built only from curriculum entities (objective text, framework items, module/event titles and descriptions, uploaded study-guide text).
- A redaction step removes anything resembling personal information (emails, phone numbers, ID/student numbers, names from the user table) before any call, with tests.
- Admin setting to restrict AI to local providers only.

**Mapping pipeline**
1. Embed objectives and framework items (cache by text hash).
2. For each objective, shortlist top-k framework items (default k=10) by hybrid score (vector similarity + full-text rank + boost for items linked to similar, previously accepted objectives). Respect cross-references when shortlisting.
3. Send the objective and shortlist to the LLM with a versioned prompt; require JSON output per candidate: `is_match`, `coverage_0_to_5`, `depth_match`, `confidence`, `rationale` (one sentence), `evidence_quote` (exact words from the objective). Validate against the schema; retry once on invalid output; log failures.
4. Save as `suggested` MappingLinks with the AIRun id.
5. Accepted and rejected decisions become few-shot examples for that institution (selected by similarity) in later runs.

**Other AI tasks** (each a separate versioned prompt in `backend/app/ai/prompts/`, with JSON output schemas)
- Extract objectives from uploaded PDF/DOCX study guides into draft objectives for review.
- Rewrite an objective to be measurable; classify domain and taxonomy level.
- Framework migration proposals (phase 2).
- Plain-language Q&A over the curriculum ("Where do we teach ECG interpretation?") using retrieval over the institution's data, answering with links to records only.
- Plain-language gap explanations for reports.

**Quality and cost**
- **Eval harness** (`scripts/eval_mapping.py` + admin UI page): compares AI suggestions with a human-mapped gold set; reports precision, recall and Cohen's kappa, per prompt version and model. Ship a fictional gold set for the demo data.
- Batch and cache calls; track tokens and estimated cost per run; stop at budget caps with a clear message.
- Never auto-accept AI links unless an admin explicitly enables a confidence threshold for bulk accept, and even then mark them as AI-accepted in reports.

## 9. South African requirements

- **Qualification types (HEQSF)** seeded as an editable configuration table (not hard-coded), with NQF exit level and minimum total credits. Seed values for the institution to verify: Higher Certificate (NQF 5, 120), Advanced Certificate (NQF 6, 120), Diploma (NQF 6, 240 or 360), Advanced Diploma (NQF 7, 120), Bachelor's (NQF 7, 360), Bachelor's professional (NQF 8, 480), Postgraduate Diploma (NQF 8, 120), Honours (NQF 8, 120), Master's (NQF 9, 180), Doctoral (NQF 10, 360). Show a notice that values must be checked against the current CHE/HEQSF documents.
- **Credits and notional hours**: 1 credit = 10 notional hours (configurable). For each module, notional hours = contact time from learning events + estimated self-study + assessment time. Compare with declared credits; flag over/under beyond a configurable tolerance (default ±10%). Year view of total credits (typical 120 per year, configurable). Check credits per NQF level against the qualification type rules.
- **Programme fields**: SAQA qualification ID, NQF exit level, qualification type, CHE accreditation status and dates, HPCSA (or other council) accreditation status and dates.
- **HPCSA core competencies**: provide an import template only. Health profile includes a role-balance report and an evidence pack layout aimed at professional board reviews. Other councils (e.g. nursing, pharmacy) are additional packs, loaded the same way.
- **POPIA**:
  - Data inventory document in `/docs/privacy/` listing every personal data field, purpose and retention.
  - Privacy notice template; per-user data export and deletion (with audit-safe anonymisation of authorship).
  - Configurable retention for audit logs and AI logs.
  - Access log for personal data views by admins.
  - Self-hosted by default; AI privacy guard (section 8); admin warning when a cloud AI provider outside South Africa is configured, explaining that curriculum text (not personal data) will be sent.
- Works on modest hardware (target: runs on a 4 vCPU / 8 GB RAM server without local LLM) and slow connections (paginate, lazy-load, compress, no huge bundles).

## 10. Integrations specification

**CSV/Excel (phase 1)** — see the imports section above. Excel templates live in `/packs/templates/` and are generated from the same field definitions used for validation, so they never drift.

**Brightspace (phase 2)** — consult the official D2L developer documentation (docs.valence.desire2learn.com) for current API versions and routes before coding.
- Auth: OAuth 2.0 app registered by the institution's Brightspace admin; tokens stored encrypted; least-privilege scopes listed in the admin guide.
- Pull: org structure/course offerings → modules; content modules and topics → learning events; calendar events → scheduled sessions; instructors → facilitators (store only names and LMS user IDs needed for display).
- Learning Outcomes API: optional push of programme/module outcomes and alignments; optional pull of existing outcome sets as a framework.
- LTI 1.3 Advantage (use a maintained library such as PyLTI1p3): resource-link launch opening the module's map; Names and Role Provisioning for role mapping; deep linking to embed a session's objectives in course content. Admin guide must explain the registration values the LMS admin enters.
- Connector interface (`BaseConnector`: `test_connection`, `pull_structure`, `pull_content`, `pull_schedule`, `push_outcomes`) so Moodle/Canvas/Blackboard can be added later.
- Sync runs as background jobs with a diff preview before applying changes; full sync history.

**Public API** — documented REST API (OpenAPI), personal API tokens with scopes, and webhooks for key events (version published, mapping accepted, import completed).

## 11. UX and accessibility

- WCAG 2.2 AA: keyboard navigation everywhere, visible focus, sufficient contrast, screen-reader labels, no information by colour alone.
- Plain language, short labels, contextual help ("?") explaining terms like coverage and depth.
- Main navigation: Dashboard · Curriculum · Mapping · Frameworks · Reports · Search · Admin. Students see Explorer · Search only.
- Lead with organisational views (what, when, who) for students and lecturers, per LOOOP user research.
- Light and dark themes; responsive down to phone width.

## 12. Security

- OWASP ASVS level 2 as the target. Rate limiting on auth; secure headers via Caddy; CSRF; strict CORS; parameterised queries only.
- Secrets encrypted at rest (connector credentials, AI keys) using a key from the environment.
- Dependency scanning (Dependabot, CodeQL); `SECURITY.md` with a disclosure process.
- Backups: documented `pg_dump` schedule and restore test.

## 13. Testing and quality

- Backend: pytest with factories; ≥80% coverage for services, permissions and reports.
- Frontend: Vitest + Testing Library for components; Playwright end-to-end for key journeys (login, build curriculum, import Excel, AI map with mocked provider, review queue, coverage report, student explorer).
- AI: provider mocked with recorded fixtures in tests; eval harness for real runs.
- Every report has a test with a small known dataset and expected numbers.

## 14. Documentation and community

- `README.md` (what it is, screenshots, quick start), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue and PR templates.
- MkDocs site: install, upgrade, backup/restore, SSO setup, AI provider setup, Brightspace setup, framework pack specification, user guides per role, glossary, FAQ.
- ADRs for every major decision in `docs/adr/`.
- `docs/PROGRESS.md` updated after every slice.

---

## Phase 2 prompt (paste when Phase 1 is approved)

> Re-read `docs/PROJECT_BRIEF.md`, `CLAUDE.md` and `docs/PROGRESS.md`. Phase 1 is complete and approved. Plan **Phase 2** as small vertical slices, starting with the Brightspace connector behind the `BaseConnector` interface. First check the current D2L Brightspace API and LTI 1.3 documentation and list the exact routes, scopes and registration values you will use, with links, for me to confirm. Ask me any open questions, wait for approval, then build slice by slice with tests, docs and commits as before.

## Phase 3 prompt (paste when Phase 2 is approved)

> Re-read `docs/PROJECT_BRIEF.md`, `CLAUDE.md` and `docs/PROGRESS.md`. Phase 2 is complete and approved. Plan **Phase 3**, starting with assessment blueprints. Propose the slices, ask open questions, wait for approval, then build with tests, docs and commits as before.

## Useful follow-up prompts

- "Run the full test suite and linters, then list anything failing and fix it."
- "Review the codebase against section 8's privacy guard. Show me every place data is sent to an AI provider and prove no personal data can reach it."
- "Walk me through installing this on a fresh Ubuntu server as if I were a university IT technician, and fix any step in the docs that is unclear."
- "Generate a short demo script for showing the platform to a programme committee, using the demo data."
