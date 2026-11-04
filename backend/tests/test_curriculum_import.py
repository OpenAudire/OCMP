"""Tests for the Excel template and import of curriculum structure and objectives (ADR 054)."""

import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    AuditLog,
    ImportJob,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
)
from app.models.curriculum import VersionStatus
from app.services import curriculum_import
from app.services.authorization import ConflictError
from app.services.curriculum_versions import copy_forward
from app.services.import_fields import (
    INSTRUCTIONS_SHEET,
    LIST_SHEET,
    SHEET_BY_KEY,
    SHEETS,
    Kind,
    Lists,
    build_workbook,
)
from tests.factories import CurriculumVersionFactory
from tests.test_curriculum_edit_api import sign_in
from tests.test_curriculum_objectives_api import World
from tests.test_curriculum_objectives_api import world as world  # fixture

API = "/api/v1"


def book(**rows: list[list[object]]) -> bytes:
    """A workbook from rows (cell values in the order of each sheet's fields)."""
    return build_workbook(Lists(), rows)


def phase(ext: str, name: str, kind: str | None = "year") -> list[object]:
    return [ext, name, kind]


def module(
    ext: str,
    code: str,
    name: str,
    phase_ext: str | None = None,
    credits: object = None,
    nqf: object = None,
    description: str | None = None,
) -> list[object]:
    return [ext, code, name, phase_ext, credits, nqf, description, None]


def session(ext: str, module_ext: str, title: str, contact: object = 60) -> list[object]:
    return [ext, module_ext, title, None, contact, 30, 2, None, None]


def objective(
    ext: str,
    level: str,
    owner: str | None,
    text: str,
    broader: str | None = None,
) -> list[object]:
    return [ext, level, owner, text, None, None, broader]


SMALL = {
    "phases": [phase("P1", "Year 1")],
    "modules": [module("M1", "NEW101", "New module", "P1", credits=12, nqf=5)],
    "sessions": [session("S1", "M1", "First session")],
    "objectives": [
        objective("O1", "programme", None, "Graduates act professionally."),
        objective("O2", "module", "M1", "Explain the basics.", "O1"),
        objective("O3", "session", "S1", "Describe the first idea.", "O2; O1"),
    ],
}


async def run_check(db: AsyncSession, world: World, content: bytes) -> curriculum_import.Plan:
    return await curriculum_import.check(
        db,
        world.draft,
        content,
        max_bytes=10_000_000,
        faculty_id=world.programme.faculty_id,
        default_scale=None,
    )


async def run_apply(db: AsyncSession, world: World, content: bytes, actor) -> object:  # type: ignore[no-untyped-def]
    plan = await run_check(db, world, content)
    assert plan.valid, [p.message for p in plan.problems]
    existing = await curriculum_import.load_existing(
        db, world.draft, world.programme.faculty_id, None
    )
    return await curriculum_import.apply(db, world.draft, plan, existing, actor, can_approve=True)


