"""Best-effort UDP discovery for trusted-LAN A2A Skill clients."""
from __future__ import annotations

import json
import logging
import re
import socket
import threading


SERVICE_ID = "crossroads-agent-cafe"
PROTOCOL_VERSION = 1
DISCOVER_TYPE = "crossroads-cafe-discover"
OFFER_TYPE = "crossroads-cafe-offer"
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_socket: socket.socket | None = None


def discovery_document() -> dict[str, object]:
    return {
        "service": SERVICE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "name": "Crossroads Agent Café",
    }


def _serve(udp_port: int, http_port: int, scheme: str) -> None:
    global _socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", udp_port))
        sock.settimeout(0.5)
        with _lock:
            _socket = sock
        logger.info("A2A LAN discovery listening on UDP %s", udp_port)
        while not _stop_event.is_set():
            try:
                raw, peer = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                request = json.loads(raw.decode("utf-8"))
                nonce = request.get("nonce") if isinstance(request, dict) else None
                if (
                    not isinstance(request, dict)
                    or request.get("type") != DISCOVER_TYPE
                    or request.get("version") != PROTOCOL_VERSION
                    or not isinstance(nonce, str)
                    or not _NONCE_RE.fullmatch(nonce)
                ):
                    continue
                offer = {
                    "type": OFFER_TYPE,
                    "version": PROTOCOL_VERSION,
                    "service": SERVICE_ID,
                    "nonce": nonce,
                    "scheme": scheme,
                    "http_port": http_port,
                }
                sock.sendto(
                    json.dumps(offer, separators=(",", ":")).encode("utf-8"), peer
                )
            except (UnicodeDecodeError, ValueError, OSError):
                continue
    except OSError as exc:
        logger.warning("A2A LAN discovery disabled: UDP %s unavailable (%s)", udp_port, exc)
    finally:
        with _lock:
            if _socket is sock:
                _socket = None
        sock.close()


def start_listener(*, enabled: bool, udp_port: int, http_port: int, scheme: str) -> None:
    """Start one daemon responder per process without blocking application startup."""
    global _thread
    if not enabled:
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_serve,
            kwargs={"udp_port": udp_port, "http_port": http_port, "scheme": scheme},
            name="a2a-lan-discovery",
            daemon=True,
        )
        _thread.start()


def stop_listener() -> None:
    global _thread
    _stop_event.set()
    with _lock:
        sock = _socket
        thread = _thread
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.5)
    with _lock:
        _thread = None
