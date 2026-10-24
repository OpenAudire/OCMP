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
from app.models.identity import UserIdentity
from app.models.institution import Department, Faculty, Institution
from app.models.role import Role, RoleAssignment
from app.models.user import User

__all__ = [
    "Base",
    "CoreModel",
    "CurriculumVersion",
    "Department",
    "Faculty",
    "Institution",
    "LearningEvent",
    "Module",
    "Objective",
    "ObjectiveLink",
    "Phase",
    "Programme",
    "QualificationType",
    "Role",
    "RoleAssignment",
    "User",
    "UserIdentity",
]
