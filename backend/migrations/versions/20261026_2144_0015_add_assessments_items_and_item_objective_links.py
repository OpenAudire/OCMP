"""add assessments, items and the objectives they assess

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26 21:44:03.818371
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "assessments",
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("method_value_id", sa.Uuid(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("timing", sa.String(length=128), server_default="", nullable=False),
        sa.Column("time_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("based_on_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_assessments_name_not_blank")),
        sa.CheckConstraint("time_minutes >= 0", name=op.f("ck_assessments_time_minutes_positive")),
        sa.CheckConstraint(
            "weight IS NULL OR weight BETWEEN 0 AND 100", name=op.f("ck_assessments_weight_range")
        ),
        sa.ForeignKeyConstraint(
            ["based_on_id"],
            ["assessments.id"],
            name=op.f("fk_assessments_based_on_id_assessments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_assessments_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["method_value_id"],
            ["tag_values.id"],
            name=op.f("fk_assessments_method_value_id_tag_values"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
            name=op.f("fk_assessments_module_id_modules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    op.create_index(
        op.f("ix_assessments_based_on_id"), "assessments", ["based_on_id"], unique=False
    )
    op.create_index(
        op.f("ix_assessments_created_by_id"), "assessments", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_assessments_deleted_at"), "assessments", ["deleted_at"], unique=False)
    op.create_index(
        op.f("ix_assessments_method_value_id"), "assessments", ["method_value_id"], unique=False
    )
    op.create_index(op.f("ix_assessments_module_id"), "assessments", ["module_id"], unique=False)
    op.create_table(
        "assessment_items",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("marks", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("based_on_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "length(btrim(label)) > 0", name=op.f("ck_assessment_items_label_not_blank")
        ),
        sa.CheckConstraint(
            "marks IS NULL OR marks >= 0", name=op.f("ck_assessment_items_marks_positive")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_items_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["based_on_id"],
            ["assessment_items.id"],
            name=op.f("fk_assessment_items_based_on_id_assessment_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_assessment_items_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_items")),
    )
    op.create_index(
        op.f("ix_assessment_items_assessment_id"),
        "assessment_items",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assessment_items_based_on_id"), "assessment_items", ["based_on_id"], unique=False
    )
    op.create_index(
        op.f("ix_assessment_items_created_by_id"),
        "assessment_items",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assessment_items_deleted_at"), "assessment_items", ["deleted_at"], unique=False
    )
    op.create_table(
        "assessment_item_objectives",
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("objective_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_assessment_item_objectives_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["assessment_items.id"],
            name=op.f("fk_assessment_item_objectives_item_id_assessment_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["objectives.id"],
            name=op.f("fk_assessment_item_objectives_objective_id_objectives"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_item_objectives")),
        sa.UniqueConstraint(
            "item_id",
            "objective_id",
            name=op.f("uq_assessment_item_objectives_item_id_objective_id"),
        ),
    )
    op.create_index(
        op.f("ix_assessment_item_objectives_created_by_id"),
        "assessment_item_objectives",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assessment_item_objectives_item_id"),
        "assessment_item_objectives",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assessment_item_objectives_objective_id"),
        "assessment_item_objectives",
        ["objective_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(
        op.f("ix_assessment_item_objectives_objective_id"), table_name="assessment_item_objectives"
    )
    op.drop_index(
        op.f("ix_assessment_item_objectives_item_id"), table_name="assessment_item_objectives"
    )
    op.drop_index(
        op.f("ix_assessment_item_objectives_created_by_id"), table_name="assessment_item_objectives"
    )
    op.drop_table("assessment_item_objectives")
    op.drop_index(op.f("ix_assessment_items_deleted_at"), table_name="assessment_items")
    op.drop_index(op.f("ix_assessment_items_created_by_id"), table_name="assessment_items")
    op.drop_index(op.f("ix_assessment_items_based_on_id"), table_name="assessment_items")
    op.drop_index(op.f("ix_assessment_items_assessment_id"), table_name="assessment_items")
    op.drop_table("assessment_items")
    op.drop_index(op.f("ix_assessments_module_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_method_value_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_deleted_at"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_created_by_id"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_based_on_id"), table_name="assessments")
    op.drop_table("assessments")
