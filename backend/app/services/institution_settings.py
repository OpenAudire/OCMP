"""Typed access to ``institutions.settings``: terminology, profiles, taxonomy, mapping, credits.

Each section is validated with defaults. Updates replace whole sections and
keep any keys this version does not know about, so newer settings survive.
OCMP runs one institution per instance (created by the setup wizard).
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.profiles import Feature, Profile, Term, features_for
from app.models import Institution, TaxonomyScale
from app.services.authorization import InvalidRequestError
from app.services.policies import CreditPolicy, MappingPolicy

Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class TermOverride(BaseModel):
    """The institution's own word for a term."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    singular: Word
    plural: Word


class InstitutionSettings(BaseModel):
    """All settings sections, with defaults."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    terminology: dict[Term, TermOverride] = {}
    profiles: frozenset[Profile] = frozenset({Profile.CORE})
    default_taxonomy_scale: str | None = None
    mapping: MappingPolicy = MappingPolicy()
    credits: CreditPolicy = CreditPolicy()

    @field_validator("profiles", mode="after")
    @classmethod
    def core_is_always_on(cls, value: frozenset[Profile]) -> frozenset[Profile]:
        return value | {Profile.CORE}

    @property
    def features(self) -> frozenset[Feature]:
        return features_for(self.profiles)

    def section(self, name: str) -> Any:
        """A section as stored in JSON."""
        value = getattr(self, name)
        if name == "profiles":
            return sorted(p.value for p in value)
        if name == "terminology":
            return {term.value: o.model_dump() for term, o in sorted(value.items())}
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value


SECTIONS = ("terminology", "profiles", "default_taxonomy_scale", "mapping", "credits")


def parse_settings(raw: dict[str, Any]) -> InstitutionSettings:
    """Validate stored settings.

    Raises:
        InvalidRequestError: If a stored section has the wrong shape.
    """
    try:
        return InstitutionSettings.model_validate(raw or {})
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid institution settings: {exc}") from exc


async def get_institution(db: AsyncSession) -> Institution | None:
    """The institution of this instance (the first created, if there are several)."""
    result = await db.execute(
        select(Institution)
        .where(Institution.deleted_at.is_(None))
        .order_by(Institution.created_at, Institution.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_settings(
    db: AsyncSession, institution: Institution, changes: dict[str, Any]
) -> InstitutionSettings:
    """Replace the given settings sections (``changes`` maps section name to new value).

    Raises:
        InvalidRequestError: For unknown sections, invalid values, or an unknown
            default taxonomy scale.
    """
    unknown = set(changes) - set(SECTIONS)
    if unknown:
        raise InvalidRequestError(f"Unknown settings sections: {', '.join(sorted(unknown))}.")
    merged = {**(institution.settings or {}), **changes}
    settings = parse_settings(merged)

    scale = settings.default_taxonomy_scale
    if "default_taxonomy_scale" in changes and scale is not None:
        exists = await db.scalar(select(TaxonomyScale.id).where(TaxonomyScale.key == scale))
        if not exists:
            raise InvalidRequestError(f"No taxonomy scale with key '{scale}'.")

    # Assign a new dict so the change is detected (and audited).
    institution.settings = {
        **(institution.settings or {}),
        **{name: settings.section(name) for name in changes},
    }
    await db.flush()
    return settings
