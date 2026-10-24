# Open Curriculum Mapping Platform (OCMP)

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

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/ocmp.git
cd ocmp

# Copy environment template
cp deploy/.env.example deploy/.env

# Edit .env with your settings
# At minimum, set SECRET_KEY to a random string

# Start the stack
cd deploy
docker compose up -d

# Open http://localhost in your browser
# Complete the first-run setup wizard
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

Full documentation is available at [docs site URL].

- [Installation Guide](docs/install.md)
- [User Guides](docs/user-guides/)
- [API Reference](/api/docs)
- [Architecture Decisions](docs/adr/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and how to report vulnerabilities.

## License

Apache-2.0. See [LICENSE](LICENSE) for details.

## Acknowledgments

OCMP is inspired by LOOOP (Charité Berlin) and One45 Curriculum (Acuity Insights), built to address gaps identified in curriculum mapping research.
