from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def request_json(url: str, token: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"send action failed: HTTP {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"send action failed: 无法连接服务器: {exc.reason}") from exc


def parse_payload(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--payload must be JSON: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a restaurant Agent visualization action.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("RESTAURANT_API_BASE"),
        required=not os.getenv("RESTAURANT_API_BASE"),
        help="Legacy helper requires an explicit URL; use order.py --discover for automatic discovery.",
    )
    parser.add_argument("--agent-id", default=os.getenv("RESTAURANT_AGENT_ID"), required=not os.getenv("RESTAURANT_AGENT_ID"))
    parser.add_argument(
        "--token",
        default=os.getenv("RESTAURANT_AGENT_TOKEN"),
        required=not os.getenv("RESTAURANT_AGENT_TOKEN"),
        help="Agent API token. Prefer the RESTAURANT_AGENT_TOKEN env var to avoid leaking the token in the process list.",
    )
    parser.add_argument("--action", required=True)
    parser.add_argument("--target")
    parser.add_argument("--message")
    parser.add_argument("--correlation-id")
    parser.add_argument("--payload")
    args = parser.parse_args()

    body = {
        "action_type": args.action,
        "target": args.target,
        "message": args.message,
        "correlation_id": args.correlation_id,
        "payload": parse_payload(args.payload),
    }
    url = args.base_url.rstrip("/") + f"/agents/{args.agent_id}/actions"
    result = request_json(url, args.token, body)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
