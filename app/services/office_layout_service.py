"""Server-side persistence for the 3D cafe editor layout.

Single global layout (namespace='default'): staff edits once, every visitor
sees the same furniture, surviving backend restarts and browser changes. The
service is intentionally thin — the editor treats the layout as an opaque
``FurnitureItem[]`` blob, so we only store/forward the JSON.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import OfficeLayout

NAMESPACE_DEFAULT = "default"


def get_layout(db: Session, namespace: str = NAMESPACE_DEFAULT) -> Optional[list]:
    """Return the stored layout items, or None when no layout is saved yet.

    Corrupt JSON degrades to None (caller falls back to default/localStorage)
    rather than raising — layout must never block the scene from rendering.
    """
    row = (
        db.query(OfficeLayout)
        .filter(OfficeLayout.namespace == namespace)
        .first()
    )
    if not row:
        return None
    try:
        parsed = json.loads(row.layout_json)
        return parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        return None


def save_layout(db: Session, items: list, namespace: str = NAMESPACE_DEFAULT) -> None:
    """Upsert the layout JSON for the given namespace (idempotent PUT)."""
    payload = json.dumps(items, ensure_ascii=False)
    row = (
        db.query(OfficeLayout)
        .filter(OfficeLayout.namespace == namespace)
        .first()
    )
    if row:
        row.layout_json = payload
    else:
        db.add(OfficeLayout(namespace=namespace, layout_json=payload))
    db.commit()
