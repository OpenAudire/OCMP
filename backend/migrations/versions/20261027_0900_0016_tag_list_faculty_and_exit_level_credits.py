"""add a faculty to tag lists and exit-level credits to qualification types

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Null: an institution-wide list (managed at the instance); else a faculty's own list.
    op.add_column("tag_lists", sa.Column("faculty_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tag_lists_faculty_id_faculties"),
        "tag_lists",
        "faculties",
        ["faculty_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_tag_lists_faculty_id"), "tag_lists", ["faculty_id"])
    op.add_column(
        "qualification_types", sa.Column("min_exit_level_credits", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_qualification_types_min_exit_level_credits_positive"),
        "qualification_types",
        "min_exit_level_credits IS NULL OR min_exit_level_credits >= 0",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_constraint(
        op.f("ck_qualification_types_min_exit_level_credits_positive"),
        "qualification_types",
        type_="check",
    )
    op.drop_column("qualification_types", "min_exit_level_credits")
    op.drop_index(op.f("ix_tag_lists_faculty_id"), table_name="tag_lists")
    op.drop_constraint(op.f("fk_tag_lists_faculty_id_faculties"), "tag_lists", type_="foreignkey")
    op.drop_column("tag_lists", "faculty_id")
