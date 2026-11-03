"""when an objective's wording last changed

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-04 09:00:00.000000

Slice 1.16b, ADR 045. A link a reviewer rejected is not asked about again by an AI run, unless the
objective's wording changed after the rejection. This column says when the wording last changed
(null: never since it was made). Additive; nothing is rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "objectives", sa.Column("text_changed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("objectives", "text_changed_at")
