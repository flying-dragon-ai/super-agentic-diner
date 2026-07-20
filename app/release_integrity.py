"""Static release integrity checks shared by readiness and CI tooling."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


_ASSET_RE = re.compile(r"(?:src|href)=[\"']([^\"']+)[\"']", re.IGNORECASE)


def validate_3d_release(root: Path) -> list[str]:
    """Return human-readable errors for missing/escaping local asset references."""
    errors: list[str] = []
    root = root.resolve()
    index = root / "index.html"
    if not index.is_file():
        return ["index.html is missing"]
    try:
        html = index.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"index.html cannot be read: {exc.__class__.__name__}"]

    for raw in _ASSET_RE.findall(html):
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or raw.startswith(("data:", "#")):
            continue
        path = parsed.path
        if path.startswith("/3d/"):
            path = path[len("/3d/") :]
        else:
            path = path.lstrip("./")
        if not path:
            continue
        target = (root / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"asset reference escapes release root: {raw}")
            continue
        if not target.is_file():
            errors.append(f"referenced asset is missing: {raw}")
    return errors
