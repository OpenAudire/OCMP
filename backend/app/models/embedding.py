"""Stored embeddings and the near-duplicate pairs computed from them (ADR 044).

Both tables hold derived data: they can be deleted and rebuilt (``python -m app.cli
embed-all``) and are not audited or exported.
"""

import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CoreModel, str_enum

DIMENSIONS = 384


class EmbeddedType(StrEnum):
    OBJECTIVE = "objective"
    FRAMEWORK_ITEM = "framework_item"


class Embedding(CoreModel):
    """The vector of one item's text, made by one model recipe.

    ``entity_id`` has no foreign key (it points at more than one table); rows are removed
    by the sweep (``embed-all``) and are always joined to the live item before use.
    """

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "model_key", name="uq_embeddings_item_and_model"
        ),
        Index(
            "ix_embeddings_vector_cosine",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )

    entity_type: Mapped[EmbeddedType] = mapped_column(str_enum(EmbeddedType, "embedded_type"))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # Model name, prompt prefix and recipe version (``app.ai.embeddings.MODEL_KEY``).
    model_key: Mapped[str] = mapped_column(String(200))
    # SHA-256 of the exact text sent; the item is embedded again only when this changes.
    text_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))


class ObjectiveSimilarity(CoreModel):
    """Two objectives of one version and level whose wording is close.

    Each pair is stored once, with ``objective_id`` the smaller id. Only pairs at or above a
    floor are kept; the institution's threshold (``settings["quality"]``) is applied when
    reading, so changing it needs no recomputation. Rows go with either objective.
    """

    __tablename__ = "objective_similarities"
    __table_args__ = (
        UniqueConstraint(
            "objective_id", "other_objective_id", "model_key", name="uq_objective_similarities_pair"
        ),
        CheckConstraint("objective_id < other_objective_id", name="ordered_pair"),
        CheckConstraint("similarity >= 0 AND similarity <= 1", name="similarity_range"),
    )

    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )
    other_objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(200))
    similarity: Mapped[float] = mapped_column(Float)
