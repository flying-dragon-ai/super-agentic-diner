from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import platform
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SERVICE_ID = "crossroads-agent-cafe"
DISCOVERY_PROTOCOL_VERSION = 1
DISCOVERY_REQUEST_TYPE = "crossroads-cafe-discover"
DISCOVERY_OFFER_TYPE = "crossroads-cafe-offer"
DEFAULT_DISCOVERY_UDP_PORT = 8137
LOCAL_BASE_URLS = ("http://127.0.0.1:8000", "http://127.0.0.1:8001")
# Use `os.getenv(KEY) or default` (not `os.getenv(KEY, default)`) so that an
# empty-string env var falls back to the default instead of writing state to cwd.
STATE_PATH = Path(os.getenv("A2A_SUPER_ORDER_STATE") or str(Path.home() / ".a2a-super-order" / "state.json"))
# Persisted backend address so AI tools set it once and all later commands
# auto-read it. The backend address can change between deploys (IP/domain).
CONFIG_PATH = Path(os.getenv("A2A_SUPER_ORDER_CONFIG") or str(Path.home() / ".a2a-super-order" / "config.json"))


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
    temp_path = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            temp_path.chmod(0o600)
        except OSError:
            pass
        temp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temp_path.unlink(missing_ok=True)


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
    except urllib.error.URLError as exc:
        # Connection refused / DNS failure / timeout. The node secret stays safe
        # (it travels in headers, never in the URL); surface a friendly message
        # instead of a raw traceback.
        raise SystemExit(f"无法连接服务器 {url}: {exc.reason}") from exc


