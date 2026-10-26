"""Audit logging.

Every change to an ``Audited`` model is recorded automatically when the
session flushes: creates, updates (changed fields only), soft deletes,
restores and deletes. Entries are inserted in the same transaction as the
change, so they are committed or rolled back with it.

Who acted comes from ``set_actor`` (called on authentication); without an
actor, entries are attributed to the system. ``audit_operation`` attaches an
operation name and details (such as a reason) to the entries written inside it.

Not captured: bulk ``UPDATE``/``DELETE`` statements and rows removed by
database cascades. Services that change audited data use ORM objects.
"""

import enum
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, event, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ColumnProperty, InstanceState, Session, UOWTransaction
from sqlalchemy.orm.attributes import instance_state

from app.models import AuditLog
from app.models.audit import ActorType
from app.models.base import Audited

_actor: ContextVar[uuid.UUID | None] = ContextVar("audit_actor", default=None)
_operation: ContextVar[dict[str, Any] | None] = ContextVar("audit_operation", default=None)

# Never recorded for any model: bookkeeping that changes on every write.
_ALWAYS_EXCLUDED = frozenset({"updated_at"})
_NOT_DIFFED = frozenset({"created_at", "created_by_id"})


def set_actor(user_id: uuid.UUID | None) -> None:
    """Attribute the following changes in this context to a user (None: system)."""
    _actor.set(user_id)


def current_actor() -> uuid.UUID | None:
    return _actor.get()


@contextmanager
def actor_scope(user_id: uuid.UUID | None = None) -> Iterator[None]:
    """Attribute changes inside the block to a user (None: system), then restore."""
    token = _actor.set(user_id)
    try:
        yield
    finally:
        _actor.reset(token)


@contextmanager
def audit_operation(
    name: str, *, actor_id: uuid.UUID | None = None, **details: Any
) -> Iterator[None]:
    """Label the audit entries written inside the block, e.g. with a reason.

    ``actor_id`` attributes them to that user, for services given an explicit actor.
    """
    token = _operation.set({"operation": name, **_jsonable(details)})
    actor_token = _actor.set(actor_id) if actor_id is not None else None
    try:
        yield
    finally:
        if actor_token is not None:
            _actor.reset(actor_token)
        _operation.reset(token)


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return value


def _state(obj: Audited) -> InstanceState[Any]:
    return instance_state(obj)


def _columns(obj: Audited) -> list[ColumnProperty[Any]]:
    model = type(obj)
    excluded = _ALWAYS_EXCLUDED | model.__audit_exclude__ | model.__audit_ignore__
    return [prop for prop in _state(obj).mapper.column_attrs if prop.key not in excluded]


def _snapshot(obj: Audited) -> dict[str, Any]:
    return {prop.key: _jsonable(getattr(obj, prop.key)) for prop in _columns(obj)}


def _changes(obj: Audited) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Changed fields before and after, and whether an excluded field changed."""
    state = _state(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for prop in _columns(obj):
        if prop.key in _NOT_DIFFED:
            continue
        history = state.attrs[prop.key].history
        if history.has_changes():
            before[prop.key] = _jsonable(history.deleted[0] if history.deleted else None)
            after[prop.key] = _jsonable(history.added[0] if history.added else None)
    hidden = any(
        state.attrs[key].history.has_changes()
        for key in type(obj).__audit_exclude__
        if key in state.attrs
    )
    return before, after, hidden


def _entry(obj: Audited, action: str, **values: Any) -> dict[str, Any]:
    actor = _actor.get()
    return {
        "id": uuid.uuid4(),
        "actor_type": ActorType.USER if actor else ActorType.SYSTEM,
        "actor_id": actor,
        "entity_type": _state(obj).mapper.persist_selectable.description,
        "entity_id": getattr(obj, "id", None),
        "action": action,
        "context": _operation.get() or {},
        **values,
    }


@event.listens_for(Session, "after_flush")
def _record_changes(session: Session, _flush_context: UOWTransaction) -> None:
    """Write audit entries for everything this flush changed."""
    entries: list[dict[str, Any]] = []
    for obj in session.new:
        if isinstance(obj, Audited):
            entries.append(_entry(obj, "create", after=_snapshot(obj)))
    for obj in session.dirty:
        if not isinstance(obj, Audited) or not session.is_modified(obj):
            continue
        before, after, hidden = _changes(obj)
        if not before and not hidden:
            continue
        action = "update"
        if "deleted_at" in after:
            action = "restore" if after["deleted_at"] is None else "soft_delete"
        context = dict(_operation.get() or {})
        if hidden:
            # Say that an excluded (e.g. personal) field changed, without its value.
            changed = sorted(
                key
                for key in type(obj).__audit_exclude__
                if _state(obj).attrs[key].history.has_changes()
            )
            context["unrecorded_fields"] = changed
        entries.append(_entry(obj, action, before=before, after=after, context=context))
    for obj in session.deleted:
        if isinstance(obj, Audited):
            entries.append(_entry(obj, "delete", before=_snapshot(obj)))
    if entries:
        # A plain table insert on the flush's connection: no nested ORM flush.
        # One insert per shape of entry: creates have no "before", deletes no "after", and a
        # single executemany needs the same keys in every row.
        shapes: dict[frozenset[str], list[dict[str, Any]]] = {}
        for entry in entries:
            shapes.setdefault(frozenset(entry), []).append(entry)
        for group in shapes.values():
            session.connection().execute(insert(AuditLog), group)


async def record_event(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an event that is not a data change (e.g. viewing personal data)."""
    actor = _actor.get()
    await db.execute(
        insert(AuditLog).values(
            id=uuid.uuid4(),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            context={**(_operation.get() or {}), **_jsonable(details or {})},
        )
    )


async def entity_history(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[AuditLog]:
    """Audit entries for one entity, oldest first."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.seq)
    )
    return list(result.scalars())


async def purge_audit_log(db: AsyncSession, *, older_than_days: int) -> int:
    """Delete audit entries older than the retention period (0 = keep everything).

    The database refuses deletes unless this transaction sets the purge flag.
    """
    if older_than_days <= 0:
        return 0
    await db.execute(text("SET LOCAL ocmp.allow_audit_purge = 'on'"))
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await db.execute(
        delete(AuditLog).where(AuditLog.occurred_at < cutoff).returning(AuditLog.id)
    )
    return len(result.all())
