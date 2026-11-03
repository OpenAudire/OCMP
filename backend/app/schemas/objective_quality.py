"""Request and response shapes of the objective quality checker (ADR 033)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.curriculum import ObjectiveDomain, ObjectiveLevel, ObjectiveStatus
from app.services.objective_checks import NearDuplicate
from app.services.objective_quality import CheckResult

CheckText = Annotated[str, StringConstraints(max_length=2000)]


class CheckRequest(BaseModel):
    """Wording as typed in the editor; may be empty. Nothing is saved."""

    text: CheckText
    domain: ObjectiveDomain | None = None
    taxonomy_level_id: uuid.UUID | None = None
    # Whether the objective links upward (unknown: leave out). Programme outcomes never do.
    has_parent_links: bool | None = None


class FindingRead(BaseModel):
    code: str
    severity: Literal["warning", "info"]
    message_key: str
    suggestion_key: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class LevelSuggestionRead(BaseModel):
    """A taxonomy level the leading verb points to; offered, never applied."""

    taxonomy_level_id: uuid.UUID
    level_name: str
    scale_key: str
    scale_name: str


class CheckRead(BaseModel):
    findings: list[FindingRead]
    detected_verb: str | None
    suggestions: list[LevelSuggestionRead]


class NearDuplicateRead(BaseModel):
    """Another objective of the same version and level that reads almost the same."""

    objective_id: uuid.UUID
    percent: int
    level: ObjectiveLevel
    text: str
    module_id: uuid.UUID | None
    module_code: str | None
    event_id: uuid.UUID | None
    event_title: str | None


class CheckedObjectiveRead(CheckRead):
    objective_id: uuid.UUID
    level: ObjectiveLevel
    text: str
    status: ObjectiveStatus
    domain: ObjectiveDomain | None
    # Where it belongs, for the link to edit it.
    module_id: uuid.UUID | None
    module_code: str | None
    event_id: uuid.UUID | None
    event_title: str | None
    can_edit: bool
    near_duplicates: list[NearDuplicateRead] = Field(default_factory=list)


class ObjectiveDuplicatesRead(BaseModel):
    objective_id: uuid.UUID
    matches: list[NearDuplicateRead]


class NearDuplicatesRead(BaseModel):
    """What the objective cards show. ``enabled`` is false while embeddings are off."""

    version_id: uuid.UUID
    enabled: bool
    threshold_percent: int
    objectives: list[ObjectiveDuplicatesRead]


class VersionCheckRead(BaseModel):
    version_id: uuid.UUID
    rules_language: str
    rules_version: int
    # False while embeddings are off: the list then has no near-duplicate findings.
    near_duplicates_checked: bool
    objectives: list[CheckedObjectiveRead]


def duplicate_read(match: NearDuplicate) -> NearDuplicateRead:
    return NearDuplicateRead(
        objective_id=match.objective.id,
        percent=int(match.similarity * 100),
        level=match.objective.level,
        text=match.objective.text,
        module_id=match.module.id if match.module else None,
        module_code=match.module.code if match.module else None,
        event_id=match.event.id if match.event else None,
        event_title=match.event.title if match.event else None,
    )


def check_read(result: CheckResult) -> CheckRead:
    return CheckRead(
        findings=[
            FindingRead(
                code=f.code,
                severity=f.severity.value,
                message_key=f.message_key,
                suggestion_key=f.suggestion_key,
                params=f.params,
            )
            for f in result.findings
        ],
        detected_verb=result.detected_verb,
        suggestions=[
            LevelSuggestionRead(
                taxonomy_level_id=s.level_id,
                level_name=s.level_name,
                scale_key=s.scale_key,
                scale_name=s.scale_name,
            )
            for s in result.suggestions
        ],
    )
