"""let module coordinators give second reviews in their own module

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27 15:00:00.000000

Data migration (product owner decision, Slice 1.14a, ADR 040). System roles are synced from
code by `app.cli` and the setup wizard, but an installed database keeps the permissions it
was given; this adds `mapping.second_review` to the system role `module_coordinator` there.
Custom roles are never touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "mapping.second_review"

# A stub of the table as it is at this revision (not the current model).
roles = sa.table(
    "roles",
    sa.column("key", sa.String),
    sa.column("is_system", sa.Boolean),
    sa.column("permissions", postgresql.ARRAY(sa.String)),
)


def upgrade() -> None:
    """Add the permission to the module coordinator system role."""
    op.execute(
        roles.update()
        .where(
            roles.c.key == "module_coordinator",
            roles.c.is_system.is_(True),
            sa.func.array_position(roles.c.permissions, PERMISSION).is_(None),
        )
        .values(permissions=sa.func.array_append(roles.c.permissions, PERMISSION))
    )


def downgrade() -> None:
    """Take the permission away again."""
    op.execute(
        roles.update()
        .where(roles.c.key == "module_coordinator", roles.c.is_system.is_(True))
        .values(permissions=sa.func.array_remove(roles.c.permissions, PERMISSION))
    )
