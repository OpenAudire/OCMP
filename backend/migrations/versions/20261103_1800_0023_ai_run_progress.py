"""progress counters on AI runs

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-03 18:00:00.000000

Slice 1.16, ADR 045. A mapping run is a list of objectives; these columns say how many there
are, how many are finished, how many failed and how many suggestions were made, so the screen can
show progress while the job runs. AI runs are never deleted (migration 0011); only added to.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("total_items", "done_items", "failed_items", "links_created")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("ai_runs", sa.Column(name, sa.Integer(), server_default="0", nullable=False))
    op.create_check_constraint(
        op.f("ck_ai_runs_progress_positive"),
        "ai_runs",
        "total_items >= 0 AND done_items >= 0 AND failed_items >= 0 AND links_created >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_runs_progress_positive"), "ai_runs", type_="check")
    for name in reversed(COLUMNS):
        op.drop_column("ai_runs", name)
