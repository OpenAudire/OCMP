"""Remove the fictional demo data (Slice 1.30): ``python -m app.cli remove-demo``.

Only what the demo dataset itself made is touched, found by the demo's own codes and keys (the
programme code, the faculty code, the framework key and version, the tag list keys, the curriculum
office account's address and the gold set's name), so real data with other codes is never in its
way. Everything goes through the ORM, so it is audited (``demo.remove``). It is a **dry run**
unless told to apply: the removal is carried out inside a savepoint that is rolled back, so the
list is exactly what would happen.

What goes: the demo programme with all its versions and what is in them (structure, objectives,
mapping links, assessments, tags, role assignments held in it, daily figures); the demo faculty when
no other programme is in it; the demo framework when nothing else is mapped to it; the demo tag
lists when nothing else uses them (a list in use is made inactive instead); the demo curriculum
office account; the demo gold set. What stays: the institution and the taxonomy scales, which a
real installation shares.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.loader import DATA_DIR, DemoData, load_data
from app.models import (
    CurriculumVersion,
    Department,
    Faculty,
    Framework,
    GoldSet,
    LearningEvent,
    MetricSnapshot,
    Module,
    Objective,
    Programme,
    RoleAssignment,
    Tagging,
    TagList,
)
from app.models.tagging import TagValue
from app.services import curriculum_versions, tagging
from app.services.audit import audit_operation
from app.services.authorization import ConflictError
from app.services.frameworks import delete_framework
from app.services.packs import load_pack_file
from app.services.users import delete_user, get_user_by_email


@dataclass
class RemovalReport:
    """What was (or would be) removed, and what was left and why."""

    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    @property
    def nothing(self) -> bool:
        return not self.removed


async def _programme_scopes(db: AsyncSession, programme: Programme) -> list[RoleAssignment]:
    modules = select(Module.id).where(
        Module.version_id.in_(
            select(CurriculumVersion.id).where(CurriculumVersion.programme_id == programme.id)
        )
    )
    events = select(LearningEvent.id).where(LearningEvent.module_id.in_(modules))
    return list(
        await db.scalars(
            select(RoleAssignment).where(
                or_(
                    (RoleAssignment.scope_type == "programme")
                    & (RoleAssignment.scope_id == programme.id),
                    (RoleAssignment.scope_type == "module") & RoleAssignment.scope_id.in_(modules),
                    (RoleAssignment.scope_type == "learning_event")
                    & RoleAssignment.scope_id.in_(events),
                )
            )
        )
    )


async def _remove_programme(db: AsyncSession, programme: Programme, report: RemovalReport) -> None:
    versions = list(
        await db.scalars(
            select(CurriculumVersion).where(
                CurriculumVersion.programme_id == programme.id,
                CurriculumVersion.deleted_at.is_(None),
            )
        )
    )
    assignments = await _programme_scopes(db, programme)
    report.removed.append(
        f"programme {programme.code} with {len(versions)} versions and "
        f"{len(assignments)} role assignments held in it"
    )
    for assignment in assignments:
        await db.delete(assignment)
    for row in await db.scalars(select(Tagging).where(Tagging.programme_id == programme.id)):
        await db.delete(row)
    for version in versions:
        item_ids: dict[str, list] = {  # type: ignore[type-arg]
            "module_id": list(
                await db.scalars(select(Module.id).where(Module.version_id == version.id))
            ),
            "objective_id": list(
                await db.scalars(select(Objective.id).where(Objective.version_id == version.id))
            ),
        }
        item_ids["learning_event_id"] = list(
            await db.scalars(
                select(LearningEvent.id).where(LearningEvent.module_id.in_(item_ids["module_id"]))
            )
        )
        for column, ids in item_ids.items():
            if ids:
                for row in await db.scalars(
                    select(Tagging).where(getattr(Tagging, column).in_(ids))
                ):
                    await db.delete(row)
        await curriculum_versions.soft_delete_version(db, version)
        await db.execute(delete(MetricSnapshot).where(MetricSnapshot.version_id == version.id))
    programme.soft_delete()
    await db.flush()


async def remove_demo(
    db: AsyncSession, data: DemoData | None = None, *, apply: bool = False
) -> RemovalReport:
    """Remove (or, without ``apply``, list) the demo data. See the module docstring."""
    data = data or load_data()
    report = RemovalReport()
    savepoint = await db.begin_nested()
    try:
        await _remove(db, data, report)
    except BaseException:
        await savepoint.rollback()
        raise
    if apply:
        await savepoint.commit()
    else:
        await savepoint.rollback()
    return report


async def _remove(db: AsyncSession, data: DemoData, report: RemovalReport) -> None:
    with audit_operation("demo.remove"):
        programme = await db.scalar(
            select(Programme).where(
                Programme.code == data.programme.code, Programme.deleted_at.is_(None)
            )
        )
        if programme is not None:
            await _remove_programme(db, programme, report)

        faculty = await db.scalar(
            select(Faculty).where(Faculty.code == data.faculty.code, Faculty.deleted_at.is_(None))
        )
        if faculty is not None:
            others = await db.scalar(
                select(Programme.id)
                .where(
                    Programme.faculty_id == faculty.id,
                    Programme.deleted_at.is_(None),
                    Programme.id != (programme.id if programme else None),
                )
                .limit(1)
            )
            if others is not None:
                report.kept.append(f"faculty {faculty.code}: other programmes are in it")
            else:
                report.removed.append(f"faculty {faculty.code} and its department")
                for department in await db.scalars(
                    select(Department).where(
                        Department.faculty_id == faculty.id, Department.deleted_at.is_(None)
                    )
                ):
                    department.soft_delete()
                faculty.soft_delete()
                await db.flush()

        pack = load_pack_file(DATA_DIR / data.framework_pack)
        framework = await db.scalar(
            select(Framework).where(
                Framework.key == pack.metadata.key,
                Framework.version_label == pack.metadata.version,
                Framework.deleted_at.is_(None),
            )
        )
        if framework is not None:
            try:
                await delete_framework(db, framework)
                report.removed.append(f"framework {framework.name} {framework.version_label}")
            except ConflictError as exc:
                report.kept.append(f"framework {framework.name}: {exc}")

        for raw in data.tag_lists:
            tag_list = await db.scalar(
                select(TagList).where(TagList.key == raw.key, TagList.deleted_at.is_(None))
            )
            if tag_list is None:
                continue
            values = list(
                await db.scalars(
                    select(TagValue.id).where(
                        TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
                    )
                )
            )
            in_use = any((await tagging.value_usage(db, values)).values())
            if in_use:
                report.kept.append(
                    f"tag list {tag_list.key}: still used by tags or sessions outside the demo"
                )
                continue
            report.removed.append(f"tag list {tag_list.key}")
            await tagging.delete_tag_list(db, tag_list)

        if data.office_user is not None:
            user = await get_user_by_email(db, data.office_user.email)
            if user is not None and not user.is_deleted:
                report.removed.append("the demo curriculum-office account")
                await delete_user(db, user)

        gold_name = json.loads((DATA_DIR / "gold-set-demo.json").read_text(encoding="utf-8"))[
            "name"
        ]
        gold = await db.scalar(
            select(GoldSet).where(GoldSet.name == gold_name, GoldSet.deleted_at.is_(None))
        )
        if gold is not None:
            report.removed.append("the demo gold set")
            gold.soft_delete()
        await db.flush()
