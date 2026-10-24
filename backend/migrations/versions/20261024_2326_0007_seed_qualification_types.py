"""seed qualification types

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24 23:26:00

Data migration: default HEQSF qualification types from the project brief
(section 9). Institutions must verify them against the current CHE/HEQSF
documents; they can be edited afterwards.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTE = "Seed value from the OCMP project brief: verify against the current HEQSF."

# key, name, NQF exit level, minimum total credits, extra note
QUALIFICATION_TYPES = [
    ("higher_certificate", "Higher Certificate", 5, 120, ""),
    ("advanced_certificate", "Advanced Certificate", 6, 120, ""),
    ("diploma", "Diploma", 6, 240, "Diplomas carry 240 or 360 credits."),
    ("advanced_diploma", "Advanced Diploma", 7, 120, ""),
    ("bachelors", "Bachelor's Degree", 7, 360, ""),
    ("bachelors_professional", "Professional Bachelor's Degree", 8, 480, ""),
    ("postgraduate_diploma", "Postgraduate Diploma", 8, 120, ""),
    ("honours", "Bachelor Honours Degree", 8, 120, ""),
    ("masters", "Master's Degree", 9, 180, ""),
    ("doctoral", "Doctoral Degree", 10, 360, ""),
]

# A stub of the table as it is at this revision (not the current model).
qualification_types = sa.table(
    "qualification_types",
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("nqf_exit_level", sa.Integer),
    sa.column("min_total_credits", sa.Integer),
    sa.column("notes", sa.Text),
)


def upgrade() -> None:
    """Insert the default qualification types."""
    op.bulk_insert(
        qualification_types,
        [
            {
                "key": key,
                "name": name,
                "nqf_exit_level": level,
                "min_total_credits": credits,
                "notes": f"{NOTE} {extra}".strip(),
            }
            for key, name, level, credits, extra in QUALIFICATION_TYPES
        ],
    )


def downgrade() -> None:
    """Remove the seeded qualification types (fails if programmes still use them)."""
    keys = [row[0] for row in QUALIFICATION_TYPES]
    op.execute(qualification_types.delete().where(qualification_types.c.key.in_(keys)))
