"""faculty and department codes are unique among live rows

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-06 13:00:00.000000

Slice 1.31. Faculties and departments are soft-deleted (``remove-demo`` deletes the demo's), but
their
code was unique among *all* rows, so loading the demo again after removing it failed. Like every
other soft-deletable table, the code is now unique among rows that are not deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_constraint("uq_faculties_institution_id_code", "faculties", type_="unique")
    op.create_index(
        "uq_faculties_institution_code_live",
        "faculties",
        ["institution_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint("uq_departments_faculty_id_code", "departments", type_="unique")
    op.create_index(
        "uq_departments_faculty_code_live",
        "departments",
        ["faculty_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade database schema (fails if a deleted and a live row share a code)."""
    op.drop_index("uq_departments_faculty_code_live", table_name="departments")
    op.create_unique_constraint(
        "uq_departments_faculty_id_code", "departments", ["faculty_id", "code"]
    )
    op.drop_index("uq_faculties_institution_code_live", table_name="faculties")
    op.create_unique_constraint(
        "uq_faculties_institution_id_code", "faculties", ["institution_id", "code"]
    )
