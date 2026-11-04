"""intended repeats

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-04 14:00:00.000000

Slice 1.24a, ADR 053. Framework items a programme teaches in many sessions on purpose (a spiral
curriculum); the report on items taught in many sessions leaves them out.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "intended_repeats",
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("framework_item_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_intended_repeats_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["framework_item_id"],
            ["framework_items.id"],
            name=op.f("fk_intended_repeats_framework_item_id_framework_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["programmes.id"],
            name=op.f("fk_intended_repeats_programme_id_programmes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intended_repeats")),
    )
    op.create_index(
        op.f("ix_intended_repeats_created_by_id"),
        "intended_repeats",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intended_repeats_deleted_at"), "intended_repeats", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_intended_repeats_framework_item_id"),
        "intended_repeats",
        ["framework_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intended_repeats_programme_id"),
        "intended_repeats",
        ["programme_id"],
        unique=False,
    )
    op.create_index(
        "uq_intended_repeats_item_live",
        "intended_repeats",
        ["programme_id", "framework_item_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("uq_intended_repeats_item_live", table_name="intended_repeats")
    op.drop_index(op.f("ix_intended_repeats_programme_id"), table_name="intended_repeats")
    op.drop_index(op.f("ix_intended_repeats_framework_item_id"), table_name="intended_repeats")
    op.drop_index(op.f("ix_intended_repeats_deleted_at"), table_name="intended_repeats")
    op.drop_index(op.f("ix_intended_repeats_created_by_id"), table_name="intended_repeats")
    op.drop_table("intended_repeats")
