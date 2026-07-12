"""Server-side persistence for the 3D cafe editor layout.

Single global layout (namespace='default'): staff edits once, every visitor
sees the same furniture, surviving backend restarts and browser changes. The
service is intentionally thin — the editor treats the layout as an opaque
``FurnitureItem[]`` blob, so we only store/forward the JSON.
"""
from __future__ import annotations

import json
from datetime import timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import OfficeLayout

NAMESPACE_DEFAULT = "default"


class LayoutConflictError(Exception):
    """The caller attempted to overwrite a layout version it did not read."""


def get_layout_record(
    db: Session,
    namespace: str = NAMESPACE_DEFAULT,
) -> tuple[Optional[list], Optional[str]]:
    """Return stored layout items plus the row update timestamp."""
    row = (
        db.query(OfficeLayout)
        .filter(OfficeLayout.namespace == namespace)
        .first()
    )
    if not row:
        return None, None
    try:
        parsed = json.loads(row.layout_json)
        items = parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        items = None
    updated_at = (
        row.updated_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        if row.updated_at
        else None
    )
    return items, updated_at


def get_layout_state(
    db: Session,
    namespace: str = NAMESPACE_DEFAULT,
) -> tuple[Optional[list], Optional[str], int | None]:
    """Return items, timestamp, and optimistic-lock version."""
    row = db.query(OfficeLayout).filter(OfficeLayout.namespace == namespace).first()
    if row is None:
        return None, None, None
    try:
        parsed = json.loads(row.layout_json)
        items = parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        items = None
    updated_at = (
        row.updated_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        if row.updated_at
        else None
    )
    return items, updated_at, int(getattr(row, "version", 1) or 1)


def get_layout(db: Session, namespace: str = NAMESPACE_DEFAULT) -> Optional[list]:
    """Return the stored layout items, or None when no layout is saved yet.

    Corrupt JSON degrades to None (caller falls back to default/localStorage)
    rather than raising — layout must never block the scene from rendering.
    """
    items, _ = get_layout_record(db, namespace)
    return items


def save_layout(
    db: Session,
    items: list,
    namespace: str = NAMESPACE_DEFAULT,
    *,
    expected_version: int | None = None,
) -> int:
    """CAS-upsert a layout and return its new optimistic-lock version."""
    payload = json.dumps(items, ensure_ascii=False)
    row = (
        db.query(OfficeLayout)
        .filter(OfficeLayout.namespace == namespace)
        .first()
    )
    if row:
        current_version = int(getattr(row, "version", 1) or 1)
        if expected_version is None:
            raise LayoutConflictError(
                "layout version is required when updating an existing layout"
            )
        if expected_version is not None and expected_version != current_version:
            raise LayoutConflictError(
                f"layout version conflict: expected {expected_version}, current {current_version}"
            )
        result = db.execute(
            update(OfficeLayout)
            .where(
                OfficeLayout.namespace == namespace,
                OfficeLayout.version == current_version,
            )
            .values(layout_json=payload, version=current_version + 1)
        )
        if result.rowcount != 1:
            db.rollback()
            raise LayoutConflictError("layout was updated concurrently")
        new_version = current_version + 1
    else:
        if expected_version not in (None, 0):
            raise LayoutConflictError("layout does not exist at the expected version")
        new_version = 1
        db.add(
            OfficeLayout(
                namespace=namespace,
                layout_json=payload,
                version=new_version,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise LayoutConflictError("layout was created concurrently") from exc
    return new_version
