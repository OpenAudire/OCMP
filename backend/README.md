# OCMP Backend

FastAPI backend for the Open Curriculum Mapping Platform.

## Development Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Unix/macOS:
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check .
mypy app

# Run tests
pytest

# Run development server
uvicorn app.main:app --reload
```

## Project Structure

```
app/
├── api/          # FastAPI routers
├── core/         # Config, security, database
├── models/       # SQLAlchemy models
├── schemas/      # Pydantic schemas
├── services/     # Business logic
├── ai/           # AI providers and prompts
└── connectors/   # LMS connectors
migrations/       # Alembic migrations
tests/            # Test suite
```
