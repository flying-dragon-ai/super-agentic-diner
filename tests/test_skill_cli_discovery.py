from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents" / "skills" / "a2a-super-order" / "scripts" / "order.py"
SPEC = importlib.util.spec_from_file_location("a2a_super_order_cli", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def test_explicit_address_is_validated_and_has_priority(monkeypatch) -> None:
    probed: list[str] = []

    def probe(url: str, timeout: float = 2.0) -> bool:
        probed.append(url)
        return url == "https://cafe.example"

    monkeypatch.setattr(cli, "probe_cafe_service", probe)
    result = cli.resolve_base_url(
        explicit="https://cafe.example/",
        environment="https://ignored.example",
        cached={"base_url": "http://127.0.0.1:8000"},
    )

    assert result == ("https://cafe.example", "argument")
    assert probed == ["https://cafe.example"]


def test_invalid_explicit_address_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(cli, "probe_cafe_service", lambda *_args, **_kwargs: False)
    with pytest.raises(SystemExit, match="无法验证 argument"):
        cli.resolve_base_url(
            explicit="https://wrong.example",
            environment=None,
            cached={},
        )


def test_stale_cache_recovers_to_local_service(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "probe_cafe_service",
        lambda url, timeout=2.0: url == "http://127.0.0.1:8001",
    )
    result = cli.resolve_base_url(
        explicit=None,
        environment=None,
        cached={"base_url": "http://192.168.1.20:8000"},
    )
    assert result == ("http://127.0.0.1:8001", "localhost")


def test_force_discovery_skips_cache_and_accepts_verified_lan_offer(monkeypatch) -> None:
    monkeypatch.setattr(cli, "LOCAL_BASE_URLS", ())
    monkeypatch.setattr(cli, "discover_lan_base_url", lambda _port: "http://192.168.1.50:8000")
    result = cli.resolve_base_url(
        explicit=None,
        environment=None,
        cached={"base_url": "https://cached.example"},
        force_discovery=True,
    )
    assert result == ("http://192.168.1.50:8000", "lan")


@pytest.mark.parametrize(
    "value",
    ["ftp://cafe.example", "http://user:pass@cafe.example", "not-a-url"],
)
def test_normalize_base_url_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        cli.normalize_base_url(value)
