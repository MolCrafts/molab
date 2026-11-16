"""Tests for ``molab.server.app`` — ``create_app`` and its ``lifespan``.

After D86 the server copies nothing from the operator config file into
``molab.config`` (the agent bridge left with the harness), and the lifespan
runs each discovered server plugin's startup/shutdown hook with no global
shutdown flag. molab registers no server plugin of its own, so the app must
boot with an empty ``molab.server_plugins`` group (D-1).

Plugin discovery is faked by patching ``molab.plugins.server``'s own
``importlib_metadata`` binding — no other entry-point consumer sees it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import molab
from molab.plugins import server as server_mod
from molab.plugins.server import ServerPlugin, _discover_server_uncached
from molab.server.app import create_app
from molab.services import operator_config


class _FakeEntryPoint:
    """Minimal ``importlib.metadata.EntryPoint`` substitute."""

    def __init__(self, name: str, plugin: ServerPlugin) -> None:
        self.name = name
        self.group = "molab.server_plugins"
        self._plugin = plugin

    def load(self) -> ServerPlugin:
        return self._plugin


def _install_fake_plugins(monkeypatch: pytest.MonkeyPatch, *plugins: ServerPlugin) -> None:
    eps = tuple(_FakeEntryPoint(p.id, p) for p in plugins)

    class _FakeEntryPoints:
        def select(self, *, group: str) -> tuple[_FakeEntryPoint, ...]:
            return tuple(ep for ep in eps if ep.group == group)

    monkeypatch.setattr(
        server_mod,
        "importlib_metadata",
        SimpleNamespace(entry_points=lambda: _FakeEntryPoints()),
    )
    _discover_server_uncached.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_discovery_cache() -> Iterator[None]:
    """Never leak a fake plugin set into a later test through the cache."""
    _discover_server_uncached.cache_clear()
    yield
    _discover_server_uncached.cache_clear()


class TestCreateApp:
    def test_does_not_copy_operator_config_into_molab_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The conftest points ``OPERATOR_CONFIG_PATH`` at a tmp file and
        restores ``molab.config`` afterwards, so this writes nothing real."""
        _install_fake_plugins(monkeypatch)
        operator_config.OPERATOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        operator_config.OPERATOR_CONFIG_PATH.write_text(
            json.dumps({"agent": {"model": "x:y", "deepseek_api_key": "sk-test"}}),
            encoding="utf-8",
        )
        assert "agent.model" not in molab.config  # precondition: nothing in code

        create_app(serve_static=False)

        assert "agent.model" not in molab.config
        assert "deepseek_api_key" not in molab.config


class TestLifespan:
    def test_plugin_hooks_run_once_each(self, monkeypatch: pytest.MonkeyPatch) -> None:
        counts = {"startup": 0, "shutdown": 0}

        def _startup() -> None:
            counts["startup"] += 1

        def _shutdown() -> None:
            counts["shutdown"] += 1

        plugin = ServerPlugin(
            id="counter",
            name="Counter",
            version="1.0.0",
            register=lambda router: None,  # noqa: ARG005
            startup=_startup,
            shutdown=_shutdown,
        )
        _install_fake_plugins(monkeypatch, plugin)

        with TestClient(create_app(serve_static=False)):
            assert counts == {"startup": 1, "shutdown": 0}

        assert counts == {"startup": 1, "shutdown": 1}

    def test_boots_with_zero_plugins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_plugins(monkeypatch)
        app = create_app(serve_static=False)

        with TestClient(app):
            pass

        assert app.openapi()["paths"]