class TestTemplate:
    def test_the_template_is_made_from_the_field_definitions(self) -> None:
        workbook = load_workbook(io.BytesIO(build_workbook(Lists(formats=("Lecture",)))))

        assert workbook.sheetnames[:2] == [INSTRUCTIONS_SHEET, LIST_SHEET]
        for sheet in SHEETS:
            ws = workbook[sheet.title]
            assert [c.value for c in ws[1]] == [f.header for f in sheet.fields]
        instructions = "\n".join(c.value or "" for c in workbook[INSTRUCTIONS_SHEET]["A"])
        for sheet in SHEETS:
            for f in sheet.fields:
                assert f.header in instructions and f.help.split(".")[0] in instructions

    def test_it_carries_dropdowns_and_number_checks(self) -> None:
        workbook = load_workbook(io.BytesIO(build_workbook(Lists(formats=("Lecture", "Lab")))))

        sessions = workbook["Sessions"]
        kinds = {v.type for v in sessions.data_validations.dataValidation}
        assert kinds == {"whole", "list"}
        formula = next(
            v.formula1 for v in sessions.data_validations.dataValidation if v.type == "list"
        )
        assert formula == "=Lists!$D$2:$D$3"
        listing = workbook[LIST_SHEET]
        assert [c.value for c in listing["D"]][:3] == ["Teaching format", "Lecture", "Lab"]
        modules = workbook["Modules"]
        assert {v.type for v in modules.data_validations.dataValidation} == {"whole", "decimal"}

    def test_every_field_kind_is_checked_or_a_dropdown_or_text(self) -> None:
        for sheet in SHEETS:
            for f in sheet.fields:
                assert f.kind in Kind
        assert SHEET_BY_KEY["objectives"].field("level").required

    def test_text_that_looks_like_a_formula_is_written_as_text(self) -> None:
        content = build_workbook(Lists(formats=("=HYPERLINK(1)",)))

        cell = load_workbook(io.BytesIO(content))[LIST_SHEET]["D2"]

        assert cell.data_type == "s" and cell.value == "=HYPERLINK(1)"


class TestPreview:
    async def test_a_new_structure_is_planned_and_nothing_is_written(
        self, db_session: AsyncSession, world: World
    ) -> None:
        before = await db_session.scalar(select(func.count()).select_from(Module))

        plan = await run_check(db_session, world, book(**SMALL))

        assert plan.valid and plan.changes
        assert plan.counts()["phases"] == {"create": 1, "update": 0, "unchanged": 0}
        assert plan.counts()["objectives"]["create"] == 3
        assert await db_session.scalar(select(func.count()).select_from(Module)) == before

    async def test_problems_name_the_sheet_row_and_column(
        self, db_session: AsyncSession, world: World
    ) -> None:
        content = book(
            phases=[phase("P1", "Year 1"), phase("P1", "Again"), phase("P2", "", "decade")],
            modules=[
                module("M1", "HSC201", "Adopts the existing module"),
                module("M2", "X1", "Bad number", "NOPE", credits="12.55", nqf=11),
                module("M3", "HSC201", "Clashes with the module adopted above"),
            ],
            sessions=[session("S1", "MISSING", "Orphan"), session("S2", "M2", "Bad", "abc")],
        )

        plan = await run_check(db_session, world, content)

        assert not plan.valid
        found = {(p.sheet, p.row, p.column): p.message for p in plan.problems}
        assert "also on row 2" in found[("Phases", 3, "External ID")]
        assert found[("Phases", 4, "Name")] == "Name is required."
        assert "not in the list" in found[("Phases", 4, "Kind")]
        assert "used twice" in found[("Modules", 4, "Code")]
        assert "at most one decimal" in found[("Modules", 3, "Credits")]
        assert found[("Modules", 3, "NQF level")] == "NQF level must be from 1 to 10."
        assert (
            "No module has the External ID 'MISSING'"
            in found[("Sessions", 2, "Module (External ID)")]
        )
        assert (
            found[("Sessions", 3, "Contact minutes")] == "Contact minutes must be a whole number."
        )

    async def test_a_missing_required_column_and_a_wrong_file_are_reported(
        self, db_session: AsyncSession, world: World
    ) -> None:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Modules"
        ws.append(["External ID", "Name"])
        ws.append(["M1", "No code column"])
        out = io.BytesIO()
        wb.save(out)

        missing = await run_check(db_session, world, out.getvalue())
        not_excel = await run_check(db_session, world, b"not a workbook")
        empty = await run_check(db_session, world, build_workbook(Lists()))

        assert any(p.message == "The column 'Code' is missing." for p in missing.problems)
        assert [p.message for p in not_excel.problems] == ["This is not an Excel (.xlsx) workbook."]
        assert [p.message for p in empty.problems] == ["The workbook has no rows to import."]

    async def test_only_a_draft_version_can_be_imported_into(
        self, db_session: AsyncSession, world: World
    ) -> None:
        with pytest.raises(ConflictError):
            await curriculum_import.check(
                db_session,
                world.published,
                book(**SMALL),
                max_bytes=10_000_000,
                faculty_id=world.programme.faculty_id,
                default_scale=None,
            )

    async def test_objective_links_must_go_to_a_broader_objective_of_the_right_place(
        self, db_session: AsyncSession, world: World
    ) -> None:
        content = book(
            modules=[module("M1", "NEW101", "A"), module("M2", "NEW102", "B")],
            sessions=[session("S1", "M1", "In M1")],
            objectives=[
                objective("O2", "module", "M2", "Outcome of M2."),
                objective("O3", "session", "S1", "Objective of S1.", "O2"),
                objective("O4", "programme", "M1", "Programme outcome with an owner."),
                objective("O5", "module", "M1", "Links to nothing known.", "ZZZ"),
            ],
        )

        plan = await run_check(db_session, world, content)

        messages = {(p.row, p.column): p.message for p in plan.problems}
        assert "not a broader objective" in messages[(3, "Broader objectives (External IDs)")]
        assert messages[(4, "Owner (External ID)")] == "A programme outcome has no owner."
        assert (
            "No objective has the External ID 'ZZZ'"
            in messages[(5, "Broader objectives (External IDs)")]
        )


