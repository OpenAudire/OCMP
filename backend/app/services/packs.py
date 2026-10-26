"""Framework packs: validate, preview and import (format: packs/schema/framework-pack.schema.json).

A pack holds one framework version (metadata, item tree, cross-references) and optionally
taxonomy scales, crosswalks from earlier versions, tag lists and references to items of
other frameworks (format version 2, ADR 036). Importing creates everything through ORM
objects, so the audit log applies. Packs written for format version 1 stay valid.

Validation has two stages. ``check_pack`` needs no database and lists every problem it
finds (not only the first). ``resolve_pack`` looks up what the pack refers to (earlier
versions, other frameworks, existing scales and tag lists).
"""

import json
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Crosswalk,
    CrosswalkEntry,
    Framework,
    FrameworkCrossRef,
    FrameworkItem,
    TagList,
    TagValue,
    TaxonomyLevel,
    TaxonomyScale,
)
from app.models.framework import CrossRefType, CrosswalkEntryType, FrameworkProfile, FrameworkStatus
from app.models.tagging import TaggableType, TagListKind
from app.services.authorization import ConflictError, InvalidRequestError
from app.services.tagging import add_tag_value, create_tag_list

# The newest format this version of the application reads. Version 1 packs (no
# crosswalks, tag lists or references to other frameworks) are still valid.
FORMAT_VERSION = 2
MAX_PROBLEMS = 50
_LOOKUP_CHUNK = 1000


