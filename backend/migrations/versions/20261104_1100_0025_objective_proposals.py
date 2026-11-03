"""objective proposals from study guides

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-04 11:00:00.000000

Slice 1.18, ADR 047. An AI run that reads a study guide proposes objectives; each waits here for a
person to accept it (which makes a draft objective) or reject it. Derived data: it holds the
proposed wording and a short quote from the guide, never the guide itself or its file name.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "objective_proposals",
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
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "domain",
            sa.Enum(
                "knowledge",
                "skill",
                "attitude",
                name="proposal_domain",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("source_quote", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "rejected",
                name="proposal_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("objective_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_objective_proposals_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_runs.id"],
            name=op.f("fk_objective_proposals_run_id_ai_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
            name=op.f("fk_objective_proposals_module_id_modules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_objective_proposals_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["objectives.id"],
            name=op.f("fk_objective_proposals_objective_id_objectives"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objective_proposals")),
    )
    for column in ("created_by_id", "run_id", "module_id", "status"):
        op.create_index(op.f(f"ix_objective_proposals_{column}"), "objective_proposals", [column])


def downgrade() -> None:
    op.drop_table("objective_proposals")
