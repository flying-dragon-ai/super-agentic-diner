"""Fail-closed test environment bootstrap and integration-test gates.

Import this module before importing :mod:`app` from every test module.  The
default path is deliberately hermetic: a process-scoped temporary SQLite
database, fakeredis, no real LLM credentials, and no outbound socket access.

Networked test suites have separate, explicit opt-ins:

* live HTTP: ``RUN_LIVE_TESTS=1`` + ``LIVE_TEST_BASE_URL`` +
  ``LIVE_TEST_INSTANCE_ID``; port 8000 is rejected because it is the normal
  developer service and may contain valuable local data.
* MySQL: ``RUN_MYSQL_INTEGRATION=1`` + ``DB_MODE=mysql`` + an explicitly
  supplied ``MYSQL_DATABASE`` whose name ends in ``_test``.

The gates only validate configuration.  They never probe a server or database
while tests are being collected.
"""
from __future__ import annotations

import atexit
import os
import shutil
import socket
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class UnsafeTestEnvironmentError(RuntimeError):
    """Raised before collection can touch an unsafe external target."""


class UnexpectedNetworkAccess(RuntimeError):
    """Raised when a default test attempts to open a real network socket."""


@dataclass(frozen=True)
class LiveTestConfig:
    enabled: bool
    reason: str
    base_url: str | None = None
    instance_id: str | None = None


@dataclass(frozen=True)
class MysqlTestConfig:
    enabled: bool
    reason: str
    database: str | None = None


def _value(environ: Mapping[str, str], name: str) -> str:
    return (environ.get(name) or "").strip()


