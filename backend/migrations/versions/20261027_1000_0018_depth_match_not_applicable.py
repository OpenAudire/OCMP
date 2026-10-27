"""allow depth match "not_applicable" on mapping links

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = op.f("ck_mapping_links_depth_match")


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_constraint(CHECK, "mapping_links", type_="check")
    op.create_check_constraint(
        CHECK,
        "mapping_links",
        "depth_match IN ('below', 'matches', 'above', 'not_applicable')",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # The earlier scale has no such value; the depth becomes "not judged" (null).
    op.execute("UPDATE mapping_links SET depth_match = NULL WHERE depth_match = 'not_applicable'")
    op.drop_constraint(CHECK, "mapping_links", type_="check")
    op.create_check_constraint(
        CHECK, "mapping_links", "depth_match IN ('below', 'matches', 'above')"
    )
