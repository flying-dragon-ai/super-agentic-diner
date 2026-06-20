"""Lifecycle manager for the Colyseus coffee_room server.

Starts the Node+TS Colyseus server (colyseus-server/) as a subprocess on FastAPI
startup and terminates it on shutdown. Connection parameters come from .env via
environment variables; no secrets are hard-coded.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COLYSEUS_DIR = _REPO_ROOT / "colyseus-server"
_DIST_SERVER = _COLYSEUS_DIR / "dist" / "Server.js"

_proc: Optional[subprocess.Popen] = None
_lock = threading.Lock()


def _port() -> int:
    return int(os.environ.get("COLYSEUS_PORT", "2567"))


def start_colyseus_server() -> Optional[subprocess.Popen]:
    """Launch the Colyseus server subprocess if not already running.

    Prefers compiled dist/Server.js (run `npm run build` in colyseus-server).
    Falls back to tsx in dev when dist is missing. Safe to call repeatedly.
    """
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return _proc
        if not _COLYSEUS_DIR.is_dir():
            logger.warning("colyseus-server not found at %s; skip launch", _COLYSEUS_DIR)
            return None
        env = os.environ.copy()
        env["COLYSEUS_PORT"] = str(_port())
        try:
            if _DIST_SERVER.is_file():
                cmd = ["node", str(_DIST_SERVER)]
            else:
                cmd = ["npx", "--yes", "tsx", "src/Server.ts"]
            _proc = subprocess.Popen(
                cmd,
                cwd=str(_COLYSEUS_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            logger.info("Colyseus starting on port %s (pid=%s)", _port(), _proc.pid)
            _drain_in_background(_proc)
            return _proc
        except FileNotFoundError as exc:
            logger.warning("Node/tsx not found; Colyseus not started: %s", exc)
            return None
        except Exception:
            logger.exception("Failed to start Colyseus server")
            return None


def _drain_in_background(proc: subprocess.Popen) -> None:
    def _pump() -> None:
        try:
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    logger.info("[colyseus] %s", line)
        except Exception:
            pass

    threading.Thread(target=_pump, daemon=True, name="colyseus-stdout").start()


def stop_colyseus_server() -> None:
    global _proc
    with _lock:
        proc = _proc
        _proc = None
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info("Colyseus server stopped")
    except Exception:
        logger.exception("Error stopping Colyseus server")


def bridge_event_to_colyseus(event: dict) -> None:
    """Forward a visualization event to coffee_room.

    Stage 0 stub: actual push into Colyseus is wired in stage 5. For now we
    only log at debug so the integration point is explicit.
    """
    etype = event.get("type")
    if not etype:
        return
    logger.debug("bridge event -> colyseus: %s", etype)


__all__ = ["start_colyseus_server", "stop_colyseus_server", "bridge_event_to_colyseus"]
