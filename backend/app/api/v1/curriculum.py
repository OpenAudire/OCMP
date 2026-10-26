"""Reading the curriculum: programmes, versions, the structure tree and item details.

Every response contains only what the signed-in user may see (see
``app/services/curriculum_read.py``). Anything they may not see is a 404, the
same as something that does not exist.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser
from app.api.v1.assessments import read_assessment
from app.core.database import DbSession
from app.schemas.assessments import ModuleHoursRead
from app.schemas.curriculum import (
    LearningEventRead,
    ModuleRead,
    ObjectiveRead,
    ProgrammeRead,
    ProgrammeRef,
    ProgrammeSummary,
    QualificationTypeRead,
    StructureEvent,
    StructureModule,
    StructurePhase,
    VersionRead,
    VersionStructure,
)
from app.schemas.tagging import item_tag_reads
from app.services import assessments as assessment_service
from app.services import credit_check
from app.services.curriculum_read import (
    CurriculumAccess,
    ModuleNode,
    ObjectiveWithLinks,
    VisibleProgramme,
    curriculum_access,
    event_detail,
    module_detail,
    programme_outcomes,
    version_structure,
    visible_programme,
    visible_programmes,
    visible_version,
)

router = APIRouter(tags=["curriculum"])


async def get_access(user: CurrentUser, db: DbSession) -> CurriculumAccess:
    return await curriculum_access(db, user)


Access = Annotated[CurriculumAccess, Depends(get_access)]


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found.")


def _summary(found: VisibleProgramme) -> ProgrammeSummary:
    programme = found.programme
    return ProgrammeSummary(
        id=programme.id,
        code=programme.code,
        name=programme.name,
        faculty_id=programme.faculty_id,
        faculty_name=programme.faculty.name,
        status=programme.status,
        versions=[VersionRead.model_validate(v) for v in found.versions],
    )


def _objectives(items: list[ObjectiveWithLinks]) -> list[ObjectiveRead]:
    return [
        ObjectiveRead(
            id=item.objective.id,
            text=item.objective.text,
            domain=item.objective.domain,
            taxonomy_level_id=item.objective.taxonomy_level_id,
            status=item.objective.status,
            position=item.objective.position,
            parent_ids=item.parent_ids,
            mappings_to_recheck=item.mappings_to_recheck,
            tags=item_tag_reads(item.tags),
        )
        for item in items
    ]


def _module(node: ModuleNode) -> StructureModule:
    module = node.module
    return StructureModule(
        id=module.id,
        code=module.code,
        name=module.name,
        phase_id=module.phase_id,
        position=module.position,
        credits=module.credits,
        nqf_level=module.nqf_level,
        context_only=node.context_only,
        objective_count=node.objective_count,
        can_edit=node.can_edit,
        events=[
            StructureEvent(
                id=e.event.id,
                title=e.event.title,
                position=e.event.position,
                week=e.event.week,
                format=e.format_label,
                format_value_id=e.event.format_value_id,
                contact_minutes=e.event.contact_minutes,
                self_study_minutes=e.event.self_study_minutes,
                objective_count=e.objective_count,
                can_edit=e.can_edit,
            )
            for e in node.events
        ],
    )


@router.get("/programmes", response_model=list[ProgrammeSummary])
async def list_programmes(access: Access, db: DbSession) -> list[ProgrammeSummary]:
    """Programmes the user may see, by name, each with its visible versions."""
    return [_summary(found) for found in await visible_programmes(db, access)]


@router.get("/programmes/{programme_id}", response_model=ProgrammeRead)
async def get_programme(programme_id: uuid.UUID, access: Access, db: DbSession) -> ProgrammeRead:
    """A programme's details and its visible versions."""
    found = await visible_programme(db, access, programme_id)
    if found is None:
        raise _not_found("Programme")
    programme = found.programme
    qualification = None
    if programme.qualification_type_id is not None:
        await db.refresh(programme, attribute_names=["qualification_type"])
        if programme.qualification_type is not None:
            qualification = QualificationTypeRead.model_validate(programme.qualification_type)
    return ProgrammeRead(
        **_summary(found).model_dump(),
        qualification_type=qualification,
        nqf_exit_level=programme.nqf_exit_level,
        saqa_id=programme.saqa_id,
        total_credits=programme.total_credits,
        minimum_duration_years=programme.minimum_duration_years,
        che_accreditation_status=programme.che_accreditation_status,
        che_accredited_from=programme.che_accredited_from,
        che_accredited_until=programme.che_accredited_until,
        council_name=programme.council_name,
        council_accreditation_status=programme.council_accreditation_status,
        council_accredited_from=programme.council_accredited_from,
        council_accredited_until=programme.council_accredited_until,
    )


