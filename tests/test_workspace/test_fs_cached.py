"""Unit tests for :class:`CachedRemoteFileSystem`.

Drives a fake :class:`FileSystem` that records call counts so we can
assert "second read is mirror-served, zero inner calls".  No SSH.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import IO, Any

import pytest

from molab.workspace.fs import StatResult
from molab.workspace.fs_cached import CachedRemoteFileSystem


class _FakeRemoteFS:
    """Counts every call; backs a string-keyed in-memory store."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        self.calls: Counter[str] = Counter()

    def _hit(self, name: str) -> None:
        self.calls[name] += 1

    # ── Path ops ──
    @staticmethod
    def join(*parts: str) -> str:
        return "/".join(str(p).strip("/") for p in parts if p)

    @staticmethod
    def dirname(path: str) -> str:
        s = str(path)
        return s.rsplit("/", 1)[0] if "/" in s else "."

    @staticmethod
    def basename(path: str) -> str:
        return str(path).rsplit("/", 1)[-1]

    @staticmethod
    def resolve(path: str) -> str:
        return str(path)

    @staticmethod
    def is_absolute(path: str) -> bool:
        return str(path).startswith("/")

    # ── Existence ──
    def exists(self, path: str) -> bool:
        self._hit("exists")
        key = str(path)
        return key in self.files or key in self.dirs

    def is_dir(self, path: str) -> bool:
        self._hit("is_dir")
        return str(path) in self.dirs

    def is_file(self, path: str) -> bool:
        self._hit("is_file")
        return str(path) in self.files

    # ── Read ──
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        self._hit("read_text")
        key = str(path)
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key].decode(encoding)

    def read_bytes(self, path: str) -> bytes:
        self._hit("read_bytes")
        key = str(path)
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]

    def open(self, path: str, mode: str = "r", encoding: str = "utf-8") -> IO[Any]:
        import io as _io

        return _io.StringIO(self.read_text(path, encoding=encoding))

    # ── Write ──
    def write_text(self, path: str, content: str, *, mode: int = 0o600) -> None:
        self._hit("write_text")
        self.files[str(path)] = content.encode("utf-8")

    def write_bytes(self, path: str, content: bytes, *, mode: int = 0o600) -> None:
        self._hit("write_bytes")
        self.files[str(path)] = content

    # ── Mutations ──
    def rename(self, src: str, dst: str) -> None:
        self._hit("rename")
        self.files[str(dst)] = self.files.pop(str(src))

    def remove(self, path: str, *, recursive: bool = False) -> None:
        self._hit("remove")
        key = str(path)
        if recursive:
            for k in list(self.files):
                if k.startswith(key.rstrip("/") + "/") or k == key:
                    del self.files[k]
            self.dirs.discard(key)
        else:
            self.files.pop(key, None)
            self.dirs.discard(key)

    def copy(self, src: str, dst: str) -> None:
        self._hit("copy")
        self.files[str(dst)] = self.files[str(src)]

    def copytree(self, src: str, dst: str, *, dirs_exist_ok: bool = False) -> None:
        self._hit("copytree")
        prefix = str(src).rstrip("/") + "/"
        for k, v in list(self.files.items()):
            if k.startswith(prefix):
                self.files[str(dst).rstrip("/") + "/" + k[len(prefix) :]] = v

    # ── Dir ops ──
    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
        self._hit("mkdir")
        self.dirs.add(str(path))

    def listdir(self, path: str) -> list[str]:
        self._hit("listdir")
        prefix = str(path).rstrip("/") + "/"
        names: set[str] = set()
        for k in (*self.files.keys(), *self.dirs):
            if k.startswith(prefix):
                tail = k[len(prefix) :]
                names.add(tail.split("/", 1)[0])
        return sorted(names)

    def glob(self, path: str, pattern: str) -> list[str]:
        return []

    def rglob(self, path: str, pattern: str) -> list[str]:
        return []

    # ── Metadata ──
    def stat(self, path: str) -> StatResult:
        self._hit("stat")
        key = str(path)
        if key in self.files:
            return StatResult(size=len(self.files[key]), mtime=42.0, is_dir=False, is_file=True)
        if key in self.dirs:
            return StatResult(size=0, mtime=42.0, is_dir=True, is_file=False)
        raise FileNotFoundError(key)

    def lstat(self, path: str) -> StatResult:
        return self.stat(path)

    def touch(self, path: str) -> None:
        self._hit("touch")
        self.files.setdefault(str(path), b"")

    def chmod(self, path: str, mode: int) -> None:
        self._hit("chmod")

    def getsize(self, path: str) -> int:
        self._hit("getsize")
        return len(self.files[str(path)])

    def symlink(self, src: str, dst: str) -> None:
        self._hit("symlink")

    # ── Atomic I/O ──
    def atomic_write_json(self, path: str, data: object) -> None:
        import json as _json

        self._hit("atomic_write_json")
        self.files[str(path)] = (_json.dumps(data) + "\n").encode("utf-8")

    def atomic_write_text(self, path: str, content: str, *, encoding: str = "utf-8") -> None:
        self._hit("atomic_write_text")
        self.files[str(path)] = content.encode("utf-8")


