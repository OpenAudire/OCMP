"""Daily figures of a curriculum version for the dashboard trends (Slice 1.28, ADR 058)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CoreModel


class MetricSnapshot(CoreModel):
    """The key figures of one version on one day.

    Derived data (like embeddings): it is not audited and not exported, a day is written once
    (running the command again the same day replaces it), and it holds counts and shares only:
    never text, names or ids of people. ``metrics`` is built by ``services/dashboard_metrics.py``.
    """

    __tablename__ = "metric_snapshots"
    __table_args__ = (UniqueConstraint("version_id", "taken_on", name="uq_metric_snapshots_day"),)

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="CASCADE"), index=True
    )
    taken_on: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