def live_test_config(environ: Mapping[str, str] | None = None) -> LiveTestConfig:
    env = os.environ if environ is None else environ
    if _value(env, "RUN_LIVE_TESTS") != "1":
        return LiveTestConfig(False, "set RUN_LIVE_TESTS=1 to enable live HTTP tests")

    raw_url = _value(env, "LIVE_TEST_BASE_URL")
    if not raw_url:
        return LiveTestConfig(False, "LIVE_TEST_BASE_URL is required")
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        return LiveTestConfig(False, f"LIVE_TEST_BASE_URL is invalid: {exc}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return LiveTestConfig(False, "LIVE_TEST_BASE_URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        return LiveTestConfig(False, "LIVE_TEST_BASE_URL must not contain credentials")
    if port == 8000:
        return LiveTestConfig(False, "port 8000 is reserved for the normal developer service")

    instance_id = _value(env, "LIVE_TEST_INSTANCE_ID")
    if not instance_id:
        return LiveTestConfig(False, "LIVE_TEST_INSTANCE_ID is required")

    normalized = raw_url.rstrip("/")
    return LiveTestConfig(True, "live HTTP test target explicitly enabled", normalized, instance_id)


def require_live_test_config(
    environ: Mapping[str, str] | None = None,
) -> LiveTestConfig:
    config = live_test_config(environ)
    if not config.enabled:
        raise UnsafeTestEnvironmentError(config.reason)
    return config


def mysql_test_config(environ: Mapping[str, str] | None = None) -> MysqlTestConfig:
    env = os.environ if environ is None else environ
    if _value(env, "RUN_MYSQL_INTEGRATION") != "1":
        return MysqlTestConfig(
            False,
            "set RUN_MYSQL_INTEGRATION=1 to enable MySQL integration tests",
        )
    if _value(env, "DB_MODE").lower() != "mysql":
        return MysqlTestConfig(False, "DB_MODE=mysql is required")

    database = _value(env, "MYSQL_DATABASE")
    if not database:
        return MysqlTestConfig(False, "MYSQL_DATABASE must be explicitly supplied")
    if not database.lower().endswith("_test"):
        return MysqlTestConfig(False, "MYSQL_DATABASE must end in _test")
    return MysqlTestConfig(True, "disposable MySQL test database explicitly enabled", database)


def require_mysql_test_config(
    environ: Mapping[str, str] | None = None,
) -> MysqlTestConfig:
    config = mysql_test_config(environ)
    if not config.enabled:
        raise UnsafeTestEnvironmentError(config.reason)
    return config


_TEMP_ROOT = (
    Path(tempfile.gettempdir())
    / "crossroads-agent-cafe-tests"
    / f"process-{os.getpid()}"
)
_TEMP_DB = _TEMP_ROOT / "test.sqlite3"
_NETWORK_BLOCKED = False

_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_SOCKET_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_SOCKETPAIR = socket.socketpair
_SOCKETPAIR_STATE = threading.local()


def _inside_socketpair() -> bool:
    return bool(getattr(_SOCKETPAIR_STATE, "active", False))


def _blocked_connect(sock: socket.socket, address) -> None:
    if sock.family in {socket.AF_INET, socket.AF_INET6} and not _inside_socketpair():
        raise UnexpectedNetworkAccess(
            f"default tests cannot open network sockets (attempted {address!r})"
        )
    return _ORIGINAL_SOCKET_CONNECT(sock, address)


def _blocked_connect_ex(sock: socket.socket, address) -> int:
    if sock.family in {socket.AF_INET, socket.AF_INET6} and not _inside_socketpair():
        raise UnexpectedNetworkAccess(
            f"default tests cannot open network sockets (attempted {address!r})"
        )
    return _ORIGINAL_SOCKET_CONNECT_EX(sock, address)


def _blocked_create_connection(address, *args, **kwargs):
    raise UnexpectedNetworkAccess(
        f"default tests cannot open network sockets (attempted {address!r})"
    )


def _internal_socketpair(*args, **kwargs):
    previous = _inside_socketpair()
    _SOCKETPAIR_STATE.active = True
    try:
        return _ORIGINAL_SOCKETPAIR(*args, **kwargs)
    finally:
        _SOCKETPAIR_STATE.active = previous


def _install_network_block() -> None:
    global _NETWORK_BLOCKED
    if _NETWORK_BLOCKED:
        return
    socket.socket.connect = _blocked_connect
    socket.socket.connect_ex = _blocked_connect_ex
    socket.create_connection = _blocked_create_connection
    socket.socketpair = _internal_socketpair
    _NETWORK_BLOCKED = True


def network_is_blocked() -> bool:
    return _NETWORK_BLOCKED


def default_sqlite_path() -> Path:
    return _TEMP_DB


def _cleanup_temp_database() -> None:
    try:
        try:
            from app.db.database import engine

            engine.dispose()
        except (ImportError, RuntimeError):
            pass
        temp_base = Path(tempfile.gettempdir()).resolve()
        target = _TEMP_ROOT.resolve()
        if temp_base not in target.parents or target.name != f"process-{os.getpid()}":
            return
        shutil.rmtree(target, ignore_errors=True)
    except OSError:
        # A Windows process may still hold a SQLite handle during interpreter
        # shutdown.  The isolated file remains under the OS temp directory and
        # never under the repository or beside coffee_ai.db.
        return


def _initialize_temp_schema() -> None:
    # Import only after the environment has been forced to the isolated
    # database.  This makes DB-using tests safe even when run individually.
    from app.db import models as _models  # noqa: F401
    from app.db.database import Base, engine

    Base.metadata.create_all(bind=engine)


def _disable_runtime_process_launches() -> None:
    # app.main imports this function by value.  Replacing it before app.main is
    # imported prevents a TestClient startup from spawning Node/npx or opening
    # a Colyseus port during an otherwise in-process unit test.
    from app import colyseus_bridge

    colyseus_bridge.start_colyseus_server = lambda: None


def _bootstrap() -> None:
    live_requested = _value(os.environ, "RUN_LIVE_TESTS") == "1"
    mysql_requested = _value(os.environ, "RUN_MYSQL_INTEGRATION") == "1"
    if live_requested and mysql_requested:
        raise UnsafeTestEnvironmentError(
            "live HTTP and MySQL integration suites must run in separate processes"
        )

    if mysql_requested:
        require_mysql_test_config()
        return

    _TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ["DB_MODE"] = "sqlite"
    os.environ["SQLITE_PATH"] = str(_TEMP_DB)
    os.environ["USE_FAKEREDIS"] = "true"
    os.environ["SKILL_RECONCILE_ENABLED"] = "false"
    os.environ["AUTONOMOUS_AGENT_ENABLED"] = "false"
    os.environ["A2A_DISCOVERY_ENABLED"] = "false"
    # Empty environment variables override values that may exist in a local
    # .env file, preventing accidental LLM/EvoMap calls from unit tests.
    os.environ["LLM_API_KEY"] = ""
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["EVOMAP_NODE_SECRET"] = ""

    if live_requested:
        require_live_test_config()
    else:
        _install_network_block()
    _initialize_temp_schema()
    _disable_runtime_process_launches()


_bootstrap()
atexit.register(_cleanup_temp_database)