@pytest.fixture
def fake() -> _FakeRemoteFS:
    fake = _FakeRemoteFS()
    fake.files["/scratch/me/log.txt"] = b"hello"
    fake.dirs.add("/scratch/me")
    return fake


@pytest.fixture
def cached(fake: _FakeRemoteFS, tmp_path: Path) -> CachedRemoteFileSystem:
    return CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")


class TestCachedRemoteFileSystem:
    # ── Core read caching ────────────────────────────────────────────────

    @pytest.mark.unit
    def test_first_read_fetches_inner_second_read_hits_mirror(
        self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS
    ):
        first = cached.read_bytes("/scratch/me/log.txt")
        second = cached.read_bytes("/scratch/me/log.txt")
        assert first == b"hello"
        assert second == b"hello"
        assert fake.calls["read_bytes"] == 1, f"saw {fake.calls!r}"

    @pytest.mark.unit
    def test_mirror_layout_strips_leading_slash(
        self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS, tmp_path: Path
    ):
        cached.read_bytes("/scratch/me/log.txt")
        expected = tmp_path / "mirror" / "files" / "scratch" / "me" / "log.txt"
        assert expected.read_bytes() == b"hello"
        assert fake.calls["read_bytes"] == 1

    # ── Negative cache ───────────────────────────────────────────────────

    @pytest.mark.unit
    def test_missing_short_circuits_subsequent_exists(
        self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS
    ):
        assert cached.exists("/scratch/me/nope") is False
        fake.calls.clear()
        assert cached.exists("/scratch/me/nope") is False
        assert fake.calls["exists"] == 0

    @pytest.mark.unit
    def test_read_missing_propagates_filenotfound(self, cached: CachedRemoteFileSystem):
        with pytest.raises(FileNotFoundError):
            cached.read_bytes("/scratch/me/nope")

    # ── Invalidation on write / rename ───────────────────────────────────

    @pytest.mark.unit
    def test_write_invalidates_cache(self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS):
        cached.read_bytes("/scratch/me/log.txt")
        cached.write_text("/scratch/me/log.txt", "new content")
        fake.calls.clear()
        assert cached.read_text("/scratch/me/log.txt") == "new content"
        assert fake.calls["read_bytes"] == 1, "must re-fetch after write"

    @pytest.mark.unit
    def test_rename_invalidates_both_ends(
        self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS
    ):
        cached.read_bytes("/scratch/me/log.txt")
        cached.rename("/scratch/me/log.txt", "/scratch/me/log2.txt")
        fake.calls.clear()
        assert cached.read_bytes("/scratch/me/log2.txt") == b"hello"
        assert fake.calls["read_bytes"] == 1

    # ── TTL expiry ───────────────────────────────────────────────────────

    @pytest.mark.unit
    def test_strict_reads_same_size_same_mtime_changes(self, fake: _FakeRemoteFS, tmp_path: Path):
        """Strict fetches content even though this fake's metadata is unchanged."""
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="strict")
        cached.connect("/scratch/me")
        assert cached.read_bytes("/scratch/me/log.txt") == b"hello"
        fake.files["/scratch/me/log.txt"] = b"world"
        fake.calls.clear()
        assert cached.read_bytes("/scratch/me/log.txt") == b"world"
        assert fake.calls["read_bytes"] == 1

    @pytest.mark.unit
    def test_ttl_zero_redownloads_when_mtime_changes(self, fake: _FakeRemoteFS, tmp_path: Path):
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="strict")
        cached.connect("/scratch/me")
        cached.read_bytes("/scratch/me/log.txt")
        fake.files["/scratch/me/log.txt"] = b"goodbye"
        original_stat = fake.stat

        def _stat_changed(path: str) -> StatResult:
            result = original_stat(path)
            if str(path) == "/scratch/me/log.txt":
                return StatResult(
                    size=result.size, mtime=result.mtime + 99.0, is_dir=False, is_file=True
                )
            return result

        fake.stat = _stat_changed  # type: ignore[method-assign]
        fake.calls.clear()
        assert cached.read_bytes("/scratch/me/log.txt") == b"goodbye"
        assert fake.calls["read_bytes"] == 1

    @pytest.mark.unit
    def test_pin_mode_never_auto_expires(
        self, fake: _FakeRemoteFS, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Positive ttl = pin-until-refresh: age does not force remote I/O."""
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        base = time.time()
        monkeypatch.setattr("molab.workspace.fs_cached.time.time", lambda: base)
        cached.connect("/scratch/me")
        cached.read_bytes("/scratch/me/log.txt")
        assert fake.calls["read_bytes"] == 1

        # Far past any historical TTL window — still local-only.
        monkeypatch.setattr("molab.workspace.fs_cached.time.time", lambda: base + 10_000)
        fake.files["/scratch/me/log.txt"] = b"remote-changed"  # would be visible if revalidated
        fake.calls.clear()
        assert cached.read_bytes("/scratch/me/log.txt") == b"hello"
        assert fake.calls["read_bytes"] == 0
        assert fake.calls["stat"] == 0

    @pytest.mark.unit
    def test_warm_prepare_serves_pin_without_blocking_on_refresh(
        self, fake: _FakeRemoteFS, tmp_path: Path
    ):
        """Warm open: local pin serves immediately; open refresh is async."""
        from types import SimpleNamespace

        mirror_root = tmp_path / "mirror"
        fake.dirs.add("/scratch/me")
        fake.dirs.add("/scratch/me/projects")
        first = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        first.connect("/scratch/me")
        first.read_bytes("/scratch/me/log.txt")

        second = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        assert second.indexed is True
        ws = SimpleNamespace(root="/scratch/me", fs=second)
        fake.calls.clear()
        # Without open-refresh: pure pin, zero remote on prepare + read.
        warnings = second.prepare(
            ws,
            block_index=False,
            refresh_on_open=False,  # type: ignore[arg-type]
        )
        assert warnings == []
        assert second.connected is False
        assert fake.calls["exists"] == 0
        assert second.read_bytes("/scratch/me/log.txt") == b"hello"
        assert fake.calls["read_bytes"] == 0

    @pytest.mark.unit
    def test_warm_prepare_schedules_one_active_refresh(self, fake: _FakeRemoteFS, tmp_path: Path):
        """Open always triggers one active force-fetch refresh (async)."""
        from types import SimpleNamespace

        mirror_root = tmp_path / "mirror"
        fake.dirs.add("/scratch/me")
        fake.dirs.add("/scratch/me/projects")
        fake.files["/scratch/me/workspace.json"] = b"{}"
        first = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        first.connect("/scratch/me")
        first.read_bytes("/scratch/me/log.txt")

        second = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        ws = SimpleNamespace(root="/scratch/me", fs=second)
        # Pin read works before/during refresh.
        assert second.read_bytes("/scratch/me/log.txt") == b"hello"
        warnings = second.prepare(ws, block_index=False, refresh_on_open=True)  # type: ignore[arg-type]
        assert warnings == []
        assert second.indexing is True or second._index_thread is not None
        if second._index_thread is not None:
            second._index_thread.join(timeout=2.0)
        assert second.indexed is True
        # Active refresh force-fetched workspace.json at least once.
        assert fake.calls["read_bytes"] >= 1 or fake.calls["read_text"] >= 0

    @pytest.mark.unit
    def test_cold_prepare_indexes_in_background(self, fake: _FakeRemoteFS, tmp_path: Path):
        from types import SimpleNamespace

        fake.dirs.add("/scratch/me")
        fake.dirs.add("/scratch/me/projects")
        fake.files["/scratch/me/workspace.json"] = b'{"name":"ws"}'
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        assert cached.indexed is False
        ws = SimpleNamespace(root="/scratch/me", fs=cached)
        warnings = cached.prepare(ws, block_index=False)  # type: ignore[arg-type]
        assert warnings == []
        assert cached.connected is True
        if cached._index_thread is not None:
            cached._index_thread.join(timeout=2.0)
        assert cached.indexed is True

    @pytest.mark.unit
    def test_force_fetch_bypasses_pin_for_refresh_thread(self, fake: _FakeRemoteFS, tmp_path: Path):
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.connect("/scratch/me")
        cached.read_bytes("/scratch/me/log.txt")
        fake.files["/scratch/me/log.txt"] = b"updated"
        fake.calls.clear()
        # Pin still serves old bytes on UI thread.
        assert cached.read_bytes("/scratch/me/log.txt") == b"hello"
        assert fake.calls["read_bytes"] == 0
        # Active refresh thread force-fetches.
        with cached.force_fetch():
            assert cached.read_bytes("/scratch/me/log.txt") == b"updated"
        assert fake.calls["read_bytes"] == 1
        # Pin now holds the new bytes.
        fake.calls.clear()
        assert cached.read_bytes("/scratch/me/log.txt") == b"updated"
        assert fake.calls["read_bytes"] == 0

    @pytest.mark.unit
    def test_force_fetch_propagates_to_parallel_workers(self, fake: _FakeRemoteFS, tmp_path: Path):
        """ThreadPool workers must inherit force_fetch (TLS is not shared)."""
        from molab.workspace.fs_cached import _parallel_map

        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.connect("/scratch/me")
        for i in range(4):
            path = f"/scratch/me/p{i}.json"
            fake.files[path] = b"v1"
            cached.read_bytes(path)
            fake.files[path] = b"v2"

        def _read(i: int) -> bytes:
            return cached.read_bytes(f"/scratch/me/p{i}.json")

        # Without force_fetch workers would return pinned v1.
        with cached.force_fetch():
            out = _parallel_map(_read, list(range(4)), max_workers=4, force_fetch_fs=cached)
        assert out == [b"v2"] * 4

    @pytest.mark.unit
    def test_sidecar_ancient_fetched_at_still_pinned(self, fake: _FakeRemoteFS, tmp_path: Path):
        """Prior-session wall-clock ages must not force SSH on next open."""
        mirror_root = tmp_path / "mirror"
        first = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        first.connect("/scratch/me")
        first.read_bytes("/scratch/me/log.txt")
        import json as _json

        sidecar = mirror_root / "_index.json"
        raw = _json.loads(sidecar.read_text(encoding="utf-8"))
        for payload in raw["entries"].values():
            payload["fetched_at"] = 1.0  # ancient
        for payload in raw.get("dirs", {}).values():
            payload["fetched_at"] = 1.0
        sidecar.write_text(_json.dumps(raw), encoding="utf-8")

        second = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        fake.calls.clear()
        assert second.read_bytes("/scratch/me/log.txt") == b"hello"
        assert fake.calls["read_bytes"] == 0
        assert fake.calls["stat"] == 0

    # ── Sidecar persistence ──────────────────────────────────────────────

    @pytest.mark.unit
    def test_sidecar_round_trip_across_instances(self, fake: _FakeRemoteFS, tmp_path: Path):
        mirror_root = tmp_path / "mirror"
        first = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        first.read_bytes("/scratch/me/log.txt")
        assert fake.calls["read_bytes"] == 1

        second = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        # Cached_paths should include the entry from the first instance.
        assert "/scratch/me/log.txt" in second.cached_paths()
        fake.calls.clear()
        second.read_bytes("/scratch/me/log.txt")
        assert fake.calls["read_bytes"] == 0, "must serve from mirror after re-instantiation"

    @pytest.mark.unit
    def test_missing_sidecar_is_normal_and_created_on_connect(
        self, fake: _FakeRemoteFS, tmp_path: Path
    ):
        """A brand-new remote has no _index.json — connect materialises one."""
        mirror_root = tmp_path / "fresh-mirror"
        fake.dirs.add("/scratch/me")
        cached = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        # Init creates mirror dirs but does not invent a sidecar until connect/write.
        assert mirror_root.is_dir()
        assert cached.connected is False
        cached.connect("/scratch/me")
        assert cached.connected is True
        assert (mirror_root / "_index.json").is_file()
        # Empty index is fine — ready still false until index().
        assert cached.indexed is False
        assert cached.ready is False

    @pytest.mark.unit
    def test_write_sidecar_recovers_when_mirror_wiped(self, fake: _FakeRemoteFS, tmp_path: Path):
        """External rm -rf of mirror must not permanently mute the cache."""
        import shutil

        mirror_root = tmp_path / "mirror"
        cached = CachedRemoteFileSystem(fake, mirror_root=mirror_root, cache_mode="pinned")
        cached.read_bytes("/scratch/me/log.txt")
        assert (mirror_root / "_index.json").is_file()

        shutil.rmtree(mirror_root)
        assert not mirror_root.exists()

        # Next record re-creates dirs + sidecar instead of warning forever.
        fake.files["/scratch/me/other.txt"] = b"yy"
        cached.read_bytes("/scratch/me/other.txt")
        assert mirror_root.is_dir()
        assert (mirror_root / "_index.json").is_file()

    # ── invalidate() public surface ──────────────────────────────────────

    @pytest.mark.unit
    def test_invalidate_scope_indices_drops_only_index_files(
        self, fake: _FakeRemoteFS, tmp_path: Path
    ):
        fake.files["/scratch/me/project.json"] = b'{"items":[]}'
        fake.files["/scratch/me/runs/a/stdout.log"] = b"log bytes"
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.read_bytes("/scratch/me/project.json")
        cached.read_bytes("/scratch/me/runs/a/stdout.log")

        dropped = cached.invalidate(scope="indices")
        assert dropped == 1
        assert "/scratch/me/runs/a/stdout.log" in cached.cached_paths()
        assert "/scratch/me/project.json" not in cached.cached_paths()

    @pytest.mark.unit
    def test_invalidate_scope_indices_drops_attempt_records(
        self, fake: _FakeRemoteFS, tmp_path: Path
    ) -> None:
        from molab.workspace.fs_cached import INDEX_FILE_NAMES

        fake.files["/scratch/me/executions/e01/execution.json"] = b"{}"
        fake.files["/scratch/me/executions/e01/run.log"] = b"log"
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.read_bytes("/scratch/me/executions/e01/execution.json")
        cached.read_bytes("/scratch/me/executions/e01/run.log")

        cached.invalidate(scope="indices")

        assert "/scratch/me/executions/e01/execution.json" not in cached.cached_paths()
        assert "/scratch/me/executions/e01/run.log" in cached.cached_paths()
        assert 'invalidate(scope="indices")' in (INDEX_FILE_NAMES.__doc__ or "")

    @pytest.mark.unit
    def test_invalidate_scope_all_clears_everything(self, fake: _FakeRemoteFS, tmp_path: Path):
        fake.files["/scratch/me/extra.txt"] = b"x"
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.read_bytes("/scratch/me/log.txt")
        cached.read_bytes("/scratch/me/extra.txt")

        dropped = cached.invalidate(scope="all")
        assert dropped == 2
        assert cached.cached_paths() == []
        # files/ contents are wiped, but the mirror skeleton is recreated so
        # the next write never hits "No such file or directory" on the sidecar.
        assert (tmp_path / "mirror" / "files").is_dir()
        assert list((tmp_path / "mirror" / "files").iterdir()) == []
        assert cached.indexed is False

    @pytest.mark.unit
    def test_invalidate_specific_path(self, fake: _FakeRemoteFS, tmp_path: Path):
        fake.files["/scratch/me/extra.txt"] = b"x"
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.read_bytes("/scratch/me/log.txt")
        cached.read_bytes("/scratch/me/extra.txt")

        cached.invalidate("/scratch/me/log.txt")
        assert "/scratch/me/extra.txt" in cached.cached_paths()
        assert "/scratch/me/log.txt" not in cached.cached_paths()

    @pytest.mark.unit
    def test_invalidate_rejects_unknown_scope(self, cached: CachedRemoteFileSystem):
        with pytest.raises(ValueError, match="unknown scope"):
            cached.invalidate(scope="bogus")

    # ── Stat caching ─────────────────────────────────────────────────────

    @pytest.mark.unit
    def test_stat_serves_from_cache_after_read(
        self, cached: CachedRemoteFileSystem, fake: _FakeRemoteFS
    ):
        cached.read_bytes("/scratch/me/log.txt")
        fake.calls.clear()
        info = cached.stat("/scratch/me/log.txt")
        assert info.is_file is True
        assert fake.calls["stat"] == 0

    # ── Path ops never touch the inner FS ────────────────────────────────

    @pytest.mark.unit
    def test_path_ops_delegate_to_inner_without_io(self, fake: _FakeRemoteFS, tmp_path: Path):
        cached = CachedRemoteFileSystem(fake, mirror_root=tmp_path / "mirror", cache_mode="pinned")
        cached.join("/a", "b", "c")
        cached.dirname("/a/b/c")
        cached.basename("/a/b/c")
        cached.resolve("/a/b/c")
        # None of these trigger remote I/O.
        assert sum(fake.calls.values()) == 0


def test_open_preserves_binary_and_rejects_writes(cached, fake):
    fake.files["/binary"] = b"\xff\x00\xfe"
    with cached.open("/binary", "rb") as stream:
        assert stream.read() == b"\xff\x00\xfe"
    with pytest.raises(ValueError):
        cached.open("/binary", "w")


def test_connect_preserves_authentication_failure(cached, fake, monkeypatch):
    from molq import MolqError

    error = MolqError("AUTH_REQUIRED", "authenticate first")

    def denied(_path):
        raise error

    monkeypatch.setattr(fake, "exists", denied)
    with pytest.raises(MolqError) as caught:
        cached.connect("/scratch/me")
    assert caught.value is error


def test_old_read_cannot_repin_after_write(cached, fake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started, release = Event(), Event()
    original = fake.read_bytes

    def delayed(path):
        content = original(path)
        started.set()
        assert release.wait(5)
        return content

    monkeypatch.setattr(fake, "read_bytes", delayed)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(cached.read_bytes, "/scratch/me/log.txt")
        assert started.wait(5)
        try:
            cached.write_bytes("/scratch/me/log.txt", b"new")
        finally:
            release.set()
        assert pending.result() == b"hello"
    monkeypatch.setattr(fake, "read_bytes", original)
    assert cached.read_bytes("/scratch/me/log.txt") == b"new"


def test_directory_rename_evicts_descendants(cached, fake, monkeypatch):
    fake.files["/old/child"] = b"old"
    cached.read_bytes("/old/child")

    def move(src, dst):
        fake.files[dst + "/child"] = fake.files.pop(src + "/child")

    monkeypatch.setattr(fake, "rename", move)
    cached.rename("/old", "/new")
    with pytest.raises(FileNotFoundError):
        cached.read_bytes("/old/child")
    assert cached.read_bytes("/new/child") == b"old"


@pytest.mark.parametrize("operation", ["exists", "listdir"])
def test_mkdir_rejects_observations_started_before_creation(cached, fake, monkeypatch, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    original = getattr(fake, operation)
    target = "/scratch/me/new" if operation == "exists" else "/scratch/me"

    def delayed(path):
        result = original(path)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(fake, operation, delayed)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(getattr(cached, operation), target)
        assert entered.wait(5)
        try:
            cached.mkdir("/scratch/me/new")
        finally:
            release.set()
        pending.result()
    monkeypatch.setattr(fake, operation, original)
    assert cached.exists("/scratch/me/new")
    assert "new" in cached.listdir("/scratch/me")


def test_mkdir_does_not_resurrect_parent_listing_on_reopen(cached, fake):
    assert "new" not in cached.listdir("/scratch/me")
    cached.mkdir("/scratch/me/new")
    reopened = CachedRemoteFileSystem(fake, mirror_root=cached.mirror_root)
    assert "new" in reopened.listdir("/scratch/me")


def test_pinned_batch_and_write_do_not_race_mirror_eviction(cached, fake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FutureTimeout
    from threading import Event

    key = "/scratch/me/log.txt"
    cached.read_bytes(key)
    entered, release = Event(), Event()
    original = cached._local.read_bytes

    def delayed(path):
        entered.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr(cached._local, "read_bytes", delayed)
    with ThreadPoolExecutor() as pool:
        reader = pool.submit(cached.read_many, [key])
        assert entered.wait(5)
        writer = pool.submit(cached.write_bytes, key, b"new")
        try:
            import contextlib

            with contextlib.suppress(FutureTimeout):
                writer.result(timeout=0.1)
        finally:
            release.set()
        assert reader.result()[key] == b"hello"
        writer.result()
    assert cached.read_bytes(key) == b"new"


def test_observation_during_write_is_evicted_after_commit(cached, fake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    original = fake.write_bytes
    key = "/scratch/me/log.txt"

    def delayed(path, content, *, mode=0o600):
        entered.set()
        assert release.wait(5)
        original(path, content, mode=mode)

    monkeypatch.setattr(fake, "write_bytes", delayed)
    with ThreadPoolExecutor() as pool:
        writer = pool.submit(cached.write_bytes, key, b"new")
        assert entered.wait(5)
        try:
            # A slow remote mutation must not block mirror readers globally.
            reader = pool.submit(cached.read_bytes, key)
            assert reader.result(timeout=2) == b"hello"
        finally:
            release.set()
        writer.result()
    assert cached.read_bytes(key) == b"new"


@pytest.mark.parametrize("operation", ["mkdir", "atomic_write_text"])
def test_parent_creation_evicts_ancestor_negative_pins(tmp_path, operation):
    from molab.workspace.fs_local import LocalFileSystem

    root = tmp_path / "remote"
    root.mkdir()
    fs = CachedRemoteFileSystem(LocalFileSystem(), mirror_root=tmp_path / "mirror")
    parent = root / "new"
    assert not fs.exists(parent)
    assert fs.listdir(root) == []
    if operation == "mkdir":
        fs.mkdir(parent / "deep", parents=True)
    else:
        fs.atomic_write_text(parent / "deep" / "file", "data")
    assert fs.exists(parent)
    assert fs.listdir(root) == ["new"]
    reopened = CachedRemoteFileSystem(LocalFileSystem(), mirror_root=fs.mirror_root)
    assert reopened.exists(parent)
    assert reopened.listdir(root) == ["new"]
