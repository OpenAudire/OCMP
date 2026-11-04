"""The history of curriculum imports (Slice 1.25, ADR 054; the history screen is Slice 1.26).

One row for each import that was applied: who, when, into which version, and how many rows were
created, updated or left unchanged in each sheet. It holds counts only: never the file, its name
or any of its cells.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Audited, CoreModel


class ImportJob(Audited, CoreModel):
    """One applied import."""

    __tablename__ = "import_jobs"

    # What was imported ("curriculum" now; tags, frameworks and mappings arrive in Slice 1.26).
    kind: Mapped[str] = mapped_column(String(32), index=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), default=None, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="applied", server_default="applied")
    # {"phases": {"created": 1, "updated": 0, "unchanged": 2}, ...}
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