@router.get("/curriculum-versions/{version_id}/structure", response_model=VersionStructure)
async def get_version_structure(
    version_id: uuid.UUID, access: Access, db: DbSession
) -> VersionStructure:
    """Phases, modules and sessions of a version, in order, as far as the user may see."""
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise _not_found("Curriculum version")
    structure = await version_structure(db, visible)
    programme = visible.programme
    return VersionStructure(
        version=VersionRead.model_validate(visible.version),
        programme=ProgrammeRef(id=programme.id, code=programme.code, name=programme.name),
        partial=not visible.view.full,
        outcome_count=structure.outcome_count,
        phases=[
            StructurePhase(
                id=p.phase.id,
                name=p.phase.name,
                kind=p.phase.kind,
                position=p.phase.position,
                modules=[_module(m) for m in p.modules],
            )
            for p in structure.phases
        ],
        modules_without_phase=[_module(m) for m in structure.modules_without_phase],
        can_edit=structure.can_edit,
        can_change_status=structure.can_change_status,
        can_copy_forward=structure.can_copy_forward,
        can_edit_outcomes=structure.can_edit_outcomes,
        can_approve_outcomes=structure.can_approve_outcomes,
        can_unpublish=structure.can_unpublish,
        can_edit_outcome_tags=structure.can_edit_outcome_tags,
    )


@router.get("/curriculum-versions/{version_id}/outcomes", response_model=list[ObjectiveRead])
async def list_programme_outcomes(
    version_id: uuid.UUID, access: Access, db: DbSession
) -> list[ObjectiveRead]:
    """The version's programme outcomes. Needs the whole version to be visible."""
    visible = await visible_version(db, access, version_id)
    if visible is None or not visible.view.full:
        raise _not_found("Curriculum version")
    return _objectives(await programme_outcomes(db, version_id))


@router.get("/modules/{module_id}", response_model=ModuleRead)
async def get_module(module_id: uuid.UUID, access: Access, db: DbSession) -> ModuleRead:
    """A module with its outcomes and the totals of its sessions."""
    detail = await module_detail(db, access, module_id)
    if detail is None:
        raise _not_found("Module")
    module = detail.module
    [hours] = await credit_check.modules_hours(db, [module], await credit_check.credit_policy(db))
    return ModuleRead(
        id=module.id,
        version_id=module.version_id,
        phase_id=module.phase_id,
        code=module.code,
        name=module.name,
        credits=module.credits,
        nqf_level=module.nqf_level,
        description=module.description,
        external_lms_ref=module.external_lms_ref,
        event_count=detail.event_count,
        contact_minutes=detail.contact_minutes,
        self_study_minutes=detail.self_study_minutes,
        outcomes=_objectives(detail.outcomes),
        can_edit_objectives=detail.can_edit_objectives,
        can_approve_objectives=detail.can_approve_objectives,
        tags=item_tag_reads(detail.tags),
        can_edit_tags=detail.can_edit_tags,
        assessments=[
            read_assessment(found)
            for found in await assessment_service.module_assessments(db, module.id)
        ],
        can_edit_assessments=detail.can_edit_assessments,
        hours=ModuleHoursRead(**vars(hours)),
    )


@router.get("/learning-events/{event_id}", response_model=LearningEventRead)
async def get_learning_event(
    event_id: uuid.UUID, access: Access, db: DbSession
) -> LearningEventRead:
    """A session with its objectives."""
    detail = await event_detail(db, access, event_id)
    if detail is None:
        raise _not_found("Learning event")
    event = detail.event
    return LearningEventRead(
        id=event.id,
        module_id=event.module_id,
        title=event.title,
        format=detail.format_label,
        format_value_id=event.format_value_id,
        contact_minutes=event.contact_minutes,
        self_study_minutes=event.self_study_minutes,
        week=event.week,
        position=event.position,
        description=event.description,
        external_lms_ref=event.external_lms_ref,
        objectives=_objectives(detail.objectives),
        can_edit_objectives=detail.can_edit_objectives,
        can_approve_objectives=detail.can_approve_objectives,
        tags=item_tag_reads(detail.tags),
        can_edit_tags=detail.can_edit_tags,
    )
