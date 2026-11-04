"""What a report builder is given (Slices 1.22 to 1.24, ADR 051)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Framework
from app.models.framework import FrameworkStatus
from app.services.authorization import InvalidRequestError
from app.services.coverage_engine import Method
from app.services.curriculum_read import VisibleVersion
from app.services.policies import CoveragePolicy
from app.services.report_export import ReportDoc


@dataclass
class ReportContext:
    """The database, what the user may see, the institution's numbers and the choices made on
    the screen."""

    db: AsyncSession
    visible: VisibleVersion
    policy: CoveragePolicy
    framework_id: uuid.UUID | None = None
    method: Method = Method.SINGLE
    phase_id: uuid.UUID | None = None

    async def framework(self) -> Framework:
        """The chosen framework.

        Raises:
            InvalidRequestError: If none was chosen or it cannot be used.
        """
        if self.framework_id is None:
            raise InvalidRequestError("Choose a framework for this report.")
        framework = await self.db.get(Framework, self.framework_id)
        if framework is None or framework.is_deleted or framework.status == FrameworkStatus.DRAFT:
            raise InvalidRequestError("That framework cannot be used for a report.")
        return framework

    async def optional_framework(self) -> Framework | None:
        return await self.framework() if self.framework_id is not None else None


Builder = Callable[[ReportContext], Awaitable[ReportDoc]]


def common_about(
    visible: VisibleVersion, made_on_text: str, partial: bool
) -> list[tuple[str, str]]:
    """The lines every report starts with: the version, the time and what is counted."""
    version = visible.version
    lines = [
        (
            "Curriculum version",
            f"{visible.programme.code} {visible.programme.name}, {version.academic_year} "
            f"({version.status.value})",
        ),
        ("Made on", made_on_text),
        (
            "What is counted",
            "Only objectives and sessions you may see. Only accepted mapping links count; "
            "suggestions and links waiting for review are not mapping.",
        ),
    ]
    if partial:
        lines.append(
            (
                "Only part of the curriculum",
                "This report covers only the part of the curriculum its reader can see.",
            )
        )
    return lines
