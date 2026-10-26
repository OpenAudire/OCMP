"""seed the exit-level minimum credits of the bachelor's qualification types

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27 09:01:00.000000

Data migration. Stellenbosch University, "Guidelines on qualification types" (July 2022),
as given by the product owner: a Bachelor's degree (360 credits) has at least 120 credits at
NQF level 7, and a professional Bachelor's degree (480 credits) at least 120 credits at
NQF level 8. The source document was not fetched when this was written, so the figures are
to be checked against the current CHE and HEQSF documents. Institutions can edit them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A stub of the table as it is at this revision (not the current model).
qualification_types = sa.table(
    "qualification_types",
    sa.column("key", sa.String),
    sa.column("min_exit_level_credits", sa.Integer),
    sa.column("notes", sa.Text),
)

# key, credits at the type's NQF exit level, note added to the seeded one
SEEDS = [
    (
        "bachelors",
        120,
        "At least 120 credits at NQF level 7 "
        "(Stellenbosch University, Guidelines on qualification types, July 2022; "
        "verify against the current CHE/HEQSF documents).",
    ),
    (
        "bachelors_professional",
        120,
        "At least 120 credits at NQF level 8 "
        "(Stellenbosch University, Guidelines on qualification types, July 2022; "
        "verify against the current CHE/HEQSF documents).",
    ),
]


def upgrade() -> None:
    """Set the exit-level minimum credits and say where they come from."""
    for key, credits, note in SEEDS:
        op.execute(
            qualification_types.update()
            .where(qualification_types.c.key == key)
            .values(
                min_exit_level_credits=credits,
                notes=sa.func.trim(qualification_types.c.notes + " " + sa.literal(note)),
            )
        )


def downgrade() -> None:
    """Clear the figures (the added sentence in the notes is removed too)."""
    for key, _credits, note in SEEDS:
        op.execute(
            qualification_types.update()
            .where(qualification_types.c.key == key)
            .values(
                min_exit_level_credits=None,
                notes=sa.func.trim(
                    sa.func.replace(qualification_types.c.notes, sa.literal(" " + note), "")
                ),
            )
        )
