"""The rules of the role balance report (Slice 1.24a, ADR 053), as pure functions.

* Each objective of a session gets an **equal share** of the session's contact time; that share is
  divided among the framework groups the objective maps to.
* An objective whose own accepted mappings give no group is **estimated** from the mappings of the
  module outcomes it links up to; only when it has no upward links at all, from the mappings of the
  outcomes of its module. A session with no objective is estimated from its module's outcomes.
* Whatever is not found is "not mapped".
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    """The groups an objective counts for, and whether they are estimated rather than its own."""

    groups: frozenset[uuid.UUID]
    estimated: bool


NOTHING = Resolution(frozenset(), False)


def resolve(
    own: Collection[uuid.UUID],
    parents: Sequence[Collection[uuid.UUID]] | None,
    module_outcomes: Collection[uuid.UUID],
) -> Resolution:
    """``own``: groups of the objective's accepted links. ``parents``: for each module outcome it
    links up to, that outcome's groups (``None``/empty list when it has no upward link).
    ``module_outcomes``: groups of all outcomes of its module."""
    if own:
        return Resolution(frozenset(own), False)
    if parents:
        found = frozenset().union(*parents)
        return Resolution(found, True) if found else NOTHING
    if module_outcomes:
        return Resolution(frozenset(module_outcomes), True)
    return NOTHING


def split_minutes(
    minutes: float, resolutions: Sequence[Resolution]
) -> list[tuple[uuid.UUID | None, float, bool]]:
    """(group or ``None`` for not mapped, minutes, estimated) for one session: ``minutes`` divided
    equally over its objectives, each share divided equally over that objective's groups."""
    if not resolutions or minutes <= 0:
        return []
    share = minutes / len(resolutions)
    out: list[tuple[uuid.UUID | None, float, bool]] = []
    for resolution in resolutions:
        if not resolution.groups:
            out.append((None, share, False))
            continue
        part = share / len(resolution.groups)
        out.extend((group, part, resolution.estimated) for group in sorted(resolution.groups))
    return out
