# Contributing to OCMP

Thank you for considering contributing to the Open Curriculum Mapping Platform!

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include steps to reproduce, expected behavior, and actual behavior
4. Include your environment (OS, Docker version, browser)

### Suggesting Features

1. Check existing issues and the project roadmap
2. Use the feature request template
3. Explain the use case and why it would benefit users

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes following our conventions
4. Add tests for new functionality
5. Ensure all tests pass (`pytest` for backend, `npm test` for frontend)
6. Ensure linting passes (`ruff check .` for backend, `npm run lint` for frontend)
7. Submit a pull request using the template

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add coverage report export
fix: correct credit calculation
docs: update installation guide
test: add permission tests
refactor: extract mapping service
chore: update dependencies
```

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Docker and Docker Compose
- PostgreSQL 16 (or use Docker)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Unix/macOS:
source .venv/bin/activate

# Install all dependencies including dev tools
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

**Important:** Always work inside the virtual environment. Never install packages globally.

### Frontend

```bash
cd frontend
npm install
```

### Running Linters

```bash
# Backend (from backend/ with venv activated)
ruff check .           # Check for issues
ruff format --check .  # Check formatting
mypy app               # Type checking

# Frontend (from frontend/)
npm run lint           # ESLint
npm run typecheck      # TypeScript
```

### Running Tests

```bash
# Backend (from backend/ with venv activated)
pytest                 # Run all tests with coverage
pytest tests/ -v       # Verbose output
pytest -x              # Stop on first failure

# Frontend (from frontend/)
npm run test           # Run tests once
npm run test:watch     # Watch mode
npm run test:coverage  # With coverage
```

### Documentation

The documentation site uses MkDocs Material (`mkdocs.yml`, pages in `docs/`). Install it
in its own virtual environment and check your changes with a strict build, as CI does:

```bash
python -m venv .venv-docs
.venv-docs/bin/pip install -r docs/requirements.txt   # Windows: .venv-docs\Scripts\pip
.venv-docs/bin/mkdocs serve            # preview at http://127.0.0.1:8000
.venv-docs/bin/mkdocs build --strict   # fails on broken links
```

Update the operator and admin guides in the same pull request as the change they
describe.

### Line Endings

This project uses LF line endings (Unix-style). The `.gitattributes` file ensures consistent line endings across all platforms. If you're on Windows, Git will handle the conversion automatically.

## Code Style

### Python

- Follow PEP 8 (enforced by ruff)
- Use type hints
- Use async/await for I/O operations
- Write docstrings for public functions

### TypeScript

- Use strict TypeScript
- Use functional React components
- Use translation keys for all UI text

## Questions?

Open a discussion or reach out to the maintainers.
