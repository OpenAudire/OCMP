"""Schemas for tag lists, tag values and tagging curriculum items (ADR 034)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.curriculum import ObjectiveLevel
from app.models.tagging import TaggableType, TagListKind
from app.services.tagging import ItemTag

# The kinds of item that can be tagged from the builder. Programmes are not versioned
# items, so they are not offered (ADR 034); older lists may still list them.
TaggableKind = Literal["module", "learning_event", "objective"]
ListItemType = Literal["programme", "module", "learning_event", "objective"]

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ListKey = Annotated[str, StringConstraints(max_length=64, pattern=r"^[a-z0-9_-]+$")]
ValueCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class TagValueRead(BaseModel):
    id: uuid.UUID
    label: str
    code: str | None
    description: str
    position: int
    is_active: bool
    # Taggings and sessions using it; only filled in for managers.
    usage_count: int = 0


class TagListRead(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    kind: TagListKind
    description: str
    entity_types: list[str]
    is_active: bool
    values: list[TagValueRead]


class TagListCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: ListKey
    name: Label
    kind: TagListKind = TagListKind.CUSTOM
    description: Text = ""
    entity_types: list[TaggableKind] = Field(
        default=["module", "learning_event", "objective"], min_length=1
    )


class TagListUpdate(BaseModel):
    """Fields left out stay as they are. The key and kind cannot change."""

    model_config = ConfigDict(extra="forbid")

    name: Label | None = None
    description: Text | None = None
    entity_types: list[ListItemType] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class TagValueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Label
    code: ValueCode | None = None
    description: Text = ""


class TagValueUpdate(BaseModel):
    """Fields left out stay as they are; ``code: null`` clears the code."""

    model_config = ConfigDict(extra="forbid")

    label: Label | None = None
    code: ValueCode | None = None
    description: Text | None = None
    is_active: bool | None = None


# --- Tags on curriculum items ---------------------------------------------------------


class TagSourceRead(BaseModel):
    """The item an inherited tag came from."""

    item_type: TaggableType
    item_id: uuid.UUID
    name: str


class ItemTagRead(BaseModel):
    """A tag on an item: set directly (removable), inherited from sources, or both."""

    tag_value_id: uuid.UUID
    label: str
    list_id: uuid.UUID
    list_name: str
    # The tagging to remove; null when the tag is only inherited.
    direct_tagging_id: uuid.UUID | None
    sources: list[TagSourceRead]


class TagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_value_id: uuid.UUID
    # Also tag the items in the preview that do not have the tag yet.
    inherit: bool = False


class PreviewItem(BaseModel):
    item_type: TaggableType
    item_id: uuid.UUID
    name: str
    # For objectives: programme, module or learning event.
    level: ObjectiveLevel | None
    # Module code for a session or objective that sits in a module, for orientation.
    module_code: str | None
    # new: would get the tag; has_tag: already has it directly; not_applicable: the
    # list is not used on this kind of item.
    status: Literal["new", "has_tag", "not_applicable"]


class InheritancePreviewRead(BaseModel):
    tag_value_id: uuid.UUID
    label: str
    list_name: str
    # The item itself already carries the tag directly (saving would conflict).
    item_has_tag: bool
    items: list[PreviewItem]


class TagApplied(BaseModel):
    """The item's tags after tagging, and how many other items received the tag."""

    tags: list[ItemTagRead]
    inherited_count: int


def item_tag_reads(tags: list[ItemTag]) -> list[ItemTagRead]:
    """The API form of the tags ``item_tags`` found for one item."""
    return [
        ItemTagRead(
            tag_value_id=tag.value.id,
            label=tag.value.label,
            list_id=tag.tag_list.id,
            list_name=tag.tag_list.name,
            direct_tagging_id=tag.direct_tagging_id,
            sources=[
                TagSourceRead(item_type=s.item_type, item_id=s.item_id, name=s.name)
                for s in tag.sources
            ],
        )
        for tag in tags
    ]
