"""Permissions and the built-in (system) roles.

Permissions are defined in code because endpoints check them. Roles are rows
in the database: the system roles below are synced from this module (see
``sync_system_roles``), and administrators can add custom roles made of any
of these permissions.
"""

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    """Everything an endpoint can require."""

    # Instance administration
    SETTINGS_MANAGE = "settings.manage"  # SSO, AI provider, integrations, terminology, profiles
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"  # define custom roles
    ROLES_ASSIGN = "roles.assign"  # grant roles within one's scope
    AUDIT_VIEW = "audit.view"  # read the audit log

    # Curriculum
    CURRICULUM_VIEW = "curriculum.view"  # including drafts
    CURRICULUM_VIEW_PUBLISHED = "curriculum.view_published"
    CURRICULUM_EDIT = "curriculum.edit"  # programmes, phases, modules, learning events
    CURRICULUM_PUBLISH = "curriculum.publish"  # publish curriculum versions
    OBJECTIVES_EDIT = "objectives.edit"

    # Frameworks and tag lists
    FRAMEWORKS_MANAGE = "frameworks.manage"
    TAGLISTS_MANAGE = "taglists.manage"
    TAGGING_EDIT = "tagging.edit"

    # Mapping
    MAPPING_EDIT = "mapping.edit"
    MAPPING_REVIEW = "mapping.review"
    MAPPING_SECOND_REVIEW = "mapping.second_review"
    AI_RUN = "ai.run"

    # Reporting
    REPORTS_VIEW = "reports.view"
    EVIDENCE_VIEW = "evidence.view"


# Holding the key permission also grants the listed ones.
IMPLIED: dict[Permission, frozenset[Permission]] = {
    Permission.CURRICULUM_VIEW: frozenset({Permission.CURRICULUM_VIEW_PUBLISHED}),
}


def expand(permissions: frozenset[Permission] | set[Permission]) -> frozenset[Permission]:
    """Permissions plus everything they imply."""
    result = set(permissions)
    for permission in permissions:
        result |= IMPLIED.get(permission, frozenset())
    return frozenset(result)


class ScopeType(StrEnum):
    """Levels at which a role can be assigned, from broadest to narrowest."""

    INSTANCE = "instance"
    FACULTY = "faculty"
    PROGRAMME = "programme"
    MODULE = "module"
    LEARNING_EVENT = "learning_event"


@dataclass(frozen=True)
class SystemRole:
    key: str
    name: str
    description: str
    permissions: frozenset[Permission]
    scope_types: frozenset[ScopeType]
    requires_expiry: bool = False


P = Permission
S = ScopeType

_CURRICULUM_LEADERSHIP = frozenset(
    {
        P.CURRICULUM_VIEW,
        P.CURRICULUM_EDIT,
        P.CURRICULUM_PUBLISH,
        P.OBJECTIVES_EDIT,
        P.TAGGING_EDIT,
        P.MAPPING_EDIT,
        P.MAPPING_REVIEW,
        P.MAPPING_SECOND_REVIEW,
        P.AI_RUN,
        P.REPORTS_VIEW,
        P.EVIDENCE_VIEW,
        P.ROLES_ASSIGN,
    }
)

# The roles from the project brief (section 4).
SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        key="platform_admin",
        name="Platform admin",
        description="Install settings, SSO, AI provider, integrations, users and roles.",
        permissions=frozenset(Permission),
        scope_types=frozenset({S.INSTANCE}),
    ),
    SystemRole(
        key="curriculum_office",
        name="Curriculum office",
        description="Manage frameworks, tag lists, curriculum versions and all reports.",
        permissions=_CURRICULUM_LEADERSHIP | {P.FRAMEWORKS_MANAGE, P.TAGLISTS_MANAGE},
        scope_types=frozenset({S.INSTANCE, S.FACULTY}),
    ),
    SystemRole(
        key="programme_director",
        name="Programme director",
        description="Programme outcomes and structure, coverage review, publishing versions.",
        permissions=_CURRICULUM_LEADERSHIP,
        scope_types=frozenset({S.PROGRAMME}),
    ),
    SystemRole(
        key="module_coordinator",
        name="Module coordinator",
        description="Modules, learning events, objectives, mapping and AI suggestion review.",
        permissions=frozenset(
            {
                P.CURRICULUM_VIEW,
                P.CURRICULUM_EDIT,
                P.OBJECTIVES_EDIT,
                P.TAGGING_EDIT,
                P.MAPPING_EDIT,
                P.MAPPING_REVIEW,
                P.AI_RUN,
                P.REPORTS_VIEW,
            }
        ),
        scope_types=frozenset({S.MODULE}),
    ),
    SystemRole(
        key="lecturer",
        name="Lecturer / facilitator",
        description="Edit the objectives of their own sessions and view their schedule.",
        permissions=frozenset({P.CURRICULUM_VIEW, P.OBJECTIVES_EDIT}),
        scope_types=frozenset({S.MODULE, S.LEARNING_EVENT}),
    ),
    SystemRole(
        key="mapper",
        name="Mapper / reviewer",
        description="Create and review mappings (first and second review).",
        permissions=frozenset(
            {P.CURRICULUM_VIEW, P.MAPPING_EDIT, P.MAPPING_REVIEW, P.MAPPING_SECOND_REVIEW}
        ),
        scope_types=frozenset({S.PROGRAMME, S.MODULE}),
    ),
    SystemRole(
        key="student",
        name="Student",
        description="Read-only curriculum explorer and search over published content.",
        permissions=frozenset({P.CURRICULUM_VIEW_PUBLISHED}),
        scope_types=frozenset({S.INSTANCE, S.PROGRAMME}),
    ),
    SystemRole(
        key="external_reviewer",
        name="External reviewer",
        description="Time-limited read-only access to evidence packs of selected programmes.",
        permissions=frozenset({P.CURRICULUM_VIEW_PUBLISHED, P.REPORTS_VIEW, P.EVIDENCE_VIEW}),
        scope_types=frozenset({S.PROGRAMME}),
        requires_expiry=True,
    ),
)

SYSTEM_ROLE_KEYS = frozenset(role.key for role in SYSTEM_ROLES)
