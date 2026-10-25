# OCMP Documentation

The **Open Curriculum Mapping Platform (OCMP)** is an open-source, self-hosted curriculum
mapping platform for universities. It holds the structure of a programme (phases, modules,
learning events and objectives), maps objectives to competency frameworks and taxonomies,
and reports on coverage, gaps and workload.

!!! note "Project status"
    OCMP is in **Phase 0 (foundations)**: installation, sign-in, roles and permissions, the
    data model, the audit log and a demo dataset are in place. Curriculum editing, mapping
    and reports arrive in Phase 1. Some tasks described here are done through the API or
    the command line until their admin screens exist.

## Where to start

| You want to... | Read |
|---|---|
| Install OCMP on a server | [Install](operations/install.md) |
| Look up a setting in `.env` | [Configuration](operations/configuration.md) |
| Move to a newer version | [Upgrade](operations/upgrade.md) |
| Protect and recover the data | [Backup and restore](operations/backup-restore.md) |
| Run the platform after installation | [Admin basics](admin/basics.md) |
| Give people access | [Users and roles](admin/users-and-roles.md) |
| Let people sign in with the university account | [Single sign-on](admin/sso.md) |
| Meet POPIA obligations | [Personal data inventory](privacy/data-inventory.md), [privacy notice template](privacy/privacy-notice-template.md) |
| Understand why it is built this way | [Architecture decisions](adr/index.md) |

## How OCMP runs

OCMP runs as a set of Docker containers on one server, started with Docker Compose:

| Service | Purpose |
|---|---|
| `caddy` | HTTPS (automatic certificates), the only service reachable from outside |
| `web` | The web application (static files) |
| `api` | The REST API, under `/api/v1/` |
| `worker` | Background jobs, such as sending email |
| `migrate` | Runs once on every start to update the database schema, then exits |
| `db` | PostgreSQL 16 with pgvector: all curriculum, framework and account data |
| `redis` | Sign-in sessions, rate limits and the job queue |

The interactive API reference is served by every installation at `/api/docs`.

## Data and privacy

OCMP is self-hosted: all data stays on the institution's server. The demo dataset and the
demo framework are fictional. Personal data (names, email addresses) is never sent to AI
providers. The [personal data inventory](privacy/data-inventory.md) lists everything OCMP
stores about people.
