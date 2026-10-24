"""enable postgres extensions

Revision ID: 0001
Revises:
Create Date: 2026-10-24 21:59:44.212166
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # pgvector stores embeddings for semantic search and AI mapping shortlists.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade database schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
