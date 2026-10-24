"""SQLAlchemy models package.

Every model must be imported here so Alembic autogenerate sees its table.
"""

from app.models.base import Base, CoreModel
from app.models.curriculum import (
    CurriculumVersion,
    LearningEvent,
    Module,
    Objective,
    ObjectiveLink,
    Phase,
    Programme,
    QualificationType,
)
from app.models.framework import (
    Crosswalk,
    CrosswalkEntry,
    Framework,
    FrameworkCrossRef,
    FrameworkItem,
    TaxonomyLevel,
    TaxonomyScale,
)
from app.models.identity import UserIdentity
from app.models.institution import Department, Faculty, Institution
from app.models.mapping import AIRun, AIRunCall, MappingLink, ReviewAssignment
from app.models.role import Role, RoleAssignment
from app.models.tagging import Tagging, TagList, TagValue
from app.models.user import User

__all__ = [
    "AIRun",
    "AIRunCall",
    "Base",
    "CoreModel",
    "Crosswalk",
    "CrosswalkEntry",
    "CurriculumVersion",
    "Department",
    "Faculty",
    "Framework",
    "FrameworkCrossRef",
    "FrameworkItem",
    "Institution",
    "LearningEvent",
    "MappingLink",
    "Module",
    "Objective",
    "ObjectiveLink",
    "Phase",
    "Programme",
    "QualificationType",
    "ReviewAssignment",
    "Role",
    "RoleAssignment",
    "TagList",
    "TagValue",
    "Tagging",
    "TaxonomyLevel",
    "TaxonomyScale",
    "User",
    "UserIdentity",
]
