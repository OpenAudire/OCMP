"""Framework packs: validate and import (format: packs/schema/framework-pack.schema.json).

A pack holds one framework version (metadata, item tree, cross-references)
and optionally taxonomy scales. Importing creates them through the framework
service, so the usual rules and the audit log apply.
"""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Framework, FrameworkItem, TaxonomyLevel, TaxonomyScale
from app.models.framework import CrossRefType, FrameworkProfile
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.frameworks import add_cross_ref, add_item


class PackMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(pattern=r"^[a-z0-9-]+$", max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    publisher: str = Field(min_length=1, max_length=255)
    licence: str = ""
    profile: FrameworkProfile = FrameworkProfile.CORE
    description: str = ""
    url: str | None = None


class PackItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    description: str = ""
    parent_code: str | None = None
    order: int = 0
    metadata: dict[str, Any] = {}


class PackCrossRef(BaseModel):
    from_code: str
    to_code: str
    type: CrossRefType


class PackLevel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    verbs: list[str] = []


class PackScale(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    levels: list[PackLevel] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_levels(self) -> "PackScale":
        orders = [level.order for level in self.levels]
        names = [level.name for level in self.levels]
        if len(set(orders)) != len(orders) or len(set(names)) != len(names):
            raise ValueError(f"Scale '{self.key}' repeats a level order or name.")
        return self


class FrameworkPack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metadata: PackMetadata
    items: list[PackItem] = Field(min_length=1)
    cross_references: list[PackCrossRef] = []
    taxonomy_scales: list[PackScale] = []

    @model_validator(mode="after")
    def consistent_tree(self) -> "FrameworkPack":
        codes = [item.code for item in self.items]
        if len(set(codes)) != len(codes):
            raise ValueError("Item codes must be unique.")
        known = set(codes)
        parents = {item.code: item.parent_code for item in self.items}
        for item in self.items:
            if item.parent_code is not None and item.parent_code not in known:
                raise ValueError(f"Item '{item.code}' has an unknown parent '{item.parent_code}'.")
        for code in codes:  # walk up from each item; a repeat means a cycle
            seen = set()
            current: str | None = code
            while current is not None:
                if current in seen:
                    raise ValueError(f"Item '{code}' is part of a parent cycle.")
                seen.add(current)
                current = parents[current]
        for ref in self.cross_references:
            if ref.from_code not in known or ref.to_code not in known:
                raise ValueError(f"Cross-reference {ref.from_code} -> {ref.to_code} is unknown.")
        return self


def parse_pack(data: dict[str, Any]) -> FrameworkPack:
    """Validate pack data.

    Raises:
        InvalidRequestError: Describing what is wrong with the pack.
    """
    try:
        return FrameworkPack.model_validate(data)
    except ValidationError as exc:
        raise InvalidRequestError(f"Invalid framework pack: {exc}") from exc


def load_pack_file(path: Path) -> FrameworkPack:
    """Read and validate a pack file."""
    return parse_pack(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PackImport:
    framework: Framework
    items: dict[str, FrameworkItem]
    scales: dict[str, TaxonomyScale]


async def import_pack(
    db: AsyncSession, pack: FrameworkPack, *, created_by_id: uuid.UUID | None = None
) -> PackImport:
    """Create the pack's framework version, items, cross-references and scales.

    Scales that already exist (same key) are reused, not duplicated.

    Raises:
        ConflictError: If this framework version is already imported.
    """
    meta = pack.metadata
    exists = await db.scalar(
        select(Framework.id).where(
            Framework.key == meta.key,
            Framework.version_label == meta.version,
            Framework.deleted_at.is_(None),
        )
    )
    if exists:
        raise ConflictError(f"Framework '{meta.key}' version {meta.version} is already imported.")

    framework = Framework(
        key=meta.key,
        name=meta.name,
        version_label=meta.version,
        publisher=meta.publisher,
        licence_note=meta.licence,
        description=meta.description,
        url=meta.url,
        profile=meta.profile,
        created_by_id=created_by_id,
    )
    db.add(framework)
    await db.flush()

    items: dict[str, FrameworkItem] = {}
    pending = list(pack.items)
    while pending:  # parents before children (the tree was validated as acyclic)
        ready = [i for i in pending if i.parent_code is None or i.parent_code in items]
        for raw in ready:
            items[raw.code] = await add_item(
                db,
                framework,
                code=raw.code,
                title=raw.title,
                description=raw.description,
                parent=items.get(raw.parent_code) if raw.parent_code else None,
                position=raw.order,
                metadata=raw.metadata,
                created_by_id=created_by_id,
            )
            pending.remove(raw)
    for ref in pack.cross_references:
        await add_cross_ref(
            db, items[ref.from_code], items[ref.to_code], ref.type, created_by_id=created_by_id
        )

    scales: dict[str, TaxonomyScale] = {}
    for raw_scale in pack.taxonomy_scales:
        scale = (
            await db.execute(select(TaxonomyScale).where(TaxonomyScale.key == raw_scale.key))
        ).scalar_one_or_none()
        if scale is None:
            scale = TaxonomyScale(
                key=raw_scale.key,
                name=raw_scale.name,
                description=raw_scale.description,
                created_by_id=created_by_id,
            )
            db.add(scale)
            await db.flush()
            db.add_all(
                TaxonomyLevel(
                    scale_id=scale.id,
                    position=level.order,
                    name=level.name,
                    description=level.description,
                    verbs=level.verbs,
                    created_by_id=created_by_id,
                )
                for level in raw_scale.levels
            )
            await db.flush()
        scales[raw_scale.key] = scale
    return PackImport(framework=framework, items=items, scales=scales)
