from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


SECRET_KEYS = ("SECRET", "PASSWORD", "TOKEN", "KEY")


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_with_overrides(path: Path) -> dict[str, str]:
    values = _load_env(path)
    for key, value in os.environ.items():
        if key.startswith(("EVOMAP_", "A2A_", "WORKER_")):
            values[key] = value
    return values


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_upper = key.upper()
            is_presence_flag = key_upper.endswith(("_CONFIGURED", "_PRESENT", "_ENABLED"))
            if not is_presence_flag and any(token in key_upper for token in SECRET_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "CoffeeAIBoss/1.0 (+https://evomap.ai; binding-check)",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc
    data = json.loads(body) if body else {}
    if not isinstance(data, dict):
        raise RuntimeError("response was not a JSON object")
    return data


def check_binding(env_path: Path, timeout: float) -> tuple[int, dict[str, Any]]:
    env = _env_with_overrides(env_path)
    hub_url = (env.get("EVOMAP_HUB_URL") or "https://evomap.ai").rstrip("/")
    listing_id = env.get("EVOMAP_SERVICE_LISTING_ID", "").strip()
    configured_node_id = env.get("EVOMAP_NODE_ID", "").strip()
    configured_secret_present = bool(env.get("EVOMAP_NODE_SECRET", "").strip())
    worker_enabled = env.get("WORKER_ENABLED", "").strip().lower() in {"1", "true", "on", "yes"}

    result: dict[str, Any] = {
        "ok": False,
        "env_path": str(env_path),
        "hub": hub_url,
        "checks": {
            "listing_configured": bool(listing_id),
            "node_id_configured": bool(configured_node_id),
            "node_secret_configured": configured_secret_present,
            "worker_enabled": worker_enabled,
        },
        "listing": None,
        "diagnosis": [],
    }

    if not listing_id:
        result["diagnosis"].append("EVOMAP_SERVICE_LISTING_ID is missing.")
        return 2, result

    listing = _get_json(f"{hub_url}/a2a/service/{quote(listing_id, safe='')}", timeout)
    public_listing = {
        "id": listing.get("id"),
        "title": listing.get("title"),
        "status": listing.get("status"),
        "node_id": listing.get("node_id"),
        "execution_mode": listing.get("execution_mode"),
        "price_per_task": listing.get("price_per_task"),
        "max_concurrent": listing.get("max_concurrent"),
        "active_claims": listing.get("active_claims"),
        "featured": listing.get("featured"),
    }
    result["listing"] = public_listing

    if listing.get("status") != "active":
        result["diagnosis"].append("Configured service listing is not active.")
    if configured_node_id and listing.get("node_id") != configured_node_id:
        result["diagnosis"].append(
            "EVOMAP_NODE_ID does not match the service listing owner node_id."
        )
    if not configured_node_id:
        result["diagnosis"].append("EVOMAP_NODE_ID is missing.")
    if not configured_secret_present:
        result["diagnosis"].append("EVOMAP_NODE_SECRET is missing.")
    if not worker_enabled:
        result["diagnosis"].append(
            "WORKER_ENABLED is not enabled; provider worker will not participate in Hub work dispatch."
        )

    result["ok"] = not result["diagnosis"]
    return (0 if result["ok"] else 1), result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Coffee AI Boss EvoMap service listing and provider-worker binding."
    )
    parser.add_argument("--env-file", default=".env", help="Path to the local env file.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    code, result = check_binding(Path(args.env_file), args.timeout)
    json.dump(
        _redact(result),
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
