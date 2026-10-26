"""Schemas for the framework pack import screen (ADR 036)."""

import uuid

from pydantic import BaseModel, Field

from app.models.framework import FrameworkProfile, FrameworkStatus


class ProblemRead(BaseModel):
    path: str
    message: str


class PackMetadataRead(BaseModel):
    key: str
    name: str
    version: str
    publisher: str
    licence: str
    profile: FrameworkProfile
    description: str
    url: str | None
    template: bool


class PackCountsRead(BaseModel):
    items: int
    levels: int
    root_items: int
    cross_references: int
    external_references: int
    crosswalks: int
    crosswalk_entries: int
    taxonomy_scales: int
    tag_lists: int
    tag_values: int


class SampleItemRead(BaseModel):
    code: str
    title: str
    depth: int


class PackPreviewRead(BaseModel):
    """What a pack file would do. ``token`` is set only when it can be imported."""

    valid: bool
    errors: list[ProblemRead]
    warnings: list[str]
    format_version: int | None = None
    metadata: PackMetadataRead | None = None
    counts: PackCountsRead | None = None
    sample: list[SampleItemRead] = []
    sample_truncated: bool = False
    token: str | None = None
    # Seconds the token stays valid.
    expires_in: int | None = None


class PackImportRequest(BaseModel):
    token: str = Field(min_length=10, max_length=100)
    # Make the imported version the active one (earlier versions become superseded).
    activate: bool = False


class PackImportRead(BaseModel):
    framework_id: uuid.UUID
    key: str
    name: str
    version: str
    status: FrameworkStatus
    items: int
    cross_references: int
    external_references: int
    crosswalks: int
    crosswalk_entries: int
    scales_created: int
    tag_lists_created: int
    tag_values_added: int
    superseded_versions: int


class PackTemplateRead(BaseModel):
    name: str
    title: str
    description: str
    items: int
