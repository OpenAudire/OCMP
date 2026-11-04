"""Intentional repeats: items a programme teaches in many sessions on purpose (Slice 1.24a,
ADR 053). Reading needs the report permission, marking needs ``curriculum.edit`` at the
programme. A version the person cannot see is a 404."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.api.v1.curriculum import Access
from app.core.database import DbSession
from app.models import FrameworkItem
from app.services import intended_repeats
from app.services.audit import audit_operation
from app.services.authorization import AuthorizationError
from app.services.curriculum_read import VisibleVersion, visible_version
from app.services.report_access import may_report

router = APIRouter(tags=["reports"])


class MarkIn(BaseModel):
    framework_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=intended_repeats.MAX_REASON)


class MarkRead(BaseModel):
    id: uuid.UUID
    framework_id: uuid.UUID
    code: str
    title: str
    reason: str


class MarksRead(BaseModel):
    can_edit: bool
    marks: list[MarkRead]


async def _visible(
    db: DbSession, access: Access, actor: CurrentUser, version_id: uuid.UUID
) -> VisibleVersion:
    visible = await visible_version(db, access, version_id)
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curriculum version not found.")
    if not await may_report(db, actor, visible):
        raise AuthorizationError("You do not have permission to see reports for this programme.")
    return visible


async def _read(db: DbSession, visible: VisibleVersion, actor: CurrentUser) -> MarksRead:
    marks = await intended_repeats.marked_items(db, visible.programme.id)
    items = {
        i.id: i
        for i in await db.scalars(
            select(FrameworkItem).where(FrameworkItem.id.in_(list(marks) or [uuid.uuid4()]))
        )
    }
    return MarksRead(
        can_edit=await intended_repeats.may_mark(db, actor, visible.programme.id),
        marks=sorted(
            (
                MarkRead(
                    id=row.id,
                    framework_id=items[item_id].framework_id,
                    code=items[item_id].code,
                    title=items[item_id].title,
                    reason=row.reason,
                )
                for item_id, row in marks.items()
            ),
            key=lambda m: m.code,
        ),
    )


@router.get("/curriculum-versions/{version_id}/intended-repeats", response_model=MarksRead)
async def list_marks(
    version_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> MarksRead:
    """The programme's items marked as intentional repeats."""
    return await _read(db, await _visible(db, access, actor, version_id), actor)


@router.post(
    "/curriculum-versions/{version_id}/intended-repeats",
    response_model=MarksRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_mark(
    version_id: uuid.UUID, body: MarkIn, access: Access, actor: CurrentUser, db: DbSession
) -> MarksRead:
    """Mark a framework item as taught repeatedly on purpose (a spiral curriculum)."""
    visible = await _visible(db, access, actor, version_id)
    with audit_operation("reports.intended_repeat_mark", actor_id=actor.id, reason=body.reason):
        await intended_repeats.mark(
            db, actor, visible.programme.id, body.framework_id, body.code, body.reason
        )
    return await _read(db, visible, actor)


@router.delete(
    "/curriculum-versions/{version_id}/intended-repeats/{mark_id}", response_model=MarksRead
)
async def remove_mark(
    version_id: uuid.UUID, mark_id: uuid.UUID, access: Access, actor: CurrentUser, db: DbSession
) -> MarksRead:
    """Remove a mark: the item is listed again when it is taught in many sessions."""
    visible = await _visible(db, access, actor, version_id)
    with audit_operation("reports.intended_repeat_unmark", actor_id=actor.id):
        await intended_repeats.unmark(db, actor, visible.programme.id, mark_id)
    return await _read(db, visible, actor)
