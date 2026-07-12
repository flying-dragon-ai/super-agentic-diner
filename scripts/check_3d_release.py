"""Validate that the built 3D index references existing release assets."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ROOT = REPO_ROOT / "app" / "static" / "3d"
sys.path.insert(0, str(REPO_ROOT))

from app.release_integrity import validate_3d_release  # noqa: E402


def _tracked(path: Path) -> bool:
    relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tracked", action="store_true")
    args = parser.parse_args()

    errors = validate_3d_release(RELEASE_ROOT)
    if args.require_tracked and not errors:
        html = (RELEASE_ROOT / "index.html").read_text(encoding="utf-8")
        import re
        from urllib.parse import urlsplit

        for raw in re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", html):
            path = urlsplit(raw).path
            if path.startswith("/3d/"):
                path = path[len("/3d/") :]
            else:
                path = path.lstrip("./")
            if path and not _tracked(RELEASE_ROOT / path):
                errors.append(f"referenced asset is not tracked by git: {raw}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("3D release integrity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
