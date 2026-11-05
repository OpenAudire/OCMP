"""SQLAlchemy models package.

Every model must be imported here so Alembic autogenerate sees its table.
"""

from app.models.ai_settings import AIProviderConfig, AISettings
from app.models.api_token import ApiToken
from app.models.assessment import Assessment, AssessmentItem, AssessmentItemObjective
from app.models.audit import AuditLog
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
from app.models.embedding import Embedding, ObjectiveSimilarity
from app.models.evaluation import EvalRun, GoldCase, GoldLink, GoldSet
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
from app.models.import_job import ImportJob
from app.models.institution import Department, Faculty, Institution
from app.models.intended_repeat import IntendedRepeat
from app.models.mapping import AIRun, AIRunCall, MappingLink, ReviewAssignment
from app.models.metrics import MetricSnapshot
from app.models.proposal import ObjectiveProposal, ProposalStatus
from app.models.role import Role, RoleAssignment
from app.models.tagging import Tagging, TagList, TagValue
from app.models.user import User

__all__ = [
    "AIProviderConfig",
    "AIRun",
    "AIRunCall",
    "AISettings",
    "ApiToken",
    "Assessment",
    "AssessmentItem",
    "AssessmentItemObjective",
    "AuditLog",
    "Base",
    "CoreModel",
    "Crosswalk",
    "CrosswalkEntry",
    "CurriculumVersion",
    "Department",
    "Embedding",
    "EvalRun",
    "Faculty",
    "Framework",
    "FrameworkCrossRef",
    "FrameworkItem",
    "GoldCase",
    "GoldLink",
    "GoldSet",
    "ImportJob",
    "Institution",
    "IntendedRepeat",
    "LearningEvent",
    "MappingLink",
    "MetricSnapshot",
    "Module",
    "Objective",
    "ObjectiveLink",
    "ObjectiveProposal",
    "ObjectiveSimilarity",
    "Phase",
    "Programme",
    "ProposalStatus",
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
