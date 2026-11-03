"""add embeddings and objective similarities

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-03 10:00:00.000000

Slice 1.15, ADR 044. ``embeddings`` is the text-hash cache of vectors (384 numbers, cosine
HNSW index). ``objective_similarities`` holds close pairs of objectives found by a job after
a save, so the objective card reads a stored result. Both are derived data and can be
rebuilt with ``python -m app.cli embed-all``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
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
        sa.Column(
            "entity_type",
            sa.Enum(
                "objective",
                "framework_item",
                name="embedded_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("model_key", sa.String(length=200), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", Vector(384), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_embeddings_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embeddings")),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "model_key", name="uq_embeddings_item_and_model"
        ),
    )
    op.create_index(op.f("ix_embeddings_created_by_id"), "embeddings", ["created_by_id"])
    op.create_index(op.f("ix_embeddings_entity_id"), "embeddings", ["entity_id"])
    op.create_index(
        "ix_embeddings_vector_cosine",
        "embeddings",
        ["vector"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"vector": "vector_cosine_ops"},
    )

    op.create_table(
        "objective_similarities",
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
        sa.Column("objective_id", sa.Uuid(), nullable=False),
        sa.Column("other_objective_id", sa.Uuid(), nullable=False),
        sa.Column("model_key", sa.String(length=200), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "objective_id < other_objective_id",
            name=op.f("ck_objective_similarities_ordered_pair"),
        ),
        sa.CheckConstraint(
            "similarity >= 0 AND similarity <= 1",
            name=op.f("ck_objective_similarities_similarity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_objective_similarities_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["objectives.id"],
            name=op.f("fk_objective_similarities_objective_id_objectives"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["other_objective_id"],
            ["objectives.id"],
            name=op.f("fk_objective_similarities_other_objective_id_objectives"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objective_similarities")),
        sa.UniqueConstraint(
            "objective_id",
            "other_objective_id",
            "model_key",
            name="uq_objective_similarities_pair",
        ),
    )
    op.create_index(
        op.f("ix_objective_similarities_created_by_id"),
        "objective_similarities",
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_objective_similarities_objective_id"), "objective_similarities", ["objective_id"]
    )
    op.create_index(
        op.f("ix_objective_similarities_other_objective_id"),
        "objective_similarities",
        ["other_objective_id"],
    )


def downgrade() -> None:
    op.drop_table("objective_similarities")
    op.drop_table("embeddings")
