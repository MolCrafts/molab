"""Tests for ``molab.plugins.server`` — the server plugin layer.

Covers ``discover_server_plugins()``'s entry-point walk over the
``molab.server_plugins`` group (cache + failure isolation + api-version
gating + first-wins de-duplication + empty discovery) and
``signal_shutdown_server_plugins()``'s failure isolation. molab itself
registers no server plugin (D86), so the empty group is the default boot
path and is pinned here (D-1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from types import SimpleNamespace

import pytest

from molab.plugins import server as server_mod
from molab.plugins.server import (
    SERVER_PLUGIN_API_VERSION,
    ServerPlugin,
    _discover_server_uncached,
    discover_server_plugins,
    signal_shutdown_server_plugins,
)

# ── discovery fixtures + helpers ──────────────────────────────────────────


class _FakeEntryPoint:
    """Minimal ``importlib.metadata.EntryPoint`` substitute."""

    def __init__(
        self,
        name: str,
        loader: Callable[[], object],
        *,
        group: str = "molab.server_plugins",
    ) -> None:
        self.name = name
        self.group = group
        self._loader = loader

    def load(self) -> object:
        return self._loader()


def _install_fake_eps(
    monkeypatch: pytest.MonkeyPatch,
    eps: Iterable[_FakeEntryPoint],
) -> list[int]:
    """Install fake entry points and return a call-counter list.

    Patches only ``molab.plugins.server``'s own ``importlib_metadata``
    binding, so no other entry-point consumer in the process sees the fakes.
    The returned ``list[int]`` has length 1 and tracks how many times the
    patched ``entry_points()`` callable is invoked — used by the cache test to
    assert the second call hits the cache.
    """
    eps_tuple = tuple(eps)
    call_count = [0]

    class _FakeEntryPoints:
        def select(self, *, group: str) -> tuple[_FakeEntryPoint, ...]:
            return tuple(ep for ep in eps_tuple if ep.group == group)

    def _entry_points() -> _FakeEntryPoints:
        call_count[0] += 1
        return _FakeEntryPoints()

    monkeypatch.setattr(
        server_mod, "importlib_metadata", SimpleNamespace(entry_points=_entry_points)
    )
    # Cached state must be cleared so the test sees the patched eps
    _discover_server_uncached.cache_clear()
    return call_count


@pytest.fixture(autouse=True)
def _fresh_discovery_cache() -> Iterator[None]:
    """Never leak a fake plugin set into a later test through the cache."""
    _discover_server_uncached.cache_clear()
    yield
    _discover_server_uncached.cache_clear()


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Spy on ``molab.plugins.server.logger.warning`` calls.

    mollog bypasses stdlib ``logging`` so pytest's ``caplog`` / ``capfd``
    do not see its output; we capture the messages directly.
    """
    captured: list[str] = []
    monkeypatch.setattr(
        server_mod.logger,
        "warning",
        lambda msg, **_: captured.append(str(msg)),
    )
    return captured


def _make_plugin(
    plugin_id: str = "alpha",
    *,
    api_version: str = SERVER_PLUGIN_API_VERSION,
    signal_shutdown: Callable[[], None] | None = None,
) -> ServerPlugin:
    return ServerPlugin(
        id=plugin_id,
        name=plugin_id.title(),
        version="1.0.0",
        register=lambda router: None,  # noqa: ARG005
        signal_shutdown=signal_shutdown,
        api_version=api_version,
    )


class TestDiscoverServerPlugins:
    def test_happy_path_returns_tuple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        valid = _make_plugin("alpha")
        _install_fake_eps(monkeypatch, [_FakeEntryPoint("alpha", lambda: valid)])

        result = discover_server_plugins()

        assert isinstance(result, tuple)
        assert result == (valid,)

    def test_failing_entry_point_is_isolated(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        valid = _make_plugin("good")

        def boom() -> object:
            raise ImportError("missing dep")

        _install_fake_eps(
            monkeypatch,
            [
                _FakeEntryPoint("bad", boom),
                _FakeEntryPoint("good", lambda: valid),
            ],
        )

        result = discover_server_plugins()

        assert result == (valid,)
        assert any("bad" in msg for msg in warnings)

    def test_non_serverplugin_object_is_filtered(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        _install_fake_eps(
            monkeypatch,
            [_FakeEntryPoint("not-a-plugin", lambda: object())],
        )

        result = discover_server_plugins()

        assert result == ()
        assert any("ServerPlugin" in msg for msg in warnings)

    def test_wrong_api_version_is_filtered(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        future = _make_plugin("future", api_version="999")
        valid = _make_plugin("now")
        _install_fake_eps(
            monkeypatch,
            [
                _FakeEntryPoint("future", lambda: future),
                _FakeEntryPoint("now", lambda: valid),
            ],
        )

        result = discover_server_plugins()

        assert result == (valid,)
        assert any("api_version" in msg for msg in warnings)

    def test_duplicate_id_first_wins(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        first = _make_plugin("dup")
        second = _make_plugin("dup")
        assert first is not second  # sanity: distinct objects, same id

        _install_fake_eps(
            monkeypatch,
            [
                _FakeEntryPoint("first", lambda: first),
                _FakeEntryPoint("second", lambda: second),
            ],
        )

        result = discover_server_plugins()

        assert result == (first,)
        assert any("duplicate" in msg.lower() for msg in warnings)

    def test_cache_hits_on_second_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        valid = _make_plugin("cached")
        call_count = _install_fake_eps(
            monkeypatch,
            [_FakeEntryPoint("cached", lambda: valid)],
        )

        first = discover_server_plugins()
        calls_after_first = call_count[0]
        second = discover_server_plugins()

        assert first == second == (valid,)
        # entry_points() must NOT be called again on the cached path
        assert call_count[0] == calls_after_first
        assert calls_after_first == 1

    def test_empty_group_discovers_nothing_quietly(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        """D-1: molab ships no server plugin, so an empty group is the norm."""
        _install_fake_eps(monkeypatch, [])

        assert discover_server_plugins() == ()
        assert warnings == []


class TestSignalShutdownServerPlugins:
    def test_a_raising_hook_does_not_stop_the_next(
        self,
        monkeypatch: pytest.MonkeyPatch,
        warnings: list[str],
    ) -> None:
        calls: list[str] = []

        def boom() -> None:
            calls.append("first")
            raise RuntimeError("wake failed")

        first = _make_plugin("first", signal_shutdown=boom)
        second = _make_plugin("second", signal_shutdown=lambda: calls.append("second"))
        _install_fake_eps(
            monkeypatch,
            [
                _FakeEntryPoint("first", lambda: first),
                _FakeEntryPoint("second", lambda: second),
            ],
        )

        signal_shutdown_server_plugins()

        assert calls == ["first", "second"]
        assert any("first" in msg for msg in warnings)

    def test_no_plugins_is_a_no_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_eps(monkeypatch, [])

        signal_shutdown_server_plugins()
