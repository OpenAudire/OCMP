# ADR 025: Product Name "Curriculum in Context"

## Status

Accepted (2026-10-25, Phase 1 plan decision 6; implemented in Slice 1.1)

## Context

Phase 0 used the working name "Open Curriculum Mapping Platform (OCMP)". The approved
Phase 1 mockups use the product name **Curriculum in Context**, with a two-tone wordmark
("Curriculum" / "in Context"). Renaming code identifiers would touch the repository,
Python package, CLI, images, compose project, Redis keys, cookies and database defaults,
all of which existing installations and scripts depend on.

## Decision

- People see **Curriculum in Context** everywhere: the UI (wordmark in the sidebar and on
  the sign-in pages, page title, translations), the documentation site and README, email
  sender name and subjects (`APP_NAME` and `SMTP_FROM_NAME` defaults), the OpenAPI title,
  the demo data and the framework pack schema title. No acronym is used.
- Technical identifiers stay `ocmp`: the repository (`OpenAudire/OCMP`), the `app` Python
  package and `python -m app.cli`, image names (`ocmp-backend`, `ocmp-web`), the compose
  project, `OCMP_*` environment variables, Redis key prefixes, cookie names and database
  defaults. Nothing changes for existing installations except the visible name.
- The product name is a translation key (`app.title`, `app.wordmarkFirst`,
  `app.wordmarkSecond`) like all UI text; it is not translated in English.
- ADRs 001-024 keep "OCMP" as written: they are records of decisions at the time.

## Consequences

- Installations that set `SMTP_FROM_NAME=OCMP` explicitly keep that sender name until the
  operator changes it.
- The demo institution created by `load-demo` is now "Demo University" (was "OCMP Demo
  University"); existing demo installations keep their name.
- Code comments and docstrings that mention "OCMP" refer to the codebase and are changed
  only when touched.
