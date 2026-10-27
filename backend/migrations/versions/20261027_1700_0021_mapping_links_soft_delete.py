"""soft-delete for mapping links (they go with their objective)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-27 17:00:00.000000

Slice 1.14b, ADR 043. Adds ``deleted_at`` and makes the one-link-per-pair rule apply to
live rows only, so a deleted link never blocks a new one. Existing links stay as they are;
links of already deleted objectives are cleaned up with the audited CLI command
``clean-orphan-links``, not here (a migration would bypass the audit log).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mapping_links", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index(op.f("ix_mapping_links_deleted_at"), "mapping_links", ["deleted_at"])
    op.drop_constraint(
        "uq_mapping_links_objective_id_framework_item_id", "mapping_links", type_="unique"
    )
    op.create_index(
        "uq_mapping_links_objective_item_live",
        "mapping_links",
        ["objective_id", "framework_item_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Deleted rows would collide with live ones in the full unique constraint: drop them.
    op.execute("DELETE FROM mapping_links WHERE deleted_at IS NOT NULL")
    op.drop_index("uq_mapping_links_objective_item_live", table_name="mapping_links")
    op.create_unique_constraint(
        "uq_mapping_links_objective_id_framework_item_id",
        "mapping_links",
        ["objective_id", "framework_item_id"],
    )
    op.drop_index(op.f("ix_mapping_links_deleted_at"), table_name="mapping_links")
    op.drop_column("mapping_links", "deleted_at")
