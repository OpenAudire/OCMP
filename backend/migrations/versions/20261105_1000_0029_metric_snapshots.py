"""metric snapshots

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-05 10:00:00.000000

Slice 1.28, ADR 058. The key figures of a curriculum version once a day (counts and shares only),
which the committee dashboard draws as trend lines.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "metric_snapshots",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_metric_snapshots_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["curriculum_versions.id"],
            name=op.f("fk_metric_snapshots_version_id_curriculum_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_snapshots")),
        sa.UniqueConstraint("version_id", "taken_on", name="uq_metric_snapshots_day"),
    )
    op.create_index(
        op.f("ix_metric_snapshots_created_by_id"), "metric_snapshots", ["created_by_id"]
    )
    op.create_index(op.f("ix_metric_snapshots_version_id"), "metric_snapshots", ["version_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f("ix_metric_snapshots_version_id"), table_name="metric_snapshots")
    op.drop_index(op.f("ix_metric_snapshots_created_by_id"), table_name="metric_snapshots")
    op.drop_table("metric_snapshots")
