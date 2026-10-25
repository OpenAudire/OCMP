# Curriculum in Context

An open-source, self-hosted curriculum mapping platform for universities.

## Features

- **Curriculum Structure**: Programme → Phase → Module → Learning Event → Objective
- **Framework Mapping**: Map objectives to competency frameworks, taxonomies, and vocabularies
- **AI-Assisted Mapping**: Draft mappings with AI, review and accept in a fast keyboard-driven queue
- **Coverage Analysis**: Identify gaps, redundancies, and workload issues
- **Reports**: Coverage, gaps, traceability, teaching formats, and accreditation evidence
- **LMS Integration**: Sync with Brightspace (Phase 2)
- **Student & Staff Views**: Searchable curriculum explorer

## Quick Start

You need a Linux server with Docker Engine and the Compose plugin. The
[install guide](https://openaudire.github.io/OCMP/operations/install/) covers every step,
including DNS, certificates, email and backups.

```bash
git clone https://github.com/OpenAudire/OCMP.git
cd OCMP/deploy
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
# set DOMAIN (and SMTP_*) in .env, then:
docker compose up -d --build --wait

# Show the setup token, then open https://<DOMAIN>/setup
docker compose exec api python -m app.cli setup-token
```

## Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

## Documentation

The documentation site is at **[openaudire.github.io/OCMP](https://openaudire.github.io/OCMP/)**
(source in [`docs/`](docs/)):

- [Install](docs/operations/install.md), [Upgrade](docs/operations/upgrade.md),
  [Backup and restore](docs/operations/backup-restore.md)
- [Admin basics](docs/admin/basics.md), [Users and roles](docs/admin/users-and-roles.md),
  [Single sign-on](docs/admin/sso.md)
- [Architecture decisions](docs/adr/index.md)
- API reference: `/api/docs` on every installation

Build the site locally:

```bash
python -m venv .venv-docs
.venv-docs/bin/pip install -r docs/requirements.txt   # Windows: .venv-docs\Scripts\pip
.venv-docs/bin/mkdocs serve
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and how to report vulnerabilities.

## License

Apache-2.0. See [LICENSE](LICENSE) for details.

## Acknowledgments

Curriculum in Context is inspired by LOOOP (Charité Berlin) and One45 Curriculum (Acuity Insights), built to address gaps identified in curriculum mapping research.
