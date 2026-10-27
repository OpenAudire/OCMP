"""add ai settings and provider configs

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27 12:44:55.107538
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RUN_TYPE_CHECK = op.f("ck_ai_runs_ai_run_type")
OLD_TYPES = "'mapping', 'extraction', 'rewrite', 'migration', 'qa', 'classification'"


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_constraint(RUN_TYPE_CHECK, "ai_runs", type_="check")
    op.create_check_constraint(
        RUN_TYPE_CHECK, "ai_runs", f"type IN ({OLD_TYPES}, 'connection_test')"
    )
    op.create_table(
        "ai_provider_configs",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "null",
                "anthropic",
                "openai_compatible",
                "ollama",
                name="ai_provider_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column(
            "data_location",
            sa.Enum(
                "local",
                "south_africa",
                "outside_south_africa",
                name="ai_data_location",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="outside_south_africa",
            nullable=False,
        ),
        sa.Column("temperature", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("input_price_per_mtok", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("output_price_per_mtok", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_key_set_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "provider <> 'null'", name=op.f("ck_ai_provider_configs_provider_is_real")
        ),
        sa.CheckConstraint(
            "(input_price_per_mtok IS NULL OR input_price_per_mtok >= 0)"
            " AND (output_price_per_mtok IS NULL OR output_price_per_mtok >= 0)",
            name=op.f("ck_ai_provider_configs_prices_positive"),
        ),
        sa.CheckConstraint(
            "temperature IS NULL OR temperature BETWEEN 0 AND 2",
            name=op.f("ck_ai_provider_configs_temperature"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_ai_provider_configs_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_ai_provider_configs_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_provider_configs")),
        sa.UniqueConstraint(
            "institution_id",
            "provider",
            name=op.f("uq_ai_provider_configs_institution_id_provider"),
        ),
    )
    op.create_index(
        op.f("ix_ai_provider_configs_created_by_id"),
        "ai_provider_configs",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_provider_configs_institution_id"),
        "ai_provider_configs",
        ["institution_id"],
        unique=False,
    )
    op.create_table(
        "ai_settings",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column(
            "active_provider",
            sa.Enum(
                "null",
                "anthropic",
                "openai_compatible",
                "ollama",
                name="ai_active_provider",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="null",
            nullable=False,
        ),
        sa.Column("local_only", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "on_personal_data",
            sa.Enum(
                "refuse",
                "redact",
                name="ai_personal_data_action",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="refuse",
            nullable=False,
        ),
        sa.Column(
            "monthly_cost_cap",
            sa.Numeric(precision=12, scale=2),
            server_default="10.00",
            nullable=True,
        ),
        sa.Column("monthly_token_cap", sa.BigInteger(), server_default="2000000", nullable=True),
        sa.Column("monthly_call_cap", sa.Integer(), server_default="2000", nullable=True),
        sa.Column("max_calls_per_run", sa.Integer(), server_default="500", nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default="1024", nullable=False),
        sa.Column("ack_provider_key", sa.String(length=600), nullable=True),
        sa.Column("ack_by_id", sa.Uuid(), nullable=True),
        sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "(monthly_cost_cap IS NULL OR monthly_cost_cap >= 0)"
            " AND (monthly_token_cap IS NULL OR monthly_token_cap >= 0)"
            " AND (monthly_call_cap IS NULL OR monthly_call_cap >= 0)"
            " AND max_calls_per_run > 0 AND max_output_tokens > 0",
            name=op.f("ck_ai_settings_limits_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["ack_by_id"],
            ["users.id"],
            name=op.f("fk_ai_settings_ack_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_ai_settings_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_ai_settings_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_settings")),
        sa.UniqueConstraint("institution_id", name=op.f("uq_ai_settings_institution_id")),
    )
    op.create_index(
        op.f("ix_ai_settings_created_by_id"), "ai_settings", ["created_by_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # AI runs can never be deleted, so a downgrade is refused while connection tests exist.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM ai_runs WHERE type = 'connection_test') THEN "
        "RAISE EXCEPTION 'AI runs cannot be deleted; connection test runs exist'; "
        "END IF; END $$"
    )
    op.drop_constraint(RUN_TYPE_CHECK, "ai_runs", type_="check")
    op.create_check_constraint(RUN_TYPE_CHECK, "ai_runs", f"type IN ({OLD_TYPES})")
    op.drop_index(op.f("ix_ai_settings_created_by_id"), table_name="ai_settings")
    op.drop_table("ai_settings")
    op.drop_index(op.f("ix_ai_provider_configs_institution_id"), table_name="ai_provider_configs")
    op.drop_index(op.f("ix_ai_provider_configs_created_by_id"), table_name="ai_provider_configs")
    op.drop_table("ai_provider_configs")
