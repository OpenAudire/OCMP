"""Schemas for the mapping workspace: objectives with their links, and making links (ADR 039)."""

import uuid

from pydantic import BaseModel, Field

from app.models.curriculum import ObjectiveLevel, VersionStatus
from app.models.mapping import AcceptMethod, DepthMatch, MappingSource, MappingStatus
from app.services.mapping_links import COVERAGE_MAX, COVERAGE_MIN, RATIONALE_MAX


class WorkspaceLink(BaseModel):
    """A link as the workspace shows it. No reviewer names are returned."""

    id: uuid.UUID
    framework_id: uuid.UUID
    framework_name: str
    framework_version_label: str
    item_id: uuid.UUID
    item_code: str
    item_title: str
    coverage: int | None
    depth_match: DepthMatch | None
    rationale: str
    source: MappingSource
    status: MappingStatus
    # How an accepted link was accepted; "bulk" = Accept all, no person looked at it alone.
    accept_method: AcceptMethod | None
    needs_recheck: bool
    needs_discussion: bool


class WorkspaceObjective(BaseModel):
    id: uuid.UUID
    text: str
    level: ObjectiveLevel
    phase_id: uuid.UUID | None
    phase_name: str | None
    module_id: uuid.UUID | None
    module_code: str | None
    module_name: str | None
    learning_event_id: uuid.UUID | None
    learning_event_title: str | None
    # mapping.edit / mapping.review at this objective's scope (roles higher up count).
    can_edit: bool
    can_review: bool
    links: list[WorkspaceLink]


class MappingWorkspace(BaseModel):
    version_id: uuid.UUID
    academic_year: int
    version_status: VersionStatus
    programme_id: uuid.UUID
    programme_name: str
    # Only draft versions can be mapped (ADR 030).
    editable: bool
    # The institution's four-eyes mode: reviewers' links wait for a second reviewer.
    four_eyes: bool
    objectives: list[WorkspaceObjective]


class LinkCreate(BaseModel):
    framework_item_id: uuid.UUID
    coverage: int = Field(ge=COVERAGE_MIN, le=COVERAGE_MAX)
    depth_match: DepthMatch
    rationale: str = Field(default="", max_length=RATIONALE_MAX)


class LinkUpdate(BaseModel):
    coverage: int = Field(ge=COVERAGE_MIN, le=COVERAGE_MAX)
    depth_match: DepthMatch
    rationale: str = Field(default="", max_length=RATIONALE_MAX)


class LinkRemoved(BaseModel):
    # False when the link was rejected instead of deleted (a suggestion of the system).
    deleted: bool
