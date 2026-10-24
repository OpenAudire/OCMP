"""Tag lists ("mapping lists"), their values, and taggings of curriculum items.

Examples: teaching methods (PBL, lecture...), assessment methods (OSCE, MCQ...),
themes, longitudinal threads, keywords, resources, EPAs and custom lists.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import CoreModel, SoftDeleteMixin, live_unique, str_enum


class TagListKind(StrEnum):
    TEACHING_METHOD = "teaching_method"
    ASSESSMENT_METHOD = "assessment_method"
    THEME = "theme"
    THREAD = "thread"
    KEYWORD = "keyword"
    RESOURCE = "resource"
    EPA = "epa"
    CUSTOM = "custom"


class TaggableType(StrEnum):
    """What can be tagged. Each has its own column on ``taggings``."""

    PROGRAMME = "programme"
    MODULE = "module"
    LEARNING_EVENT = "learning_event"
    OBJECTIVE = "objective"


# Tagging column for each taggable type.
TAGGING_COLUMNS = {
    TaggableType.PROGRAMME: "programme_id",
    TaggableType.MODULE: "module_id",
    TaggableType.LEARNING_EVENT: "learning_event_id",
    TaggableType.OBJECTIVE: "objective_id",
}


class TagList(SoftDeleteMixin, CoreModel):
    """A configurable list of tags, managed by the curriculum office."""

    __tablename__ = "tag_lists"
    __table_args__ = (
        live_unique("uq_tag_lists_key_live", "key"),
        CheckConstraint("key ~ '^[a-z0-9_-]+$'", name="key_format"),
    )

    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[TagListKind] = mapped_column(str_enum(TagListKind, "tag_list_kind"))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Which kinds of item this list may tag (TaggableType values).
    entity_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)),
        default=lambda: [t.value for t in TaggableType],
        server_default="{programme,module,learning_event,objective}",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    values: Mapped[list["TagValue"]] = relationship(
        back_populates="tag_list", lazy="raise", order_by="TagValue.position"
    )


class TagValue(SoftDeleteMixin, CoreModel):
    """One tag in a list."""

    __tablename__ = "tag_values"
    __table_args__ = (
        live_unique("uq_tag_values_list_label_live", "tag_list_id", "label"),
        live_unique("uq_tag_values_list_code_live", "tag_list_id", "code"),
    )

    tag_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tag_lists.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(255))
    # Stable identifier for imports (upsert by code); optional.
    code: Mapped[str | None] = mapped_column(String(64), default=None)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    tag_list: Mapped[TagList] = relationship(back_populates="values", lazy="raise")


class Tagging(CoreModel):
    """A tag applied to one curriculum item, directly or by inheritance.

    Exactly one of the item columns is set. An inherited tagging points to the
    tagging it came from, and disappears with it.
    """

    __tablename__ = "taggings"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(programme_id, module_id, learning_event_id, objective_id) = 1",
            name="exactly_one_item",
        ),
        CheckConstraint(
            "inherited_from_id IS NULL OR inherited_from_id <> id", name="not_self_inherited"
        ),
        UniqueConstraint(
            "tag_value_id",
            "programme_id",
            "module_id",
            "learning_event_id",
            "objective_id",
            "inherited_from_id",
            postgresql_nulls_not_distinct=True,
            name="uq_taggings_value_item_source",
        ),
    )

    tag_value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tag_values.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programmes.id", ondelete="CASCADE"), default=None, index=True
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), default=None, index=True
    )
    learning_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("learning_events.id", ondelete="CASCADE"), default=None, index=True
    )
    objective_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), default=None, index=True
    )
    inherited_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("taggings.id", ondelete="CASCADE"), default=None, index=True
    )

    tag_value: Mapped[TagValue] = relationship(lazy="raise")

    @property
    def is_inherited(self) -> bool:
        return self.inherited_from_id is not None
