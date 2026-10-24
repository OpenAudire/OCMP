"""Feature profiles, configurable terms, and what each profile switches on.

The core profile is always on and covers the whole discipline-neutral
platform. Optional profiles add discipline-specific features on top.
"""

from enum import StrEnum


class Profile(StrEnum):
    CORE = "core"
    HEALTH = "health"  # health sciences


class Feature(StrEnum):
    """Features that only some profiles enable (everything else is core)."""

    # Share of teaching time and objectives per top-level framework group per phase.
    ROLE_BALANCE_REPORT = "role_balance_report"
    # Evidence pack layout aimed at professional council (e.g. HPCSA) reviews.
    COUNCIL_EVIDENCE_PACK = "council_evidence_pack"
    # Clinical placements and patient/case availability per site (phase 3).
    CLINICAL_PLACEMENTS = "clinical_placements"


PROFILE_FEATURES: dict[Profile, frozenset[Feature]] = {
    Profile.CORE: frozenset(),
    Profile.HEALTH: frozenset(
        {Feature.ROLE_BALANCE_REPORT, Feature.COUNCIL_EVIDENCE_PACK, Feature.CLINICAL_PLACEMENTS}
    ),
}


def features_for(profiles: frozenset[Profile] | set[Profile]) -> frozenset[Feature]:
    """All features enabled by a set of profiles."""
    enabled: set[Feature] = set()
    for profile in profiles:
        enabled |= PROFILE_FEATURES[profile]
    return frozenset(enabled)


class Term(StrEnum):
    """Curriculum words an institution can rename (e.g. module -> course).

    Default wording lives in the frontend translations (``terms.<key>_one`` /
    ``terms.<key>_other``); institutions store overrides only.
    """

    PROGRAMME = "programme"
    CURRICULUM_VERSION = "curriculum_version"
    PHASE = "phase"
    MODULE = "module"
    LEARNING_EVENT = "learning_event"
    OBJECTIVE = "objective"
    FRAMEWORK = "framework"
    FRAMEWORK_ITEM = "framework_item"