def request_get_json(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        raise ApiError(exc.code, body) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Unable to connect to {url}: {exc.reason}") from exc


def normalize_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid backend URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("backend URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("backend URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("backend URL must not contain a query or fragment")
    return candidate


def probe_cafe_service(base_url: str, timeout: float = 2.0) -> bool:
    """Verify that a URL is this café, without sending account credentials."""
    request = urllib.request.Request(
        base_url.rstrip("/") + "/skill/discovery",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            document = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
        return False
    return bool(
        isinstance(document, dict)
        and document.get("service") == SERVICE_ID
        and document.get("protocol_version") == DISCOVERY_PROTOCOL_VERSION
    )


def _discovery_udp_port() -> int:
    raw = os.getenv("A2A_SUPER_ORDER_DISCOVERY_PORT", str(DEFAULT_DISCOVERY_UDP_PORT))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("A2A_SUPER_ORDER_DISCOVERY_PORT must be an integer") from exc
    if value < 1 or value > 65535:
        raise SystemExit("A2A_SUPER_ORDER_DISCOVERY_PORT must be between 1 and 65535")
    return value


def discover_lan_base_url(udp_port: int, timeout: float = 1.5) -> str | None:
    """Find and verify the first café offer from a private IPv4 network."""
    nonce = uuid.uuid4().hex
    payload = json.dumps(
        {
            "type": DISCOVERY_REQUEST_TYPE,
            "version": DISCOVERY_PROTOCOL_VERSION,
            "nonce": nonce,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    deadline = time.monotonic() + timeout
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.sendto(payload, ("255.255.255.255", udp_port))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                raw, peer = sock.recvfrom(2048)
            except socket.timeout:
                return None
            try:
                address = ipaddress.ip_address(peer[0])
                offer = json.loads(raw.decode("utf-8"))
                if not isinstance(offer, dict):
                    continue
                port = int(offer.get("http_port"))
                scheme = offer.get("scheme")
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not (address.is_private or address.is_loopback):
                continue
            if (
                offer.get("type") != DISCOVERY_OFFER_TYPE
                or offer.get("version") != DISCOVERY_PROTOCOL_VERSION
                or offer.get("service") != SERVICE_ID
                or offer.get("nonce") != nonce
                or scheme not in {"http", "https"}
                or port < 1
                or port > 65535
            ):
                continue
            candidate = f"{scheme}://{peer[0]}:{port}"
            if probe_cafe_service(candidate):
                return candidate
    except OSError:
        return None
    finally:
        sock.close()


def resolve_base_url(
    *,
    explicit: str | None,
    environment: str | None,
    cached: dict[str, Any],
    force_discovery: bool = False,
) -> tuple[str, str]:
    """Validate intentional URLs, then recover stale cache through discovery."""
    for raw, source in ((explicit, "argument"), (environment, "environment")):
        if not raw:
            continue
        try:
            candidate = normalize_base_url(raw)
        except ValueError as exc:
            raise SystemExit(f"{source} backend address is invalid: {exc}") from exc
        if not probe_cafe_service(candidate):
            raise SystemExit(
                f"无法验证 {source} 指定的咖啡厅服务：{candidate}。"
                "请确认服务已启动并检查 /skill/discovery。"
            )
        return candidate, source

    if not force_discovery:
        raw_cached = cached.get("base_url") if isinstance(cached, dict) else None
        if isinstance(raw_cached, str) and raw_cached.strip():
            try:
                candidate = normalize_base_url(raw_cached)
            except ValueError:
                candidate = ""
            if candidate and probe_cafe_service(candidate):
                return candidate, "cache"

    for candidate in LOCAL_BASE_URLS:
        if probe_cafe_service(candidate):
            return candidate, "localhost"

    discovered = discover_lan_base_url(_discovery_udp_port())
    if discovered:
        return discovered, "lan"
    raise SystemExit(
        "未找到 Crossroads Agent Café 后端。请启动服务（局域网访问需绑定 0.0.0.0），"
        "或使用 --base-url / RESTAURANT_API_BASE 指定地址。"
    )


def fetch_menu(base_url: str, token: str) -> tuple[bool, Any, str]:
    """GET {base_url}/menu. Read-only reachability + menu probe.

    ``/menu`` is anonymous and returns a list of products, so a 200 here also
    proves the backend is reachable for ordering. Used by ``--ping`` and
    ``--menu``. Returns ``(ok, data, error_message)``.
    """
    url = base_url.rstrip("/") + "/skill/menu"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return True, data, ""
    except urllib.error.HTTPError as exc:
        return False, None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:  # surface any failure to the caller with a reason
        return False, None, str(exc)


def cmd_ping(args: argparse.Namespace, registration: dict[str, Any]) -> int:
    """Step-0 self-check: is the backend reachable? Prints a decision-friendly JSON."""
    ok, data, err = fetch_menu(args.base_url, registration["api_token"])
    if not ok:
        print(json.dumps({
            "ok": False,
            "base_url": args.base_url,
            "status": "unreachable",
            "error": err,
            "hint": (
                "Run --discover to refresh a stale cached address, or set "
                "--base-url / RESTAURANT_API_BASE explicitly."
            ),
        }, ensure_ascii=False, indent=2))
        return 1
    items = data if isinstance(data, list) else []
    names = [str(it.get("name", "?")) for it in items if isinstance(it, dict)]
    print(json.dumps({
        "ok": True,
        "base_url": args.base_url,
        "status": "reachable",
        "menu_count": len(items),
        "sample": names[:5],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_menu(args: argparse.Namespace, registration: dict[str, Any]) -> int:
    """List available coffees so the caller knows exactly what to put in --message."""
    ok, data, err = fetch_menu(args.base_url, registration["api_token"])
    if not ok:
        print(json.dumps({
            "ok": False,
            "base_url": args.base_url,
            "status": "unreachable",
            "error": err,
            "hint": "Backend not reachable. Run --ping first to diagnose.",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    items = data if isinstance(data, list) else []
    compact = [
        {
            "name": it.get("name"),
            "price": it.get("price"),
            "tags": it.get("tags"),
            "category": it.get("category"),
            "stock": it.get("stock"),
        }
        for it in items
        if isinstance(it, dict)
    ]
    print(json.dumps({
        "base_url": args.base_url,
        "count": len(compact),
        "items": compact,
    }, ensure_ascii=False, indent=2))
    return 0


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
        "evomap_capability_status": "detected" if (evomap_creds or args.evomap_node_id or os.getenv("A2A_HUB_URL")) else "unknown",
    }
    if not args.evomap_node_secret:
        raise SystemExit(
            "Skill registration requires verified EvoMap credentials. "
            "Run --check-evomap and install/bind the node before ordering."
        )
    result = request_json(
        base_url + "/skill/register",
        payload,
        extra_headers={"X-Evomap-Node-Secret": args.evomap_node_secret},
    )
    result["evomap_node_id"] = node_id
    state[base_url] = result
    write_json(STATE_PATH, state)
    return result


def require_logged_in(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    registration = state.get(base_url) if isinstance(state, dict) else None
    if not isinstance(registration, dict) or not registration.get("api_token"):
        raise SystemExit(
            "account_login_required: run this Skill with --login, complete login in the browser, then retry"
        )
    try:
        profile = request_get_json(
            base_url + "/skill/me", token=registration["api_token"]
        )
    except ApiError as exc:
        if exc.status == 401:
            state.pop(base_url, None)
            write_json(STATE_PATH, state)
            raise SystemExit(
                "account_login_required: the saved login is invalid; run --login again"
            ) from exc
        raise
    for key in (
        "consumer_id", "agent_id", "evomap_node_id", "username", "nickname",
        "display_name", "currency", "balance", "scopes",
    ):
        if key in profile:
            registration[key] = profile[key]
    state[base_url] = registration
    write_json(STATE_PATH, state)
    return registration


def login_account(
    args: argparse.Namespace, root: Path, state: dict[str, Any]
) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    evomap_creds = load_evomap_credentials()
    node_id = (
        evomap_creds["node_id"]
        if evomap_creds
        else detect_node_id(root, args.evomap_node_id)
    )
    node_secret = args.evomap_node_secret or (
        evomap_creds["node_secret"] if evomap_creds else None
    )
    started = request_json(
        base_url + "/skill/auth/device/start",
        {
            "tool_name": args.tool_name,
            "display_name": args.display_name,
            "evomap_node_id": node_id,
            "evomap_did": args.evomap_did,
        },
        extra_headers={"X-Evomap-Node-Secret": node_secret or ""},
    )
    verification_url = str(started["verification_uri_complete"])
    user_code = str(started["user_code"])
    print(
        f"请在浏览器完成咖啡厅账号登录与授权：{verification_url}\n授权码：{user_code}",
        file=sys.stderr,
    )
    try:
        webbrowser.open(verification_url, new=2)
    except Exception:
        pass

    deadline = time.monotonic() + int(started.get("expires_in") or 600)
    interval = max(2, int(started.get("interval") or 2))
    device_code = str(started["device_code"])
    while time.monotonic() < deadline:
        result = request_json(
            base_url + "/skill/auth/device/token", {"device_code": device_code}
        )
        if result.get("status") == "authorization_pending":
            time.sleep(interval)
            continue
        if result.get("status") != "authorized" or not result.get("api_token"):
            raise SystemExit("Skill login failed: invalid authorization response")
        registration = {
            key: value
            for key, value in result.items()
            if key not in {"status", "authenticated"}
        }
        state[base_url] = registration
        write_json(STATE_PATH, state)
        return registration
    raise SystemExit("Skill login expired; run --login and try again")


def logout_account(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    registration = state.get(base_url) if isinstance(state, dict) else None
    if isinstance(registration, dict) and registration.get("api_token"):
        try:
            request_json(
                base_url + "/skill/logout",
                {},
                token=registration["api_token"],
            )
        except ApiError as exc:
            if exc.status != 401:
                raise
    state.pop(base_url, None)
    write_json(STATE_PATH, state)
    return {
        "ok": True,
        "status": "skill_logged_out",
        "web_session": "unchanged",
        "account_binding": "retained",
    }


def submit_order(args: argparse.Namespace, registration: dict[str, Any]) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    request_id = args.request_id or "skill-" + uuid.uuid4().hex
    payload = {
        "consumer_id": registration["consumer_id"],
        "agent_id": registration["agent_id"],
        "message": args.message,
        "request_id": request_id,
        "auto_confirm": True,
        "payment_proof": None,  # client-submitted proofs are rejected by the backend
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
    # Force UTF-8 on stdout/stderr so non-ASCII coffee names render correctly
    # when AI tools capture the output (Windows otherwise uses a locale codec
    # like GBK, which breaks UTF-8 parsers downstream).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Order coffee through the A2A super order Skill.")
    parser.add_argument("--base-url", default=None, help="Backend URL. Validated before use and saved after a successful probe.")
    parser.add_argument("--discover", action="store_true", help="Ignore a saved address, discover the café on localhost/LAN, validate it, and cache it.")
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
        help="Deprecated and ignored: the backend rejects unverified client payment proofs.",
    )
    parser.add_argument("--force-register", action="store_true")
    parser.add_argument("--register-only", action="store_true")
    parser.add_argument("--login", action="store_true", help="Log in through the cafe web page and bind this Skill.")
    parser.add_argument("--me", action="store_true", help="Show the linked cafe account and CNY balance.")
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Revoke this Skill login and clear local state; the browser session and node binding remain.",
    )
    parser.add_argument(
        "--check-evomap",
        action="store_true",
        help="Read-only check of local EvoMap install status (no side effects).",
    )
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Check backend reachability via GET /menu (read-only, no side effects). Run this first.",
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="List available coffees via GET /menu (read-only). Use exact names in --message.",
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

    cached_config = read_json(CONFIG_PATH, {})
    cached_config = cached_config if isinstance(cached_config, dict) else {}
    args.base_url, address_source = resolve_base_url(
        explicit=args.base_url,
        environment=os.getenv("RESTAURANT_API_BASE"),
        cached=cached_config,
        force_discovery=args.discover,
    )
    if address_source != "cache":
        cached_config.update(
            {
                "base_url": args.base_url,
                "source": address_source,
                "validated_at": int(time.time()),
            }
        )
        write_json(CONFIG_PATH, cached_config)
    if args.discover:
        print(json.dumps({
            "ok": True,
            "base_url": args.base_url,
            "source": address_source,
            "status": "validated",
        }, ensure_ascii=False, indent=2))
        return 0

    if args.payment_proof:
        print(
            "⚠️ --payment-proof 已弃用并被忽略：后端拒绝客户端伪造的支付凭证，付费请用 --evomap-node-secret。",
            file=sys.stderr,
        )

    root = Path.cwd()
    state = read_json(STATE_PATH, {})
    try:
        if args.login:
            registration = login_account(args, root, state)
            print(json.dumps(redact_for_stdout(registration), ensure_ascii=False, indent=2))
            return 0
        if args.logout:
            print(json.dumps(logout_account(args, state), ensure_ascii=False, indent=2))
            return 0
        registration = require_logged_in(args, state)
        if args.ping:
            return cmd_ping(args, registration)
        if args.menu:
            return cmd_menu(args, registration)
        if args.me:
            print(json.dumps(redact_for_stdout(registration), ensure_ascii=False, indent=2))
            return 0
        if args.register_only:
            print("--register-only is deprecated; the Skill is already linked through web login.", file=sys.stderr)
            output = redact_for_stdout(registration)
            output["state_path"] = str(STATE_PATH)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        if not args.message:
            raise SystemExit("Use --discover, --login, --me, --ping, --menu, --logout, or --message")
        result = submit_order(args, registration)
    except ApiError as exc:
        print(f"请求失败: HTTP {exc.status}", file=sys.stderr)
        print(json.dumps(redact_for_stdout(exc.body), ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(redact_for_stdout(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
