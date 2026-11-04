"""The gold sets and evaluation runs of the AI mapping evaluation harness (Slice 1.19, ADR 048).

A **gold set** is a list of objectives with the framework items a person says they map to
(coverage 0 to 5 and depth). It holds curriculum wording and codes only, never personal data.
An **evaluation run** asks the AI to map those objectives (nothing is saved as a link) and keeps
what the AI answered, so that precision, recall and Cohen's kappa can be worked out at any
threshold afterwards without paying for another run.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel, SoftDeleteMixin, live_unique, str_enum
from app.models.mapping import DepthMatch


class GoldSet(Audited, SoftDeleteMixin, CoreModel):
    """A named set of objectives with the mappings a person decided are right."""

    __tablename__ = "gold_sets"
    __table_args__ = (live_unique("uq_gold_sets_name_live", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    framework_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frameworks.id", ondelete="RESTRICT"), index=True
    )
    # True for a set written for the demo data: it shows how the harness works and is not a
    # measure of anything (the demo set was written by the developers, not by a panel).
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")


class GoldCase(Audited, CoreModel):
    """One objective of a gold set. It may have no mapping rows: a person decided it maps to
    nothing in the framework."""

    __tablename__ = "gold_cases"
    __table_args__ = (UniqueConstraint("gold_set_id", "position", name="uq_gold_cases_position"),)

    gold_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gold_sets.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    objective_text: Mapped[str] = mapped_column(Text)


class GoldLink(Audited, CoreModel):
    """A framework item a person decided an objective maps to (coverage 1 to 5), or explicitly
    decided it does not (coverage 0)."""

    __tablename__ = "gold_links"
    __table_args__ = (
        UniqueConstraint("case_id", "item_code", name="uq_gold_links_case_item"),
        CheckConstraint("coverage BETWEEN 0 AND 5", name="coverage_range"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gold_cases.id", ondelete="CASCADE"), index=True
    )
    item_code: Mapped[str] = mapped_column(String(100))
    coverage: Mapped[int] = mapped_column(Integer)
    depth: Mapped[DepthMatch | None] = mapped_column(
        str_enum(DepthMatch, "gold_depth"), default=None
    )


class EvalRun(CoreModel):
    """One evaluation of a prompt version and model on a gold set.

    The row keeps the raw answers (``results``, one entry per gold objective), so every
    threshold can be tried afterwards. Derived data: not audited, not exported.
    """

    __tablename__ = "eval_runs"

    gold_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gold_sets.id", ondelete="CASCADE"), index=True
    )
    # The AI run that carries the calls, tokens, cost and progress.
    ai_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), unique=True
    )
    # The curriculum version whose objectives (matched by wording) the gold set was run on.
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    top_k: Mapped[int] = mapped_column(Integer)
    # The AI's answers per gold objective; see ``services/eval_run.py`` for the shape.
    results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )
    # Gold objectives with no objective of that wording in the version (left out of the figures).
    not_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
