from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request


def _detect_username() -> str:
    """Cross-platform current login account name (aligned with order.py)."""
    try:
        user = getpass.getuser()
        if user:
            return user.strip()
    except Exception:
        pass
    return (os.getenv("USER") or os.getenv("USERNAME") or "user").strip()


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
    except urllib.error.URLError as exc:
        raise SystemExit(f"register failed: 无法连接服务器: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Register this tool as an advanced restaurant visualization Agent.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("RESTAURANT_API_BASE"),
        required=not os.getenv("RESTAURANT_API_BASE"),
        help="Legacy helper requires an explicit URL; use order.py --discover for automatic discovery.",
    )
    parser.add_argument("--tool-name", default=os.getenv("RESTAURANT_TOOL_NAME", "codex"))
    parser.add_argument("--display-name", default=os.getenv("RESTAURANT_AGENT_NAME") or _detect_username())
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
    print("⚠️ api_token 仅显示一次，请妥善保存，勿分享以下输出。", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
