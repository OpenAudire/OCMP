"""Frameworks (competency frameworks, level descriptors, vocabularies) and taxonomy scales.

Each framework row is one version of a framework: frameworks with the same
``key`` and different ``version_label`` are versions of the same framework,
and crosswalks describe how items move between two versions. Field names
follow the framework pack format (``packs/schema/framework-pack.schema.json``).
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import CoreModel, SoftDeleteMixin, live_unique, str_enum


class FrameworkProfile(StrEnum):
    CORE = "core"
    HEALTH = "health"
    OTHER = "other"


class FrameworkStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"  # a newer version exists
    RETIRED = "retired"


class CrossRefType(StrEnum):
    RELATED = "related"
    PREREQUISITE = "prerequisite"
    BROADER = "broader"
    NARROWER = "narrower"
    EQUIVALENT = "equivalent"  # mainly between frameworks


class CrosswalkEntryType(StrEnum):
    EQUIVALENT = "equivalent"  # old item maps to one new item
    SPLIT = "split"  # old item maps to several new items (one entry each)
    MERGED = "merged"  # several old items map to one new item (one entry each)
    REMOVED = "removed"  # old item has no successor
    NEW = "new"  # new item has no predecessor


class TaxonomyScale(CoreModel):
    """An ordered scale of cognitive or performance levels (Bloom, Miller, SOLO...)."""

    __tablename__ = "taxonomy_scales"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")

    levels: Mapped[list["TaxonomyLevel"]] = relationship(
        back_populates="scale", lazy="raise", order_by="TaxonomyLevel.position"
    )


class TaxonomyLevel(CoreModel):
    """One level of a scale, with the verbs that suggest it."""

    __tablename__ = "taxonomy_levels"
    __table_args__ = (
        UniqueConstraint("scale_id", "position"),
        UniqueConstraint("scale_id", "name"),
        CheckConstraint("position >= 0", name="position_positive"),
    )

    scale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_scales.id", ondelete="CASCADE"), index=True
    )
    # Order within the scale (pack field "order"); higher means more demanding.
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    verbs: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, server_default="{}")

    scale: Mapped[TaxonomyScale] = relationship(back_populates="levels", lazy="raise")


class Framework(SoftDeleteMixin, CoreModel):
    """One version of a framework."""

    __tablename__ = "frameworks"
    __table_args__ = (
        live_unique("uq_frameworks_key_version_live", "key", "version_label"),
        CheckConstraint("key ~ '^[a-z0-9-]+$'", name="key_format"),
    )

    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version_label: Mapped[str] = mapped_column(String(64))
    publisher: Mapped[str] = mapped_column(String(255))
    # Licence or usage restrictions, shown wherever the framework is used.
    licence_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    url: Mapped[str | None] = mapped_column(String(2048), default=None)
    profile: Mapped[FrameworkProfile] = mapped_column(
        str_enum(FrameworkProfile, "framework_profile"),
        default=FrameworkProfile.CORE,
        server_default=FrameworkProfile.CORE.value,
    )
    status: Mapped[FrameworkStatus] = mapped_column(
        str_enum(FrameworkStatus, "framework_status"),
        default=FrameworkStatus.DRAFT,
        server_default=FrameworkStatus.DRAFT.value,
    )

    items: Mapped[list["FrameworkItem"]] = relationship(
        back_populates="framework", lazy="raise", order_by="FrameworkItem.position"
    )


class FrameworkItem(CoreModel):
    """A competency, descriptor or keyword within a framework, in a tree.

    Items are not soft-deleted: a framework version is fixed once published,
    and changes are made in a new version with a crosswalk.
    """

    __tablename__ = "framework_items"
    __table_args__ = (
        UniqueConstraint("framework_id", "code"),
        # Target of the composite FK that keeps a parent in the same framework.
        UniqueConstraint("id", "framework_id"),
        ForeignKeyConstraint(
            ["parent_id", "framework_id"],
            ["framework_items.id", "framework_items.framework_id"],
            name="fk_framework_items_parent_same_framework",
            ondelete="CASCADE",
        ),
        CheckConstraint("depth >= 0", name="depth_positive"),
        CheckConstraint("(parent_id IS NULL) = (depth = 0)", name="depth_matches_parent"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frameworks.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    depth: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Order among siblings (pack field "order").
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Pack field "metadata" (``metadata`` is reserved by SQLAlchemy).
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )

    framework: Mapped[Framework] = relationship(back_populates="items", lazy="raise")
    parent: Mapped["FrameworkItem | None"] = relationship(
        foreign_keys=[parent_id],
        primaryjoin="FrameworkItem.parent_id == FrameworkItem.id",
        remote_side="FrameworkItem.id",
        lazy="raise",
        viewonly=True,
    )


class FrameworkCrossRef(CoreModel):
    """A typed link between two items, within one framework or across frameworks."""

    __tablename__ = "framework_cross_refs"
    __table_args__ = (
        UniqueConstraint("from_item_id", "to_item_id", "type"),
        CheckConstraint("from_item_id <> to_item_id", name="not_self"),
    )

    from_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), index=True
    )
    to_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[CrossRefType] = mapped_column(str_enum(CrossRefType, "cross_ref_type"))


class Crosswalk(CoreModel):
    """How the items of one framework version map onto another version."""

    __tablename__ = "crosswalks"
    __table_args__ = (
        UniqueConstraint("from_framework_id", "to_framework_id"),
        CheckConstraint("from_framework_id <> to_framework_id", name="different_frameworks"),
    )

    from_framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frameworks.id", ondelete="CASCADE"), index=True
    )
    to_framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frameworks.id", ondelete="CASCADE"), index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")

    entries: Mapped[list["CrosswalkEntry"]] = relationship(back_populates="crosswalk", lazy="raise")


class CrosswalkEntry(CoreModel):
    """One mapping in a crosswalk. Which items are set depends on the type."""

    __tablename__ = "crosswalk_entries"
    __table_args__ = (
        CheckConstraint(
            "(type = 'removed' AND from_item_id IS NOT NULL AND to_item_id IS NULL)"
            " OR (type = 'new' AND from_item_id IS NULL AND to_item_id IS NOT NULL)"
            " OR (type IN ('equivalent', 'split', 'merged')"
            " AND from_item_id IS NOT NULL AND to_item_id IS NOT NULL)",
            name="items_match_type",
        ),
    )

    crosswalk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crosswalks.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[CrosswalkEntryType] = mapped_column(
        str_enum(CrosswalkEntryType, "crosswalk_entry_type")
    )
    from_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), default=None, index=True
    )
    to_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("framework_items.id", ondelete="CASCADE"), default=None, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")

    crosswalk: Mapped[Crosswalk] = relationship(back_populates="entries", lazy="raise")
