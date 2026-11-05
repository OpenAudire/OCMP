"""personal api tokens

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-05 12:00:00.000000

Slice 1.30, ADR 060. Personal API tokens: a hash of the token, its scopes and expiry. The token
itself is shown once and never stored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "api_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_api_tokens_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_api_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )
    op.create_index(op.f("ix_api_tokens_created_by_id"), "api_tokens", ["created_by_id"])
    op.create_index(op.f("ix_api_tokens_user_id"), "api_tokens", ["user_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index(op.f("ix_api_tokens_user_id"), table_name="api_tokens")
    op.drop_index(op.f("ix_api_tokens_created_by_id"), table_name="api_tokens")
    op.drop_table("api_tokens")
