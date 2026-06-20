from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
STATE_PATH = Path(os.getenv("A2A_SUPER_ORDER_STATE", Path.home() / ".a2a-super-order" / "state.json"))


class ApiError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def redact_for_stdout(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ("secret", "token", "key", "authorization")):
                redacted[key] = "[stored-in-state]"
            else:
                redacted[key] = redact_for_stdout(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_stdout(item) for item in value]
    return value


def request_json(
    url: str,
    payload: dict[str, Any],
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update({key: value for key, value in extra_headers.items() if value})
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        raise ApiError(exc.code, body) from exc


EVOMAP_HOME = Path(os.getenv("EVOLVER_HOME") or (Path.home() / ".evomap"))


def detect_username() -> str:
    """Cross-platform current login account name (NOT hostname).

    macOS: getpass.getuser() / $USER
    Windows: getpass.getuser() / %USERNAME%
    """
    try:
        user = getpass.getuser()
        if user:
            return user.strip()
    except Exception:
        pass
    return (os.getenv("USER") or os.getenv("USERNAME") or "user").strip()


def detect_evomap_install() -> dict[str, Any]:
    """Read-only detection of local EvoMap install via Evolver credential files.

    No side effects: does not write, network, or spawn processes.
    """
    node_id_file = EVOMAP_HOME / "node_id"
    node_secret_file = EVOMAP_HOME / "node_secret"
    has_node_id = node_id_file.exists()
    has_secret = node_secret_file.exists()
    return {
        "installed": has_node_id and has_secret,
        "has_node_id": has_node_id,
        "has_node_secret": has_secret,
        "evomap_home": str(EVOMAP_HOME),
        "node_id_path": str(node_id_file),
        "node_secret_path": str(node_secret_file),
    }


def load_evomap_credentials() -> dict[str, str] | None:
    """Load node_id + node_secret. Prefer ~/.evomap/ files, fall back to env vars."""
    install = detect_evomap_install()
    if install["installed"]:
        try:
            node_id = (EVOMAP_HOME / "node_id").read_text(encoding="utf-8").strip()
            node_secret = (EVOMAP_HOME / "node_secret").read_text(encoding="utf-8").strip()
            if node_id and node_secret:
                return {"node_id": node_id, "node_secret": node_secret}
        except Exception:
            pass
    node_id = (os.getenv("A2A_NODE_ID") or os.getenv("EVOMAP_NODE_ID") or "").strip()
    node_secret = (os.getenv("A2A_NODE_SECRET") or os.getenv("EVOMAP_NODE_SECRET") or "").strip()
    if node_id and node_secret:
        return {"node_id": node_id, "node_secret": node_secret}
    return None


def detect_mcp_node_id(root: Path) -> str | None:
    mcp_path = root / ".mcp.json"
    if not mcp_path.exists():
        return None
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        for server in servers.values():
            env = server.get("env") or {}
            node_id = env.get("EVOMAP_NODE_ID") or env.get("A2A_NODE_ID")
            if node_id:
                return str(node_id)
    except Exception:
        return None
    return None


def detect_node_id(root: Path, explicit: str | None) -> str:
    node_id = (
        explicit
        or os.getenv("EVOMAP_NODE_ID")
        or os.getenv("A2A_NODE_ID")
        or detect_mcp_node_id(root)
    )
    if node_id:
        return node_id.strip()
    host = platform.node() or "local"
    return "local-unregistered-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", host).strip("-").lower()


