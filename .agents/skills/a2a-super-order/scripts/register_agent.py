from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def request_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"register failed: HTTP {exc.code} {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Register this tool as an advanced restaurant visualization Agent.")
    parser.add_argument("--base-url", default=os.getenv("RESTAURANT_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--tool-name", default=os.getenv("RESTAURANT_TOOL_NAME", "codex"))
    parser.add_argument("--display-name", default=os.getenv("RESTAURANT_AGENT_NAME", "Codex Waiter"))
    parser.add_argument("--role", default=os.getenv("RESTAURANT_AGENT_ROLE", "waiter"))
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()

    payload = {
        "tool_name": args.tool_name,
        "display_name": args.display_name,
        "role_type": args.role,
        "capabilities": args.capability,
        "metadata": {"source": "a2a-super-order-skill"},
    }
    result = request_json(args.base_url.rstrip("/") + "/agents/register", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
