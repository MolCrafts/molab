"""The CLI must open a remote workspace through the mirror cache.

Without this the CLI pays one SSH round-trip per ``exists`` / ``stat`` /
``listdir`` on a tree it is about to walk in full, which is the difference
between ``molexp workspace info`` on a remote workspace taking a second and
taking minutes. The assertions are about which filesystem class is
constructed and whether the tree is warmed — not about SSH actually working.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from molexp.workspace.fs_cached import CachedRemoteFileSystem
from molexp.workspace.fs_local import LocalFileSystem
from molexp.workspace.fs_remote import RemoteFileSystem
from molexp.workspace.target import (
    LocalTarget,
    RemoteTarget,
    remote_cache_root,
    target_to_filesystem,
)


class _StubTransport:
    """Stands in for an SSH transport; never contacted by these tests."""

    def __init__(self, *_a: object, **_kw: object) -> None:
        self.options = SimpleNamespace(host="h")


@pytest.fixture
def no_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``SshTransport`` construction inert so no connection is attempted."""
    import molq.transport as mt

    monkeypatch.setattr(mt, "SshTransport", _StubTransport)


class TestTargetToFilesystem:
    @pytest.mark.unit
    def test_remote_target_is_wrapped_in_the_mirror_cache(
        self, no_ssh: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
        target = RemoteTarget(path="/scratch/ws", host="host.example")

        fs = target_to_filesystem(target)

        assert isinstance(fs, CachedRemoteFileSystem)
        # A decorator over the SSH filesystem, not a substitute for it.
        assert isinstance(fs.inner, RemoteFileSystem)
        assert fs.mirror_root.is_relative_to(tmp_path / ".molexp" / "remote_cache")

    @pytest.mark.unit
    def test_cache_is_pinned_but_revalidated_once_per_process(
        self, no_ssh: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Pinning without ``revalidate_before`` would serve yesterday's tree."""
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
        target = RemoteTarget(path="/scratch/ws", host="host.example")

        fs = target_to_filesystem(target)

        assert fs.ttl_seconds > 0, "a per-call stat would put SSH back on every read"
        assert fs._revalidate_before is not None, "a CLI run must see fresh data once"

    @pytest.mark.unit
    def test_cached_false_yields_the_bare_transport(self, no_ssh: None) -> None:
        target = RemoteTarget(path="/scratch/ws", host="host.example")

        fs = target_to_filesystem(target, cached=False)

        assert isinstance(fs, RemoteFileSystem)

    @pytest.mark.unit
    def test_local_target_is_unaffected(self) -> None:
        fs = target_to_filesystem(LocalTarget(path="/tmp/ws"))
        assert isinstance(fs, LocalFileSystem)

    @pytest.mark.unit
    def test_two_remotes_never_share_a_mirror(self) -> None:
        """A shared mirror across hosts would serve one workspace's tree for another."""
        a = remote_cache_root(RemoteTarget(path="/data/ws", host="alpha"))
        b = remote_cache_root(RemoteTarget(path="/data/ws", host="beta"))
        c = remote_cache_root(RemoteTarget(path="/other/ws", host="alpha"))

        assert a != b, "same path on different hosts must not collide"
        assert a != c, "different paths on one host must not collide"


class TestOpenWorkspacePrefetch:
    @pytest.mark.unit
    def test_prefetch_warms_the_tree_for_listing_commands(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molexp.cli import _target as cli_target

        calls: list[dict] = []

        class _FS(LocalFileSystem):
            def prepare(self, ws: object, **kwargs: object) -> list:
                calls.append(kwargs)
                return []

        root = tmp_path / "ws"
        root.mkdir()
        (root / "workspace.json").write_text('{"id":"ws","name":"ws"}')
        target = LocalTarget(path=str(root))
        monkeypatch.setattr(
            cli_target, "resolve_workspace_target", lambda _s: (target, None, _FS())
        )

        cli_target.open_workspace(str(root), prefetch=True)

        assert calls == [{"block_index": True, "refresh_on_open": True}]

    @pytest.mark.unit
    def test_prefetch_failure_does_not_break_the_command(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A cold cache or a flaky link must degrade to slow, not to broken."""
        from molexp.cli import _target as cli_target

        class _FS(LocalFileSystem):
            def prepare(self, ws: object, **kwargs: object) -> list:
                raise ConnectionError("ssh dropped")

        root = tmp_path / "ws"
        root.mkdir()
        (root / "workspace.json").write_text('{"id":"ws","name":"ws"}')
        target = LocalTarget(path=str(root))
        monkeypatch.setattr(
            cli_target, "resolve_workspace_target", lambda _s: (target, None, _FS())
        )

        _t, _tr, _fs, ws = cli_target.open_workspace(str(root), prefetch=True)

        assert ws.root is not None

    @pytest.mark.unit
    def test_no_prefetch_on_a_plain_local_filesystem(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``prepare`` does not exist locally; asking for it must not raise."""
        from molexp.cli import _target as cli_target

        root = tmp_path / "ws"
        root.mkdir()
        (root / "workspace.json").write_text('{"id":"ws","name":"ws"}')
        target = LocalTarget(path=str(root))
        monkeypatch.setattr(
            cli_target,
            "resolve_workspace_target",
            lambda _s: (target, None, LocalFileSystem()),
        )

        _t, _tr, _fs, ws = cli_target.open_workspace(str(root), prefetch=True)

        assert ws.root is not None
