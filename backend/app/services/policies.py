"""Institution policies stored in ``institutions.settings``.

Settings are JSON so administrators can change them without migrations; this
module gives each group of settings a typed, validated shape with defaults.
"""

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CurriculumVersion, Faculty, Institution, Objective, Programme
from app.services.authorization import InvalidRequestError


class MappingPolicy(BaseModel):
    """How mapping decisions are reviewed (``settings["mapping"]``)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    # Accepted links need a second, different reviewer before they count.
    four_eyes: bool = False
    # Rejections also need a second reviewer (by default a first reject is final).
    second_review_for_rejects: bool = False


def parse_mapping_policy(settings: dict[str, object]) -> MappingPolicy:
    """Read the mapping policy from an institution's settings.

    Raises:
        InvalidRequestError: If the stored settings have the wrong shape.
    """
    try:
        return MappingPolicy.model_validate(settings.get("mapping") or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid mapping settings: {exc}") from exc


async def mapping_policy_for(db: AsyncSession, objective: Objective) -> MappingPolicy:
    """The mapping policy of the institution an objective belongs to."""
    settings = await db.scalar(
        select(Institution.settings)
        .join(Faculty, Faculty.institution_id == Institution.id)
        .join(Programme, Programme.faculty_id == Faculty.id)
        .join(CurriculumVersion, CurriculumVersion.programme_id == Programme.id)
        .where(CurriculumVersion.id == objective.version_id)
    )
    return parse_mapping_policy(settings or {})
