"""The institution's settings: terminology, profiles, taxonomy, mapping and credit policies."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, require_permission
from app.core.database import DbSession
from app.core.permissions import Permission
from app.core.profiles import Feature, Profile, Term
from app.models import Institution, User
from app.services.institution_settings import (
    InstitutionSettings,
    TermOverride,
    get_institution,
    parse_settings,
    update_settings,
)
from app.services.policies import (
    CoveragePolicy,
    CreditPolicy,
    ExplorerPolicy,
    MappingPolicy,
    QualityPolicy,
)

router = APIRouter(prefix="/institution", tags=["institution"])

SettingsManager = Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))]


class InstitutionRead(BaseModel):
    """What the UI needs to label and shape itself for this institution."""

    id: uuid.UUID
    name: str
    short_code: str
    country: str
    # Overrides only; the UI falls back to its own translations for other terms.
    terminology: dict[Term, TermOverride]
    profiles: list[Profile]
    features: list[Feature]
    default_taxonomy_scale: str | None
    mapping: MappingPolicy
    credits: CreditPolicy
    quality: QualityPolicy
    coverage: CoveragePolicy
    explorer: ExplorerPolicy


class SettingsUpdate(BaseModel):
    """Sections to replace; sections left out are unchanged. Send null to clear one."""

    model_config = ConfigDict(extra="forbid")

    terminology: dict[Term, TermOverride] | None = None
    profiles: list[Profile] | None = None
    default_taxonomy_scale: str | None = None
    mapping: MappingPolicy | None = None
    credits: CreditPolicy | None = None
    quality: QualityPolicy | None = None
    coverage: CoveragePolicy | None = None
    explorer: ExplorerPolicy | None = None


def _read(institution: Institution, settings: InstitutionSettings) -> InstitutionRead:
    return InstitutionRead(
        id=institution.id,
        name=institution.name,
        short_code=institution.short_code,
        country=institution.country,
        terminology=settings.terminology,
        profiles=sorted(settings.profiles),
        features=sorted(settings.features),
        default_taxonomy_scale=settings.default_taxonomy_scale,
        mapping=settings.mapping,
        credits=settings.credits,
        quality=settings.quality,
        coverage=settings.coverage,
        explorer=settings.explorer,
    )


async def _institution_or_404(db: DbSession) -> Institution:
    institution = await get_institution(db)
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The institution is not set up yet."
        )
    return institution


@router.get("", response_model=InstitutionRead)
async def get_current_institution(_user: CurrentUser, db: DbSession) -> InstitutionRead:
    """The institution, its terminology, profiles and enabled features."""
    institution = await _institution_or_404(db)
    return _read(institution, parse_settings(institution.settings))


@router.patch("/settings", response_model=InstitutionRead)
async def change_settings(
    body: SettingsUpdate, _manager: SettingsManager, db: DbSession
) -> InstitutionRead:
    """Replace settings sections. Changes are recorded in the audit log."""
    institution = await _institution_or_404(db)
    changes: dict[str, Any] = {}
    for name in body.model_fields_set:
        value = getattr(body, name)
        if value is None:
            # Clearing a section restores its default.
            changes[name] = InstitutionSettings().section(name)
        elif isinstance(value, BaseModel):
            changes[name] = value.model_dump()
        elif name == "terminology":
            changes[name] = {term.value: o.model_dump() for term, o in value.items()}
        elif name == "profiles":
            changes[name] = [p.value for p in value]
        else:
            changes[name] = value
    settings = await update_settings(db, institution, changes)
    return _read(institution, settings)
