# Architecture decisions

Architecture decision records (ADRs) explain why OCMP is built the way it is. Each
records the context, the decision and its consequences. New major decisions get a new
ADR; an ADR that no longer holds is revised or superseded, not deleted.

| ADR | Decision |
|---|---|
| [001](001-background-job-library.md) | Background Job Library |
| [002](002-frontend-component-library.md) | Frontend Component Library |
| [003](003-authentication-strategy.md) | Authentication Strategy |
| [004](004-database-migrations.md) | Database Migrations |
| [005](005-api-versioning.md) | API Versioning |
| [006](006-testing-strategy.md) | Testing Strategy |
| [007](007-embedding-model.md) | Embedding Model (superseded by 044) |
| [008](008-core-data-model-conventions.md) | Core Data Model Conventions |
| [009](009-session-and-csrf-implementation.md) | Session, CSRF and Sign-in Rate Limiting Implementation |
| [010](010-password-reset.md) | Password Reset by Email |
| [011](011-oidc-sign-in.md) | Sign-in with OpenID Connect |
| [012](012-roles-and-permissions.md) | Roles and Scoped Permissions |
| [013](013-curriculum-data-model.md) | Curriculum Data Model |
| [014](014-framework-data-model.md) | Framework and Taxonomy Data Model |
| [015](015-tag-lists-and-tagging.md) | Tag Lists and Tagging |
| [016](016-mapping-data-model.md) | Mapping, AI Run and Review Data Model |
| [017](017-audit-log.md) | Audit Log |
| [018](018-terminology-and-profiles.md) | Terminology and Feature Profiles |
| [019](019-frontend-architecture.md) | Frontend Architecture |
| [020](020-first-run-setup.md) | First-Run Setup |
| [021](021-demo-dataset-and-pack-import.md) | Demo Dataset and Framework Pack Import |
| [022](022-documentation-and-backups.md) | Documentation Site and Backups |
| [023](023-supply-chain-releases-and-privacy-records.md) | Dependency Scanning, Release Images and Privacy Records |
| [024](024-licence.md) | Licence |
| [025](025-product-name.md) | Product Name "Curriculum in Context" |
| [026](026-visual-design-and-theming.md) | Visual Design, Theming and Accessibility Checks |
| [027](027-curriculum-read-access.md) | Curriculum Read API and Who Sees What |
| [028](028-curriculum-structure-editing.md) | Curriculum Structure Editing |
| [029](029-reorder-and-copy.md) | Reordering and Copying Curriculum Items |
| [030](030-curriculum-versions.md) | Curriculum Versions: Publishing, Copy Forward and Diff |
| [031](031-objective-editing.md) | Objective Editing: Permissions, Upward Links and Taxonomy Levels |
| [032](032-review-fixes-slices-1-3-to-1-6.md) | Review Fixes to Slices 1.3 to 1.6: Outcome Sight, Approval, Unpublish Reason, Mapping Re-check |
| [033](033-objective-quality-checker.md) | Objective Quality Checker and Taxonomy Level Suggestion (Rule Based) |
| [034](034-tag-lists-and-tagging-ui.md) | Managing Tag Lists, Tagging Items and Inheritance |
| [035](035-assessments-and-credit-check.md) | Minimal Assessments and the Credits and Notional Hours Check |
| [036](036-framework-pack-import.md) | Framework Pack Import from the Screen, Pack Format Version 2 and Templates |
| [037](037-cleanup-deletes-and-end-to-end-hygiene.md) | Deleting Unused Frameworks and Accounts, and End-to-End Hygiene |
| [038](038-framework-library-and-browser.md) | Framework Library, Tree Browser and "Where Mapped" |
| [039](039-mapping-workspace.md) | The Mapping Workspace, the Coverage Scale and Depth |
| [040](040-review-queue.md) | The Review Queue, Second Review and Bulk Accept |
| [041](041-encrypted-secrets-at-rest.md) | Encrypted Secrets at Rest and Key Rotation |
| [042](042-ai-provider-layer-and-privacy-guard.md) | AI Provider Layer, Privacy Guard, Budgets and Local-only Mode |
| [043](043-mapping-links-go-with-their-objective.md) | Mapping Links Go With Their Objective |
| [044](044-embeddings-model-server-and-cache.md) | Embeddings: Model, Server, Cache and Near-duplicate Detection |
| [045](045-ai-mapping-pipeline.md) | The AI Mapping Pipeline |
