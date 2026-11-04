"""external ids and import jobs

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-04 15:00:00.000000

Slice 1.25, ADR 054. An external id on phases, modules, sessions and objectives (an Excel import
updates the item with the same id instead of making a second one; copy forward keeps it), and the
history of applied imports (counts only).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("phases", "modules", "learning_events", "objectives")
UNIQUE = {
    "phases": "uq_phases_version_external_id_live",
    "modules": "uq_modules_version_external_id_live",
    "objectives": "uq_objectives_version_external_id_live",
}


def upgrade() -> None:
    """Upgrade database schema."""
    for table in TABLES:
        op.add_column(table, sa.Column("external_id", sa.String(length=128), nullable=True))
        op.create_index(op.f(f"ix_{table}_external_id"), table, ["external_id"], unique=False)
    for table, name in UNIQUE.items():
        op.create_index(
            name,
            table,
            ["version_id", "external_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    op.create_table(
        "import_jobs",
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="applied", nullable=False),
        sa.Column(
            "summary",
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
            name=op.f("fk_import_jobs_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["curriculum_versions.id"],
            name=op.f("fk_import_jobs_version_id_curriculum_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
    )
    op.create_index(op.f("ix_import_jobs_created_by_id"), "import_jobs", ["created_by_id"])
    op.create_index(op.f("ix_import_jobs_kind"), "import_jobs", ["kind"])
    op.create_index(op.f("ix_import_jobs_version_id"), "import_jobs", ["version_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f("ix_import_jobs_version_id"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_kind"), table_name="import_jobs")
    op.drop_index(op.f("ix_import_jobs_created_by_id"), table_name="import_jobs")
    op.drop_table("import_jobs")
    for table, name in UNIQUE.items():
        op.drop_index(name, table_name=table)
    for table in reversed(TABLES):
        op.drop_index(op.f(f"ix_{table}_external_id"), table_name=table)
        op.drop_column(table, "external_id")