class TestApply:
    async def test_it_makes_everything_with_its_links_and_external_ids(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)

        applied = await run_apply(db_session, world, book(**SMALL), admin)

        module_row = await db_session.scalar(
            select(Module).where(Module.version_id == world.draft.id, Module.external_id == "M1")
        )
        assert module_row is not None and module_row.code == "NEW101"
        assert module_row.phase_id is not None and float(module_row.credits or 0) == 12.0
        event = await db_session.scalar(
            select(LearningEvent).where(LearningEvent.external_id == "S1")
        )
        assert event is not None and event.module_id == module_row.id
        assert (event.contact_minutes, event.self_study_minutes, event.week) == (60, 30, 2)
        o1, o2, o3 = [
            await db_session.scalar(select(Objective).where(Objective.external_id == e))
            for e in ("O1", "O2", "O3")
        ]
        assert o1 and o2 and o3
        links = set(
            await db_session.execute(select(ObjectiveLink.child_id, ObjectiveLink.parent_id))
        )
        assert (o2.id, o1.id) in links and (o3.id, o2.id) in links and (o3.id, o1.id) in links
        assert o3.status.value == "draft"
        assert len(applied.objective_ids) == 3  # type: ignore[attr-defined]
        job = await db_session.scalar(select(ImportJob))
        assert job is not None and job.kind == "curriculum" and job.version_id == world.draft.id
        assert job.summary["objectives"]["create"] == 3
        audit = list(
            await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == module_row.id))
        )
        assert audit  # made through the ORM: audited

    async def test_the_same_file_again_changes_nothing_and_a_changed_row_updates_in_place(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        await run_apply(db_session, world, book(**SMALL), admin)

        again = await run_check(db_session, world, book(**SMALL))
        assert again.valid and not again.changes
        assert all(r.action == "unchanged" for r in again.rows)

        changed = dict(SMALL)
        changed["modules"] = [module("M1", "NEW101", "Renamed", "P1", credits=15, nqf=5)]
        changed["sessions"] = [session("S1", "M1", "First session", contact=90)]
        changed["objectives"] = [
            objective("O1", "programme", None, "Graduates act professionally and ethically."),
            *SMALL["objectives"][1:],
        ]
        await run_apply(db_session, world, book(**changed), admin)

        assert await db_session.scalar(select(func.count()).select_from(Phase)) >= 1
        modules = list(await db_session.scalars(select(Module).where(Module.external_id == "M1")))
        assert len(modules) == 1 and modules[0].name == "Renamed"
        assert float(modules[0].credits or 0) == 15.0
        sessions = list(
            await db_session.scalars(select(LearningEvent).where(LearningEvent.external_id == "S1"))
        )
        assert len(sessions) == 1 and sessions[0].contact_minutes == 90
        o1 = await db_session.scalar(select(Objective).where(Objective.external_id == "O1"))
        assert o1 is not None and o1.text.endswith("and ethically.")
        total = await db_session.scalar(
            select(func.count())
            .select_from(Objective)
            .where(Objective.version_id == world.draft.id, Objective.external_id.is_not(None))
        )
        assert total == 3

    async def test_a_session_or_objective_cannot_be_moved_by_an_import(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        await run_apply(db_session, world, book(**SMALL), admin)
        moved = dict(SMALL)
        moved["modules"] = [*SMALL["modules"], module("M2", "NEW102", "Another")]
        moved["sessions"] = [session("S1", "M2", "First session")]
        moved["objectives"] = [objective("O2", "module", "M2", "Explain the basics.")]

        plan = await run_check(db_session, world, book(**moved))

        messages = [p.message for p in plan.problems]
        assert "A session cannot be moved to another module by an import." in messages
        assert (
            "An import cannot change the level or the owner of an existing objective." in messages
        )

    async def test_a_blank_kept_column_clears_and_a_removed_column_is_left_alone(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        await run_apply(db_session, world, book(**SMALL), admin)
        # The Modules sheet keeps only External ID, Code and Name: the other columns are left alone.
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Modules"
        ws.append(["External ID", "Code", "Name"])
        ws.append(["M1", "NEW101", "New module"])
        out = io.BytesIO()
        wb.save(out)

        plan = await run_check(db_session, world, out.getvalue())
        assert plan.valid and not plan.changes

        cleared = dict(SMALL)
        cleared["modules"] = [module("M1", "NEW101", "New module", None, None, None, None)]
        plan = await run_check(db_session, world, book(**{"modules": cleared["modules"]}))
        [row] = plan.rows
        assert row.action == "update" and set(row.changes) == {"Phase", "Credits", "NQF level"}

    async def test_a_plan_with_problems_is_not_applied(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        plan = await run_check(db_session, world, book(sessions=[session("S1", "X", "Orphan")]))
        existing = await curriculum_import.load_existing(
            db_session, world.draft, world.programme.faculty_id, None
        )

        with pytest.raises(ConflictError):
            await curriculum_import.apply(
                db_session, world.draft, plan, existing, admin, can_approve=True
            )


class TestAdoptingModules:
    async def test_a_module_made_on_the_screens_is_adopted_by_its_code(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        content = book(
            modules=[module("CARDIO", "HSC201", "Cardiovascular system (renamed)")],
            sessions=[session("CS1", "CARDIO", "A session of the adopted module")],
        )

        plan = await run_check(db_session, world, content)

        assert plan.valid
        [row] = [r for r in plan.rows if r.sheet == "modules"]
        assert row.action == "update" and row.changes[0] == "External ID"
        await run_apply(db_session, world, content, admin)
        await db_session.refresh(world.cardio)
        assert world.cardio.external_id == "CARDIO" and world.cardio.name.endswith("(renamed)")
        event = await db_session.scalar(
            select(LearningEvent).where(LearningEvent.external_id == "CS1")
        )
        assert event is not None and event.module_id == world.cardio.id
        again = await run_check(db_session, world, content)
        assert again.valid and not again.changes

    async def test_a_code_held_by_a_module_with_another_external_id_is_still_a_clash(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        await run_apply(db_session, world, book(modules=[module("A", "HSC201", "Adopted")]), admin)

        plan = await run_check(db_session, world, book(modules=[module("B", "HSC201", "Clash")]))

        assert [p.message for p in plan.problems] == ["The code HSC201 is used twice."]


class TestCopyForward:
    async def test_external_ids_are_copied_to_the_next_year_but_not_by_duplicating_a_module(
        self, db_session: AsyncSession, world: World
    ) -> None:
        admin = await sign_in_user(db_session)
        await run_apply(db_session, world, book(**SMALL), admin)

        forward = await copy_forward(db_session, admin, world.draft, academic_year=2031)

        modules = list(
            await db_session.scalars(select(Module).where(Module.version_id == forward.id))
        )
        assert "M1" in {m.external_id for m in modules}
        objectives = list(
            await db_session.scalars(select(Objective).where(Objective.version_id == forward.id))
        )
        assert {"O1", "O2", "O3"} <= {o.external_id for o in objectives}
        phases = list(await db_session.scalars(select(Phase).where(Phase.version_id == forward.id)))
        assert "P1" in {p.external_id for p in phases}


class TestApi:
    async def test_template_preview_and_apply_through_the_api(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        base = f"{API}/curriculum-versions/{world.draft.id}/import"

        template = await api_client.get(f"{base}/template")
        assert template.status_code == 200
        assert template.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert load_workbook(io.BytesIO(template.content)).sheetnames[0] == INSTRUCTIONS_SHEET

        preview = await api_client.post(f"{base}/preview", content=book(**SMALL))
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["valid"] and body["would_change"] and body["token"]
        assert body["counts"]["objectives"]["create"] == 3
        assert {r["action"] for r in body["rows"]} == {"create"}
        # The dry run wrote nothing.
        assert (
            await db_session.scalar(
                select(func.count()).select_from(Module).where(Module.external_id == "M1")
            )
            == 0
        )

        applied = await api_client.post(f"{base}/apply", json={"token": body["token"]})
        assert applied.status_code == 200, applied.text
        assert applied.json()["counts"]["modules"]["create"] == 1
        assert (
            await db_session.scalar(
                select(func.count()).select_from(Module).where(Module.external_id == "M1")
            )
            == 1
        )
        # The token is single use.
        again = await api_client.post(f"{base}/apply", json={"token": body["token"]})
        assert again.status_code == 422

    async def test_a_file_with_problems_gets_no_token(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        base = f"{API}/curriculum-versions/{world.draft.id}/import"

        response = await api_client.post(
            f"{base}/preview", content=book(sessions=[session("S1", "X", "Orphan")])
        )

        body = response.json()
        assert response.status_code == 200 and body["valid"] is False and body["token"] is None
        assert body["problems"][0]["sheet"] == "Sessions" and body["problems"][0]["row"] == 2

    async def test_a_published_version_and_an_unseen_one_are_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        published = await api_client.post(
            f"{API}/curriculum-versions/{world.published.id}/import/preview", content=book(**SMALL)
        )
        unseen = await api_client.get(
            f"{API}/curriculum-versions/{world.cardio.id}/import/template"
        )

        assert published.status_code == 409
        assert unseen.status_code == 404

    async def test_someone_without_edit_rights_may_not_import(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "student")
        base = f"{API}/curriculum-versions/{world.draft.id}/import"

        preview = await api_client.post(f"{base}/preview", content=book(**SMALL))
        template = await api_client.get(f"{base}/template")

        assert preview.status_code in (403, 404) and template.status_code in (403, 404)

    async def test_the_preview_of_another_version_or_user_cannot_be_applied(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        world: World,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "platform_admin")
        other = CurriculumVersionFactory(
            programme=world.programme, academic_year=2040, status=VersionStatus.DRAFT
        )
        db_session.add(other)
        await db_session.flush()
        base = f"{API}/curriculum-versions/{world.draft.id}/import"
        token = (await api_client.post(f"{base}/preview", content=book(**SMALL))).json()["token"]

        wrong = await api_client.post(
            f"{API}/curriculum-versions/{other.id}/import/apply", json={"token": token}
        )

        assert wrong.status_code == 422


async def sign_in_user(db: AsyncSession):  # type: ignore[no-untyped-def]
    from app.models import User
    from tests.authz_helpers import grant

    user = User(email="importer@example.org", display_name="Importer", is_active=True)
    db.add(user)
    await db.flush()
    await grant(db, user, "platform_admin")
    return user
