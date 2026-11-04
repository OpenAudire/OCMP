"""evaluation gold sets and runs

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-04 12:00:00.000000

Slice 1.19, ADR 048. Gold sets (objectives with the mappings a person decided are right), their
rows, and the evaluation runs that keep what the AI answered. A new AI run type, evaluation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_TYPE_CHECK = op.f("ck_ai_runs_ai_run_type")
OLD_TYPES = (
    "'mapping', 'extraction', 'rewrite', 'migration', 'qa', 'classification', 'connection_test'"
)


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_constraint(RUN_TYPE_CHECK, "ai_runs", type_="check")
    op.create_check_constraint(RUN_TYPE_CHECK, "ai_runs", f"type IN ({OLD_TYPES}, 'evaluation')")
    op.create_table(
        "gold_sets",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("framework_id", sa.Uuid(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
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
            name=op.f("fk_gold_sets_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["frameworks.id"],
            name=op.f("fk_gold_sets_framework_id_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gold_sets")),
    )
    op.create_index(
        op.f("ix_gold_sets_created_by_id"), "gold_sets", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_gold_sets_deleted_at"), "gold_sets", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_gold_sets_framework_id"), "gold_sets", ["framework_id"], unique=False)
    op.create_index(
        "uq_gold_sets_name_live",
        "gold_sets",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "gold_cases",
        sa.Column("gold_set_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("objective_text", sa.Text(), nullable=False),
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
            name=op.f("fk_gold_cases_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gold_set_id"],
            ["gold_sets.id"],
            name=op.f("fk_gold_cases_gold_set_id_gold_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gold_cases")),
        sa.UniqueConstraint("gold_set_id", "position", name="uq_gold_cases_position"),
    )
    op.create_index(
        op.f("ix_gold_cases_created_by_id"), "gold_cases", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_gold_cases_gold_set_id"), "gold_cases", ["gold_set_id"], unique=False)
    op.create_table(
        "gold_links",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("item_code", sa.String(length=100), nullable=False),
        sa.Column("coverage", sa.Integer(), nullable=False),
        sa.Column(
            "depth",
            sa.Enum(
                "below",
                "matches",
                "above",
                "not_applicable",
                name="gold_depth",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
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
        sa.CheckConstraint("coverage BETWEEN 0 AND 5", name=op.f("ck_gold_links_coverage_range")),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["gold_cases.id"],
            name=op.f("fk_gold_links_case_id_gold_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_gold_links_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gold_links")),
        sa.UniqueConstraint("case_id", "item_code", name="uq_gold_links_case_item"),
    )
    op.create_index(op.f("ix_gold_links_case_id"), "gold_links", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_gold_links_created_by_id"), "gold_links", ["created_by_id"], unique=False
    )
    op.create_table(
        "eval_runs",
        sa.Column("gold_set_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column(
            "results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("not_found", sa.Integer(), server_default="0", nullable=False),
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
            ["ai_run_id"],
            ["ai_runs.id"],
            name=op.f("fk_eval_runs_ai_run_id_ai_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_eval_runs_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["gold_set_id"],
            ["gold_sets.id"],
            name=op.f("fk_eval_runs_gold_set_id_gold_sets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["curriculum_versions.id"],
            name=op.f("fk_eval_runs_version_id_curriculum_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
        sa.UniqueConstraint("ai_run_id", name=op.f("uq_eval_runs_ai_run_id")),
    )
    op.create_index(
        op.f("ix_eval_runs_created_by_id"), "eval_runs", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_eval_runs_gold_set_id"), "eval_runs", ["gold_set_id"], unique=False)
    op.create_index(op.f("ix_eval_runs_version_id"), "eval_runs", ["version_id"], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f("ix_eval_runs_version_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_gold_set_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_created_by_id"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_gold_links_created_by_id"), table_name="gold_links")
    op.drop_index(op.f("ix_gold_links_case_id"), table_name="gold_links")
    op.drop_table("gold_links")
    op.drop_index(op.f("ix_gold_cases_gold_set_id"), table_name="gold_cases")
    op.drop_index(op.f("ix_gold_cases_created_by_id"), table_name="gold_cases")
    op.drop_table("gold_cases")
    op.drop_index(
        "uq_gold_sets_name_live",
        table_name="gold_sets",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_gold_sets_framework_id"), table_name="gold_sets")
    op.drop_index(op.f("ix_gold_sets_deleted_at"), table_name="gold_sets")
    op.drop_index(op.f("ix_gold_sets_created_by_id"), table_name="gold_sets")
    op.drop_table("gold_sets")
    op.drop_constraint(RUN_TYPE_CHECK, "ai_runs", type_="check")
    op.create_check_constraint(RUN_TYPE_CHECK, "ai_runs", f"type IN ({OLD_TYPES})")
