# ADR 023: Dependency Scanning, Release Images and Privacy Records

## Status

Accepted

## Context

The brief lists for Phase 0 or its CI/CD and security sections: Dependabot and CodeQL
(sections 5 and 12), images built and pushed to GitHub Container Registry on tagged
releases (section 5), and under POPIA a data inventory in `docs/privacy/` and a privacy
notice template (section 9). None existed at the end of Slice 0.20. The compose file also
named an embeddings image (`ghcr.io/ocmp/embeddings`) that does not exist. Checked on
2026-10-25: the repository is private and code scanning is not enabled for it; current
action majors are `github/codeql-action@v4`, `docker/metadata-action@v6`,
`docker/login-action@v4`, `actions/upload-artifact@v7`.

## Decision

### Dependabot (`.github/dependabot.yml`)
- Weekly version updates for backend and docs pip, frontend npm, the two Dockerfiles, the
  compose file and GitHub Actions; minor and patch updates grouped per ecosystem.
  Security updates follow advisories as they appear (enabled in repository settings).
- Existing workflows keep their action versions; Dependabot raises the upgrades as
  reviewable pull requests rather than this change bumping them untested.

### CodeQL (`.github/workflows/codeql.yml`)
- Python, JavaScript/TypeScript and Actions, `security-extended` queries, on pushes and
  pull requests to `main` and weekly.
- Code scanning (the Security tab) needs GitHub Code Security on a private repository, so
  the workflow does not depend on it: results are written as SARIF, kept as an artifact,
  and the job **fails on any error or warning**, listing them in the log. Setting the
  repository variable `CODE_SCANNING_ENABLED=true` also uploads them to code scanning
  once it is available (for example when the repository becomes public).
- The Actions analysis is held to the same rule. Its first run found 14 warnings, all
  fixed rather than suppressed: every workflow sets an explicit, minimal `permissions`
  block, and third-party actions are pinned to a commit SHA with the version in a comment
  (`uses: docker/login-action@<sha> # v4.7.0`), which Dependabot keeps up to date.
  GitHub's own `actions/*` and `github/*` actions keep version tags.

### Release images (`.github/workflows/release.yml`)
- A `vX.Y.Z` tag runs the full CI workflow (now callable with `workflow_call`) and, only
  if it passes, pushes `ghcr.io/openaudire/ocmp-backend` and `ocmp-web` tagged with the
  version, `X.Y`, `latest` and the commit sha. Pre-releases get only their own tags.
- Running the workflow by hand builds both images without logging in or pushing (dry run).
- Compose reads `OCMP_BACKEND_IMAGE` and `OCMP_WEB_IMAGE` (default: the local build), so
  servers can `docker compose pull` released images instead of building.
- Images are `linux/amd64` only for now.

### Embeddings profile
- **Kept as an optional profile, off by default; no image is built yet.** Nothing uses
  embeddings before Phase 1, and the serving approach in ADR 007 is to be built and
  tested with the search features. The image name now points at where it will be
  published (`ghcr.io/openaudire/ocmp-embeddings`, overridable with
  `OCMP_EMBEDDINGS_IMAGE`), the compose comment says it is not available, and
  `EMBEDDINGS_LOCAL` defaults to `false` so nothing expects the service.

### Privacy records
- `docs/privacy/data-inventory.md` lists every personal data field in the database, Redis,
  logs, backups and outbound flows, with purpose, source and retention, and how data
  subject rights are met today. It is updated with any change to personal data.
- `docs/privacy/privacy-notice-template.md` follows the POPIA section 18 contents for the
  institution to complete; both are marked as not legal advice.
- Container logs are rotated (5 x 10 MB per service), because Docker's default keeps logs,
  including client IP addresses in Caddy's access log, without limit.

## Consequences

- CodeQL findings now block merges just like test failures; false positives are dismissed
  in code with a justification, not by weakening the query suite.
- The first release needs a `v0.x.y` tag; GHCR packages of a private repository are
  private, so servers need `docker login ghcr.io` with a `read:packages` token.
- Per-user data export and deletion (brief section 9) remain Phase 1 work; the inventory
  records the current, partial state.
