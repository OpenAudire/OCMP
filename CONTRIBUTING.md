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
- Node.js 20+
- Docker and Docker Compose
- PostgreSQL 16 (or use Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Frontend

```bash
cd frontend
npm install
```

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

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
