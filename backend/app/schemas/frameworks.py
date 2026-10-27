"""Schemas for reading frameworks: the library, the item tree and where items are mapped."""

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.framework import FrameworkProfile, FrameworkStatus
from app.models.mapping import DepthMatch, MappingSource, MappingStatus


class FrameworkSummary(BaseModel):
    """One framework version in the library."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    version_label: str
    publisher: str
    licence_note: str
    description: str
    url: str | None
    profile: FrameworkProfile
    status: FrameworkStatus
    item_count: int
    top_level_count: int
    level_count: int


class FrameworkLibrary(BaseModel):
    frameworks: list[FrameworkSummary]
    # Whether the user may delete unused framework versions (frameworks.manage).
    can_manage: bool


class FrameworkItemRead(BaseModel):
    """A node of the tree: its own details and how many children it has."""

    id: uuid.UUID
    code: str
    title: str
    depth: int
    child_count: int
    # Mapping links the user may see (not rejected) to the item itself.
    mapped_count: int


class ItemPage(BaseModel):
    """A window of the children of one parent (or of the top level).

    ``offset`` is the position of the first item in the window among all ``total``
    siblings, so a long list can be opened part by part.
    """

    parent_id: uuid.UUID | None
    offset: int
    total: int
    items: list[FrameworkItemRead]


class AncestorRead(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class DetailAncestor(AncestorRead):
    # Position among its siblings (from 0), so the tree can open to the item.
    sibling_index: int


class SearchHit(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    depth: int
    # The items above it, top level first.
    path: list[AncestorRead]
    mapped_count: int


class SearchPage(BaseModel):
    query: str
    offset: int
    total: int
    hits: list[SearchHit]


class ItemDetail(BaseModel):
    id: uuid.UUID
    framework_id: uuid.UUID
    code: str
    title: str
    description: str
    depth: int
    child_count: int
    mapped_count: int
    # The items above it, top level first, each with its place among its siblings.
    path: list[DetailAncestor]
    sibling_index: int


class MappedObjective(BaseModel):
    """An objective linked to a framework item, with where it sits in the curriculum."""

    link_id: uuid.UUID
    status: MappingStatus
    source: MappingSource
    coverage: int | None
    depth_match: DepthMatch | None
    needs_recheck: bool
    needs_discussion: bool
    objective_id: uuid.UUID
    objective_text: str
    level: ObjectiveLevel
    programme_id: uuid.UUID
    programme_name: str
    version_id: uuid.UUID
    academic_year: int
    version_status: VersionStatus
    module_id: uuid.UUID | None
    module_code: str | None
    module_name: str | None
    learning_event_id: uuid.UUID | None
    learning_event_title: str | None


class WhereMapped(BaseModel):
    item_id: uuid.UUID
    # Links the user may see; ``mappings`` holds the first ``limit`` of them.
    total: int
    limit: int
    mappings: list[MappedObjective]
