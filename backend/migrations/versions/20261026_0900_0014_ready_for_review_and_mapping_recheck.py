"""add ready for review objective status and mapping needs_recheck flag

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = op.f("ck_objectives_objective_status")


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "mapping_links",
        sa.Column("needs_recheck", sa.Boolean(), server_default="false", nullable=False),
    )
    op.drop_constraint(CHECK, "objectives", type_="check")
    op.create_check_constraint(
        CHECK, "objectives", "status IN ('draft', 'ready_for_review', 'approved', 'retired')"
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Objectives waiting for review go back to draft, the only earlier status they fit.
    op.execute("UPDATE objectives SET status = 'draft' WHERE status = 'ready_for_review'")
    op.drop_constraint(CHECK, "objectives", type_="check")
    op.create_check_constraint(CHECK, "objectives", "status IN ('draft', 'approved', 'retired')")
    op.drop_column("mapping_links", "needs_recheck")
