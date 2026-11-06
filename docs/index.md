# Curriculum in Context Documentation

**Curriculum in Context** is an open-source, self-hosted curriculum
mapping platform for universities. It holds the structure of a programme (phases, modules,
learning events and objectives), maps objectives to competency frameworks and taxonomies,
and reports on coverage, gaps and workload.

!!! note "Project status"
    Curriculum in Context is at the end of **Phase 1 (core mapping)**: the curriculum builder, framework
    library, mapping workspace with AI suggestions and a review queue, search, coverage and other reports with
    Excel and PDF export, Excel import and export, the committee dashboard, the student explorer and the
    administration screens are built, and wait for the product owner's Phase 1 review. Connectors to learning
    systems, accreditation evidence packs and full assessment blueprints belong to later phases.

## Where to start

| You want to... | Read |
|---|---|
| Learn what your role does | [Guides by role](guides/index.md), [glossary](guides/glossary.md), [FAQ](guides/faq.md) |
| Install Curriculum in Context on a server | [Install](operations/install.md) |
| Look up a setting in `.env` | [Configuration](operations/configuration.md) |
| Move to a newer version | [Upgrade](operations/upgrade.md) |
| Protect and recover the data | [Backup and restore](operations/backup-restore.md) |
| Run the platform after installation | [Admin basics](admin/basics.md) |
| Give people access | [Users and roles](admin/users-and-roles.md) |
| Switch on AI suggestions | [Setting up an AI provider](admin/ai-setup.md) |
| Let people sign in with the university account | [Single sign-on](admin/sso.md) |
| Meet POPIA obligations | [Personal data inventory](privacy/data-inventory.md), [privacy notice template](privacy/privacy-notice-template.md) |
| Understand why it is built this way | [Architecture decisions](adr/index.md) |

## How Curriculum in Context runs

Curriculum in Context runs as a set of Docker containers on one server, started with Docker Compose:

| Service | Purpose |
|---|---|
| `caddy` | HTTPS (automatic certificates), the only service reachable from outside |
| `web` | The web application (static files) |
| `api` | The REST API, under `/api/v1/` |
| `worker` | Background jobs, such as sending email and AI mapping runs |
| `scheduler` | Records the dashboard's daily figures at 23:55 South African time |
| `migrate` | Runs once on every start to update the database schema, then exits |
| `db` | PostgreSQL 16 with pgvector: all curriculum, framework and account data |
| `redis` | Sign-in sessions, rate limits and the job queue |

The interactive API reference is served by every installation at `/api/docs`.

## Data and privacy

Curriculum in Context is self-hosted: all data stays on the institution's server. The demo dataset and the
demo framework are fictional. Personal data (names, email addresses) is never sent to AI
providers. The [personal data inventory](privacy/data-inventory.md) lists everything Curriculum in Context
stores about people.
