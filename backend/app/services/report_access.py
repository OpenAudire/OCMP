"""Who may read the reports of a version (Slices 1.21 and 1.22)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, ScopeType
from app.models import User
from app.services.authorization import ScopeRef, has_permission
from app.services.curriculum_read import VisibleVersion


async def may_report(db: AsyncSession, actor: User, visible: VisibleVersion) -> bool:
    """``reports.view`` at the programme, or (for a narrower view) at a module of it: then the
    report covers only the modules that person sees."""
    programme = ScopeRef(ScopeType.PROGRAMME, visible.programme.id)
    if await has_permission(db, actor, Permission.REPORTS_VIEW, programme):
        return True
    return not visible.view.full and any(
        [
            await has_permission(db, actor, Permission.REPORTS_VIEW, ScopeRef(ScopeType.MODULE, m))
            for m in visible.view.modules
        ]
    )