@dataclass(frozen=True)
class PackProblem:
    """One thing wrong with a pack: where it is and what is wrong."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class _Part(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class PackMetadata(_Part):
    key: str = Field(pattern=r"^[a-z0-9-]+$", max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    publisher: str = Field(min_length=1, max_length=255)
    licence: str = ""
    profile: FrameworkProfile = FrameworkProfile.CORE
    description: str = ""
    url: str | None = Field(default=None, max_length=2048)
    # True in the blank templates: they hold placeholders and cannot be imported as they are.
    template: bool = False


class PackItem(_Part):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    description: str = ""
    parent_code: str | None = None
    order: int = 0
    metadata: dict[str, Any] = {}


class PackCrossRef(_Part):
    from_code: str
    to_code: str
    type: CrossRefType
    # Format 2: the target is an item of another framework (an imported version of it).
    # Without a version the active version is used, else the newest.
    to_framework: str | None = Field(default=None, pattern=r"^[a-z0-9-]+$", max_length=64)
    to_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def version_needs_framework(self) -> "PackCrossRef":
        if self.to_version and not self.to_framework:
            raise ValueError("'to_version' needs 'to_framework'.")
        return self


class PackLevel(_Part):
    order: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    verbs: list[str] = []


class PackScale(_Part):
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


class PackCrosswalkEntry(_Part):
    type: CrosswalkEntryType
    from_code: str | None = None
    to_code: str | None = None
    notes: str = ""


class PackCrosswalk(_Part):
    """How the items of an earlier, already imported version of this framework move here."""

    from_version: str = Field(min_length=1, max_length=64)
    notes: str = ""
    entries: list[PackCrosswalkEntry] = Field(min_length=1)


class PackTagValue(_Part):
    label: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    description: str = ""
    order: int = 0


class PackTagList(_Part):
    key: str = Field(pattern=r"^[a-z0-9_-]+$", max_length=64)
    name: str = Field(min_length=1, max_length=255)
    kind: TagListKind = TagListKind.CUSTOM
    description: str = ""
    entity_types: list[TaggableType] = Field(default_factory=lambda: list(TaggableType))
    values: list[PackTagValue] = Field(min_length=1)


class FrameworkPack(_Part):
    format_version: int = Field(default=1, ge=1)
    metadata: PackMetadata
    items: list[PackItem] = Field(min_length=1)
    cross_references: list[PackCrossRef] = []
    taxonomy_scales: list[PackScale] = []
    crosswalks: list[PackCrosswalk] = []
    tag_lists: list[PackTagList] = []

    @property
    def uses_format_2(self) -> bool:
        return bool(
            self.crosswalks
            or self.tag_lists
            or any(ref.to_framework for ref in self.cross_references)
        )


def _location(loc: Sequence[str | int]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _tree_problems(pack: FrameworkPack) -> list[PackProblem]:
    problems: list[PackProblem] = []
    known: set[str] = set()
    for index, item in enumerate(pack.items):
        if item.code in known:
            problems.append(
                PackProblem(
                    f"items[{index}].code",
                    f"Item codes must be unique; '{item.code}' repeats.",
                )
            )
        known.add(item.code)
    parents = {item.code: item.parent_code for item in pack.items}
    for index, item in enumerate(pack.items):
        if item.parent_code is not None and item.parent_code not in known:
            problems.append(
                PackProblem(
                    f"items[{index}].parent_code",
                    f"Item '{item.code}' has an unknown parent '{item.parent_code}'.",
                )
            )
    for code in known:  # walk up from each item; a repeat means a cycle
        seen: set[str] = set()
        current: str | None = code
        while current is not None and current in known:
            if current in seen:
                problems.append(PackProblem("items", f"Item '{code}' is part of a parent cycle."))
                break
            seen.add(current)
            current = parents[current]

    ref_keys: set[tuple[str, str, str | None, str | None, str]] = set()
    for index, ref in enumerate(pack.cross_references):
        where = f"cross_references[{index}]"
        if ref.from_code not in known:
            problems.append(
                PackProblem(where, f"Cross-reference from unknown code '{ref.from_code}'.")
            )
        external = ref.to_framework is not None
        if not external and ref.to_code not in known:
            problems.append(
                PackProblem(where, f"Cross-reference {ref.from_code} -> {ref.to_code} is unknown.")
            )
        if not external and ref.from_code == ref.to_code:
            problems.append(PackProblem(where, "Cross-reference from an item to itself."))
        key = (ref.from_code, ref.to_code, ref.to_framework, ref.to_version, ref.type.value)
        if key in ref_keys:
            problems.append(PackProblem(where, "This cross-reference is listed twice."))
        ref_keys.add(key)
    return problems


def _crosswalk_problems(pack: FrameworkPack) -> list[PackProblem]:
    problems: list[PackProblem] = []
    known = {item.code for item in pack.items}
    versions: set[str] = set()
    for index, crosswalk in enumerate(pack.crosswalks):
        where = f"crosswalks[{index}]"
        if crosswalk.from_version == pack.metadata.version:
            problems.append(
                PackProblem(
                    f"{where}.from_version", "A crosswalk must start at an earlier version."
                )
            )
        if crosswalk.from_version in versions:
            problems.append(
                PackProblem(
                    f"{where}.from_version",
                    f"There is already a crosswalk from version '{crosswalk.from_version}'.",
                )
            )
        versions.add(crosswalk.from_version)
        pairs: set[tuple[str | None, str | None, str]] = set()
        for number, entry in enumerate(crosswalk.entries):
            at = f"{where}.entries[{number}]"
            needs_from = entry.type is not CrosswalkEntryType.NEW
            needs_to = entry.type is not CrosswalkEntryType.REMOVED
            if needs_from != bool(entry.from_code) or needs_to != bool(entry.to_code):
                problems.append(
                    PackProblem(
                        at,
                        f"A '{entry.type.value}' entry needs "
                        f"{'an old item (from_code)' if needs_from else 'no old item'} and "
                        f"{'a new item (to_code)' if needs_to else 'no new item'}.",
                    )
                )
            if entry.to_code and entry.to_code not in known:
                problems.append(
                    PackProblem(f"{at}.to_code", f"'{entry.to_code}' is not an item of this pack.")
                )
            key = (entry.from_code, entry.to_code, entry.type.value)
            if key in pairs:
                problems.append(PackProblem(at, "This entry is listed twice."))
            pairs.add(key)
    return problems


def _tag_list_problems(pack: FrameworkPack) -> list[PackProblem]:
    problems: list[PackProblem] = []
    keys: set[str] = set()
    for index, tag_list in enumerate(pack.tag_lists):
        where = f"tag_lists[{index}]"
        if tag_list.key in keys:
            problems.append(
                PackProblem(f"{where}.key", f"Tag list '{tag_list.key}' is listed twice.")
            )
        keys.add(tag_list.key)
        labels: set[str] = set()
        codes: set[str] = set()
        for number, value in enumerate(tag_list.values):
            at = f"{where}.values[{number}]"
            if value.label in labels:
                problems.append(
                    PackProblem(f"{at}.label", f"'{value.label}' repeats in this list.")
                )
            labels.add(value.label)
            if value.code:
                if value.code in codes:
                    problems.append(PackProblem(f"{at}.code", f"Code '{value.code}' repeats."))
                codes.add(value.code)
    return problems


def check_pack(data: Any) -> tuple[FrameworkPack | None, list[PackProblem]]:
    """Validate pack data without the database; list every problem found (up to a limit)."""
    if not isinstance(data, dict):
        return None, [PackProblem("", "A pack is a JSON object with 'metadata' and 'items'.")]
    try:
        pack = FrameworkPack.model_validate(data)
    except ValidationError as exc:
        problems = [
            PackProblem(_location(err["loc"]), err["msg"].removeprefix("Value error, "))
            for err in exc.errors()
        ]
        return None, problems[:MAX_PROBLEMS]
    problems = []
    if pack.format_version > FORMAT_VERSION:
        problems.append(
            PackProblem(
                "format_version",
                f"This pack uses format version {pack.format_version}; this installation reads "
                f"up to version {FORMAT_VERSION}. Update the application or use an older pack.",
            )
        )
    elif pack.format_version < 2 and pack.uses_format_2:
        problems.append(
            PackProblem(
                "format_version",
                "Crosswalks, tag lists and references to other frameworks need "
                f'"format_version": {FORMAT_VERSION}.',
            )
        )
    problems += _tree_problems(pack) + _crosswalk_problems(pack) + _tag_list_problems(pack)
    return (pack if not problems else None), problems[:MAX_PROBLEMS]


def parse_pack(data: dict[str, Any]) -> FrameworkPack:
    """Validate pack data.

    Raises:
        InvalidRequestError: Describing what is wrong with the pack.
    """
    pack, problems = check_pack(data)
    if pack is None:
        raise InvalidRequestError("Invalid framework pack: " + "; ".join(str(p) for p in problems))
    return pack


def load_pack_file(path: Path) -> FrameworkPack:
    """Read and validate a pack file."""
    return parse_pack(json.loads(path.read_text(encoding="utf-8")))


def tree_order(pack: FrameworkPack) -> list[tuple[PackItem, int]]:
    """Items with their depth, parents first, siblings by ``order`` (a valid tree only)."""
    children: dict[str | None, list[PackItem]] = defaultdict(list)
    for item in pack.items:
        children[item.parent_code].append(item)
    for siblings in children.values():
        siblings.sort(key=lambda i: i.order)  # stable: file order breaks ties
    out: list[tuple[PackItem, int]] = []
    stack = [(item, 0) for item in reversed(children[None])]
    while stack:
        item, depth = stack.pop()
        out.append((item, depth))
        stack.extend((child, depth + 1) for child in reversed(children[item.code]))
    return out


# --- Looking up what the pack refers to ----------------------------------------------


@dataclass
class Resolution:
    """What a pack refers to in the database, plus problems and notes for the preview."""

    problems: list[PackProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Target item of each reference to another framework, by index in cross_references.
    external_targets: dict[int, FrameworkItem] = field(default_factory=dict)
    # Source version and its items for each crosswalk, by index in crosswalks.
    crosswalk_sources: dict[int, Framework] = field(default_factory=dict)
    crosswalk_items: dict[int, dict[str, FrameworkItem]] = field(default_factory=dict)
    existing_scales: dict[str, TaxonomyScale] = field(default_factory=dict)
    existing_tag_lists: dict[str, TagList] = field(default_factory=dict)


async def _items_by_code(
    db: AsyncSession, framework_id: uuid.UUID, codes: Sequence[str]
) -> dict[str, FrameworkItem]:
    found: dict[str, FrameworkItem] = {}
    unique = list(dict.fromkeys(codes))
    for start in range(0, len(unique), _LOOKUP_CHUNK):
        rows = await db.scalars(
            select(FrameworkItem).where(
                FrameworkItem.framework_id == framework_id,
                FrameworkItem.code.in_(unique[start : start + _LOOKUP_CHUNK]),
            )
        )
        found.update({item.code: item for item in rows})
    return found


async def _target_framework(db: AsyncSession, key: str, version: str | None) -> Framework | None:
    versions = list(
        await db.scalars(
            select(Framework)
            .where(Framework.key == key, Framework.deleted_at.is_(None))
            .order_by(Framework.created_at.desc())
        )
    )
    if version is not None:
        return next((f for f in versions if f.version_label == version), None)
    active = next((f for f in versions if f.status is FrameworkStatus.ACTIVE), None)
    return active or (versions[0] if versions else None)


async def resolve_pack(db: AsyncSession, pack: FrameworkPack) -> Resolution:
    """Check the pack against the database (a valid pack, see ``check_pack``)."""
    meta = pack.metadata
    result = Resolution()
    problems, warnings = result.problems, result.warnings

    others = list(
        await db.scalars(
            select(Framework).where(Framework.key == meta.key, Framework.deleted_at.is_(None))
        )
    )
    if any(f.version_label == meta.version for f in others):
        problems.append(
            PackProblem(
                "metadata.version",
                f"Framework '{meta.key}' version {meta.version} is already imported.",
            )
        )
    elif others:
        listed = ", ".join(sorted(f"{f.version_label} ({f.status.value})" for f in others))
        warnings.append(
            f"Other versions of '{meta.key}' are already imported: {listed}. "
            "This pack becomes a new version."
        )

    wanted: dict[tuple[str, str | None], list[tuple[int, PackCrossRef]]] = defaultdict(list)
    for index, ref in enumerate(pack.cross_references):
        if ref.to_framework:
            wanted[(ref.to_framework, ref.to_version)].append((index, ref))
    for (key, version), refs in wanted.items():
        target = await _target_framework(db, key, version)
        label = f"'{key}'" + (f" version {version}" if version else "")
        if target is None:
            problems.append(
                PackProblem(
                    "cross_references",
                    f"Framework {label} is not imported yet; import it first, then this pack.",
                )
            )
            continue
        if version is None:
            warnings.append(
                f"References to '{key}' point to its {target.status.value} version "
                f"{target.version_label}."
            )
        items = await _items_by_code(db, target.id, [ref.to_code for _, ref in refs])
        for index, ref in refs:
            if ref.to_code in items:
                result.external_targets[index] = items[ref.to_code]
            else:
                problems.append(
                    PackProblem(
                        f"cross_references[{index}]",
                        f"Item '{ref.to_code}' does not exist in {label}.",
                    )
                )

    for index, crosswalk in enumerate(pack.crosswalks):
        source = next((f for f in others if f.version_label == crosswalk.from_version), None)
        where = f"crosswalks[{index}]"
        if source is None:
            problems.append(
                PackProblem(
                    f"{where}.from_version",
                    f"Version '{crosswalk.from_version}' of '{meta.key}' is not imported.",
                )
            )
            continue
        result.crosswalk_sources[index] = source
        codes = [e.from_code for e in crosswalk.entries if e.from_code]
        items = await _items_by_code(db, source.id, codes)
        result.crosswalk_items[index] = items
        for number, entry in enumerate(crosswalk.entries):
            if entry.from_code and entry.from_code not in items:
                problems.append(
                    PackProblem(
                        f"{where}.entries[{number}].from_code",
                        f"'{entry.from_code}' is not an item of version {crosswalk.from_version}.",
                    )
                )

    scale_keys = [s.key for s in pack.taxonomy_scales]
    if scale_keys:
        for scale in await db.scalars(
            select(TaxonomyScale).where(TaxonomyScale.key.in_(scale_keys))
        ):
            result.existing_scales[scale.key] = scale
        if result.existing_scales:
            warnings.append(
                "Scales that already exist are reused, not changed: "
                + ", ".join(sorted(result.existing_scales))
                + "."
            )
    list_keys = [t.key for t in pack.tag_lists]
    if list_keys:
        for tag_list in await db.scalars(
            select(TagList).where(TagList.key.in_(list_keys), TagList.deleted_at.is_(None))
        ):
            result.existing_tag_lists[tag_list.key] = tag_list
        if result.existing_tag_lists:
            warnings.append(
                "Tag lists that already exist only get the tags they lack: "
                + ", ".join(sorted(result.existing_tag_lists))
                + "."
            )
    return result


# --- Import --------------------------------------------------------------------------


@dataclass
class ImportSummary:
    items: int = 0
    cross_references: int = 0
    external_references: int = 0
    crosswalks: int = 0
    crosswalk_entries: int = 0
    scales_created: int = 0
    tag_lists_created: int = 0
    tag_values_added: int = 0


@dataclass(frozen=True)
class PackImport:
    framework: Framework
    items: dict[str, FrameworkItem]
    scales: dict[str, TaxonomyScale]
    summary: ImportSummary = field(default_factory=ImportSummary)


async def import_pack(
    db: AsyncSession, pack: FrameworkPack, *, created_by_id: uuid.UUID | None = None
) -> PackImport:
    """Create the pack's framework version, items, references, crosswalks, scales and tag lists.

    Scales and tag lists that already exist (same key) are reused; a tag list only gets the
    tags it lacks. Items are added level by level in bulk (large packs), still as ORM objects
    so each row reaches the audit log.

    Raises:
        ConflictError: If this framework version is already imported.
        InvalidRequestError: If the pack is a template or refers to something that does not exist.
    """
    meta = pack.metadata
    if meta.template:
        raise InvalidRequestError(
            "This pack is marked as a template. Replace the placeholders and remove "
            '"template": true from its metadata first.'
        )
    resolution = await resolve_pack(db, pack)
    if any(p.path == "metadata.version" for p in resolution.problems):
        raise ConflictError(f"Framework '{meta.key}' version {meta.version} is already imported.")
    if resolution.problems:
        raise InvalidRequestError(
            "Invalid framework pack: " + "; ".join(str(p) for p in resolution.problems[:10])
        )

    summary = ImportSummary()
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
    by_depth: dict[int, list[PackItem]] = defaultdict(list)
    for raw, depth in tree_order(pack):
        by_depth[depth].append(raw)
    for depth in sorted(by_depth):  # parents are flushed (have ids) before their children
        batch = [
            FrameworkItem(
                framework_id=framework.id,
                parent_id=items[raw.parent_code].id if raw.parent_code else None,
                depth=depth,
                code=raw.code,
                title=raw.title,
                description=raw.description,
                position=raw.order,
                item_metadata=raw.metadata,
                created_by_id=created_by_id,
            )
            for raw in by_depth[depth]
        ]
        db.add_all(batch)
        await db.flush()
        items.update({item.code: item for item in batch})
    summary.items = len(items)

    refs: list[FrameworkCrossRef] = []
    for index, ref in enumerate(pack.cross_references):
        target = resolution.external_targets[index] if ref.to_framework else items[ref.to_code]
        refs.append(
            FrameworkCrossRef(
                from_item_id=items[ref.from_code].id,
                to_item_id=target.id,
                type=ref.type,
                created_by_id=created_by_id,
            )
        )
        summary.external_references += 1 if ref.to_framework else 0
    db.add_all(refs)
    summary.cross_references = len(refs)

    scales: dict[str, TaxonomyScale] = {}
    for raw_scale in pack.taxonomy_scales:
        scale = resolution.existing_scales.get(raw_scale.key)
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
            summary.scales_created += 1
        scales[raw_scale.key] = scale

    for index, raw_crosswalk in enumerate(pack.crosswalks):
        source = resolution.crosswalk_sources[index]
        crosswalk = Crosswalk(
            from_framework_id=source.id,
            to_framework_id=framework.id,
            notes=raw_crosswalk.notes,
            created_by_id=created_by_id,
        )
        db.add(crosswalk)
        await db.flush()
        old_items = resolution.crosswalk_items[index]
        db.add_all(
            CrosswalkEntry(
                crosswalk_id=crosswalk.id,
                type=entry.type,
                from_item_id=old_items[entry.from_code].id if entry.from_code else None,
                to_item_id=items[entry.to_code].id if entry.to_code else None,
                notes=entry.notes,
                created_by_id=created_by_id,
            )
            for entry in raw_crosswalk.entries
        )
        summary.crosswalks += 1
        summary.crosswalk_entries += len(raw_crosswalk.entries)

    for raw_list in pack.tag_lists:
        tag_list = resolution.existing_tag_lists.get(raw_list.key)
        taken_labels: set[str] = set()
        taken_codes: set[str] = set()
        position = 0
        if tag_list is None:
            tag_list = await create_tag_list(
                db,
                key=raw_list.key,
                name=raw_list.name,
                kind=raw_list.kind,
                description=raw_list.description,
                entity_types=raw_list.entity_types,
                created_by_id=created_by_id,
            )
            summary.tag_lists_created += 1
        else:
            existing = list(
                await db.scalars(
                    select(TagValue).where(
                        TagValue.tag_list_id == tag_list.id, TagValue.deleted_at.is_(None)
                    )
                )
            )
            taken_labels = {v.label for v in existing}
            taken_codes = {v.code for v in existing if v.code}
            position = max((v.position for v in existing), default=-1) + 1
        for value in sorted(raw_list.values, key=lambda v: v.order):
            if value.label in taken_labels or (value.code and value.code in taken_codes):
                continue
            await add_tag_value(
                db,
                tag_list,
                value.label,
                code=value.code,
                description=value.description,
                position=position,
                created_by_id=created_by_id,
            )
            position += 1
            summary.tag_values_added += 1

    await db.flush()
    return PackImport(framework=framework, items=items, scales=scales, summary=summary)