def load_payment_proof(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(raw)


def register_if_needed(args: argparse.Namespace, root: Path, state: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    # Prefer real EvoMap credentials from ~/.evomap/ (or env); only fall back to
    # the local-unregistered placeholder when the user has not installed EvoMap.
    evomap_creds = load_evomap_credentials()
    if evomap_creds:
        node_id = evomap_creds["node_id"]
        if not args.evomap_node_secret:
            args.evomap_node_secret = evomap_creds["node_secret"]
    else:
        node_id = detect_node_id(root, args.evomap_node_id)
    existing = state.get(base_url)
    if (
        existing
        and existing.get("evomap_node_id") == node_id
        and existing.get("agent_id")
        and existing.get("api_token")
        and not args.force_register
    ):
        return existing

    payload = {
        "tool_name": args.tool_name,
        "display_name": args.display_name,
        "evomap_node_id": node_id,
        "evomap_did": args.evomap_did,
        "role_type": "customer",
        "capabilities": ["a2a_super_order", "evomap_credit_payment"],
        "metadata": {"workspace": str(root), "source": "a2a-super-order-skill"},
        "evomap_capability_status": "detected" if args.evomap_node_id or os.getenv("A2A_HUB_URL") else "unknown",
    }
    result = request_json(base_url + "/skill/register", payload)
    result["evomap_node_id"] = node_id
    state[base_url] = result
    write_json(STATE_PATH, state)
    return result


def submit_order(args: argparse.Namespace, registration: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    request_id = args.request_id or "skill-" + uuid.uuid4().hex
    proof = load_payment_proof(args.payment_proof)
    payload = {
        "consumer_id": registration["consumer_id"],
        "agent_id": registration["agent_id"],
        "message": args.message,
        "request_id": request_id,
        "auto_confirm": True,
        "payment_proof": proof,
    }
    extra_headers = {}
    if args.evomap_node_secret:
        extra_headers["X-Evomap-Node-Secret"] = args.evomap_node_secret
    try:
        return request_json(
            base_url + "/skill/orders",
            payload,
            token=registration["api_token"],
            extra_headers=extra_headers,
        )
    except ApiError as exc:
        if exc.status != 402:
            raise
        detail = exc.body.get("detail") if isinstance(exc.body, dict) else exc.body
        if isinstance(detail, dict) and detail.get("status") == "payment_required":
            amount = detail.get("amount_credits", "unknown")
            listing_id = (detail.get("service_order_request") or {}).get("listing_id") or "unconfigured"
            raise SystemExit(
                "This paid order requires server-side EvoMap service-order payment. "
                "Set EVOMAP_NODE_SECRET or A2A_NODE_SECRET, or pass --evomap-node-secret, "
                "then retry the same request_id. No local Evolver ATP purchase was started. "
                f"amount_credits={amount}; listing_id={listing_id}"
            ) from exc
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Order coffee through the A2A super order Skill.")
    parser.add_argument("--base-url", default=os.getenv("RESTAURANT_API_BASE", DEFAULT_BASE_URL))
    parser.add_argument("--tool-name", default=os.getenv("RESTAURANT_TOOL_NAME", "codex"))
    parser.add_argument("--display-name", default=os.getenv("RESTAURANT_AGENT_NAME") or detect_username())
    parser.add_argument("--evomap-node-id", default=os.getenv("EVOMAP_NODE_ID") or os.getenv("A2A_NODE_ID"))
    parser.add_argument("--evomap-did", default=os.getenv("EVOMAP_DID"))
    parser.add_argument(
        "--evomap-node-secret",
        default=os.getenv("EVOMAP_NODE_SECRET") or os.getenv("A2A_NODE_SECRET"),
        help="Optional secret for server-side EvoMap service-order payment. Never print this value.",
    )
    parser.add_argument("--message")
    parser.add_argument("--request-id")
    parser.add_argument(
        "--payment-proof",
        help="Deprecated: the backend rejects unverified client payment proofs.",
    )
    parser.add_argument("--force-register", action="store_true")
    parser.add_argument("--register-only", action="store_true")
    parser.add_argument(
        "--check-evomap",
        action="store_true",
        help="Read-only check of local EvoMap install status (no side effects).",
    )
    args = parser.parse_args()

    if args.check_evomap:
        install = detect_evomap_install()
        creds = load_evomap_credentials()
        print(json.dumps({
            "installed": install["installed"],
            "has_node_id": install["has_node_id"],
            "has_node_secret": install["has_node_secret"],
            "evomap_home": install["evomap_home"],
            "credentials_loaded": creds is not None,
            "username": detect_username(),
        }, ensure_ascii=False, indent=2))
        return 0

    root = Path.cwd()
    state = read_json(STATE_PATH, {})
    registration = register_if_needed(args, root, state)
    if args.register_only:
        output = redact_for_stdout(registration)
        output["state_path"] = str(STATE_PATH)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if not args.message:
        raise SystemExit("--message is required unless --register-only is used")

    result = submit_order(args, registration)
    print(json.dumps(redact_for_stdout(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
