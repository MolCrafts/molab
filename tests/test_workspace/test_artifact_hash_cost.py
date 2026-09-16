"""Registering an artifact must read its bytes once, not twice.

``ArtifactAccessor.save`` copies the file and then addresses it. Done as two
passes, registering a 10 GB trajectory reads 20 GB — and the second pass buys
nothing, because the copy already had the bytes in hand.
"""

from __future__ import annotations

import builtins
import time
from pathlib import Path

import pytest

from molexp.ids import clear_hash_memo, compute_content_hash, hash_copy
from molexp.workspace import Workspace


@pytest.fixture(autouse=True)
def _clear_memo() -> None:
    clear_hash_memo()
    yield
    clear_hash_memo()


@pytest.fixture
def ctx(tmp_path: Path):
    """A live RunContext — ``ctx.artifact`` is the accessor under test."""
    ws = Workspace(tmp_path / "ws")
    run = ws.add_project("p").add_experiment("e").add_run(params={"a": 1})
    with run.start() as active:
        yield active


class _ReadCounter:
    """Counts how many times each path is opened for reading."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, watch: str) -> None:
        self.opens = 0
        self.watch = watch
        real_open = builtins.open

        def counted(file, mode="r", *a, **kw):  # noqa: ANN002, ANN003
            if "r" in str(mode) and self.watch in str(file):
                self.opens += 1
            return real_open(file, mode, *a, **kw)

        monkeypatch.setattr(builtins, "open", counted)


class TestArtifactSaveReadPasses:
    def test_path_artifact_is_read_once(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "traj.bin"
        source.write_bytes(b"molecule" * 100_000)
        counter = _ReadCounter(monkeypatch, watch="traj.bin")

        asset = ctx.artifact.save("traj.bin", source)

        assert counter.opens == 1, "the copy and the hash must share one read pass over the source"
        assert asset.content_hash == compute_content_hash(source)

    def test_bytes_artifact_never_reads_the_file_back(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        counter = _ReadCounter(monkeypatch, watch="blob.bin")

        asset = ctx.artifact.save("blob.bin", b"payload" * 1000)

        assert counter.opens == 0, "bytes in hand need no read at all"
        assert asset.content_hash.startswith("sha256:")

    def test_recorded_hash_matches_the_written_file(self, ctx, tmp_path: Path) -> None:
        source = tmp_path / "data.bin"
        source.write_bytes(bytes(range(256)) * 500)

        asset = ctx.artifact.save("data.bin", source)
        written = Path(str(ctx.run.resolve())) / "artifacts" / "data.bin"

        assert asset.content_hash == compute_content_hash(written)
        assert written.read_bytes() == source.read_bytes()

    def test_json_artifact_hash_matches_its_file(self, ctx) -> None:
        asset = ctx.artifact.save("meta.json", {"b": 2, "a": 1})
        written = Path(str(ctx.run.resolve())) / "artifacts" / "meta.json"
        assert asset.content_hash == compute_content_hash(written)

    def test_text_artifact_hash_matches_its_file(self, ctx) -> None:
        asset = ctx.artifact.save("note.txt", "hello world")
        written = Path(str(ctx.run.resolve())) / "artifacts" / "note.txt"
        assert asset.content_hash == compute_content_hash(written)


class TestHashCopy:
    def test_copies_bytes_and_returns_the_digest(self, tmp_path: Path) -> None:
        src = tmp_path / "a.bin"
        src.write_bytes(b"x" * 2_500_000)
        dst = tmp_path / "out" / "b.bin"

        digest = hash_copy(src, dst)

        assert dst.read_bytes() == src.read_bytes()
        assert digest == compute_content_hash(src)

    def test_preserves_mtime(self, tmp_path: Path) -> None:
        src = tmp_path / "a.bin"
        src.write_bytes(b"data")
        import os

        os.utime(src, (1_600_000_000, 1_600_000_000))
        dst = tmp_path / "b.bin"

        hash_copy(src, dst)

        assert int(dst.stat().st_mtime) == 1_600_000_000


class TestLargeFilePerformance:
    def test_sparse_gigabyte_artifact_registers_in_one_pass(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "huge.bin"
        with source.open("wb") as fh:
            fh.truncate(1024 * 1024 * 1024)  # 1 GiB sparse — no disk cost.
        counter = _ReadCounter(monkeypatch, watch="huge.bin")

        started = time.monotonic()
        asset = ctx.artifact.save("huge.bin", source)
        elapsed = time.monotonic() - started

        assert counter.opens == 1
        assert asset.size == 1024 * 1024 * 1024
        assert elapsed < 120, f"one streaming pass should not take {elapsed:.0f}s"


class TestHashMemo:
    def test_repeated_hash_of_an_unchanged_file_is_served_from_memo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "f.bin"
        target.write_bytes(b"abc" * 1000)
        compute_content_hash(target)
        counter = _ReadCounter(monkeypatch, watch="f.bin")

        compute_content_hash(target)

        assert counter.opens == 0, "an unchanged file must not be re-read"

    def test_changed_file_is_rehashed(self, tmp_path: Path) -> None:
        target = tmp_path / "f.bin"
        target.write_bytes(b"one")
        first = compute_content_hash(target)
        time.sleep(0.01)
        target.write_bytes(b"two")

        assert compute_content_hash(target) != first

    def test_directory_hashes_are_not_memoized(self, tmp_path: Path) -> None:
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "a.txt").write_text("one")
        first = compute_content_hash(tree)
        (tree / "b.txt").write_text("two")

        assert compute_content_hash(tree) != first, (
            "a directory's digest depends on a whole subtree, which one stat "
            "cannot validate — so it must never be served from a memo"
        )
