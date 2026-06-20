from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parent


def image_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}

    info: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "bytes": path.stat().st_size,
    }

    try:
        with Image.open(path) as img:
            info["size"] = list(img.size)
            info["mode"] = img.mode
            stat = ImageStat.Stat(img.convert("RGB"))
            info["mean_rgb"] = [round(v, 2) for v in stat.mean]
            info["nonblank"] = any((max(ext) - min(ext)) > 3 for ext in stat.extrema)
    except Exception as exc:  # pragma: no cover - diagnostic path
        info["error"] = str(exc)

    return info


def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    return {"path": str(path), "exists": True, "bytes": path.stat().st_size}


def expect_image(
    path: Path,
    expected_size: tuple[int, int] | None,
    required: bool,
    checks: list[dict[str, Any]],
    failures: list[str],
) -> None:
    info = image_info(path)
    info["required"] = required
    info["expected_size"] = list(expected_size) if expected_size else None
    checks.append(info)

    if required and not info.get("exists"):
        failures.append(f"Missing required image: {path}")
        return

    if not info.get("exists"):
        return

    if "error" in info:
        failures.append(f"Unreadable image {path}: {info['error']}")
        return

    if expected_size and tuple(info.get("size", [])) != expected_size:
        failures.append(f"Unexpected image size for {path}: {info.get('size')} != {list(expected_size)}")

    if not info.get("nonblank"):
        failures.append(f"Image appears blank: {path}")


def expect_file(
    path: Path,
    required: bool,
    checks: list[dict[str, Any]],
    failures: list[str],
) -> None:
    info = file_info(path)
    info["required"] = required
    checks.append(info)
    if required and not info.get("exists"):
        failures.append(f"Missing required file: {path}")


def html_src_checks(path: Path, failures: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "src": []}
    if not path.exists():
        failures.append(f"Missing review HTML: {path}")
        return result

    text = path.read_text(encoding="utf-8")
    base = path.parent
    for match in re.finditer(r'src="([^"]+)"', text):
        src = match.group(1)
        target = (base / src).resolve()
        exists = target.exists()
        result["src"].append({"src": src, "target": str(target), "exists": exists})
        if not exists:
            failures.append(f"HTML image reference does not resolve: {src}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Coffee Characters imagegen workflow assets.")
    parser.add_argument(
        "--require-generated",
        action="store_true",
        help="Require model-generated concept sheet and final cafe scene outputs to exist.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON only.",
    )
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    for idx in range(1, 5):
        expect_image(ROOT / "references" / f"character-ref-0{idx}.png", None, True, checks, failures)

    expect_image(ROOT / "coffee-characters-reference-board-v1.png", (2048, 2048), True, checks, failures)
    expect_image(ROOT / "coffee-characters-cafe-composite-preview-v1.png", (2304, 1536), True, checks, failures)
    expect_image(ROOT / "coffee-characters-concept-sheet-v1.png", (2048, 2048), args.require_generated, checks, failures)
    expect_image(ROOT / "coffee-characters-final-cafe-scene-v1.png", (2048, 1152), args.require_generated, checks, failures)

    for name in [
        "coffee-characters-concept-sheet-v1.prompt.md",
        "coffee-characters-concept-sheet-v1.prompt.txt",
        "coffee-characters-final-cafe-scene-v1.prompt.txt",
        "coffee-characters-cafe-composite-preview-v1.notes.md",
        "coffee-characters-v1-review.html",
        "run-concept-sheet-v1.ps1",
        "run-final-cafe-scene-v1.ps1",
        "validate-imagegen-workflow.py",
    ]:
        expect_file(ROOT / name, True, checks, failures)

    html = html_src_checks(ROOT / "coffee-characters-v1-review.html", failures)

    report = {
        "root": str(ROOT),
        "require_generated": args.require_generated,
        "ok": not failures,
        "failures": failures,
        "checks": checks,
        "html": html,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status = "OK" if report["ok"] else "FAILED"
        print(f"Coffee Characters imagegen workflow validation: {status}")
        if failures:
            print("")
            for failure in failures:
                print(f"- {failure}")
        print("")
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
