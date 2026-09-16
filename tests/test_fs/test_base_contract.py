"""The ``scandir`` / ``read_range`` Protocol contract, run against every backend.

These are the semantics the walkers and the windowed readers rely on, so they
are asserted against each implementation rather than trusted per class: a fake
that disagrees about a broken symlink or an offset past EOF would make a test
elsewhere pass for the wrong reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.fs import DirEntry, FileSystem, LocalFileSystem, bulk
from tests.support.fs_fallbacks import default_read_range, default_scandir


class _FallbackFS:
    """A FileSystem whose bulk ops come from the generic test fallbacks."""

    def __init__(self) -> None:
        self._real = LocalFileSystem()

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def scandir(self, path, *, with_stat: bool = True) -> list[DirEntry]:
        return default_scandir(self, path, with_stat=with_stat)

    def read_range(self, path, offset: int, length: int) -> bytes:
        return default_read_range(self, path, offset, length)


@pytest.fixture(params=["local", "fallback"])
def fs(request: pytest.FixtureRequest):
    return LocalFileSystem() if request.param == "local" else _FallbackFS()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "sub").mkdir()
    (tmp_path / "file.txt").write_text("abcdefghij")
    (tmp_path / "sub" / "nested.txt").write_text("x")
    return tmp_path


class TestScandir:
    def test_lists_children_with_types(self, fs: FileSystem, tree: Path) -> None:
        by_name = {e.name: e for e in fs.scandir(tree)}
        assert set(by_name) == {"sub", "file.txt"}
        assert by_name["sub"].is_dir and not by_name["sub"].is_file
        assert by_name["file.txt"].is_file and not by_name["file.txt"].is_dir

    def test_reports_size_and_mtime_with_stat(self, fs: FileSystem, tree: Path) -> None:
        entry = next(e for e in fs.scandir(tree) if e.name == "file.txt")
        assert entry.size == 10
        assert entry.mtime > 0

    def test_never_includes_dot_entries(self, fs: FileSystem, tree: Path) -> None:
        assert {".", ".."}.isdisjoint({e.name for e in fs.scandir(tree)})

    def test_missing_path_raises_file_not_found(self, fs: FileSystem, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            fs.scandir(tmp_path / "nope")

    def test_file_path_raises_not_a_directory(self, fs: FileSystem, tree: Path) -> None:
        with pytest.raises(NotADirectoryError):
            fs.scandir(tree / "file.txt")

    def test_empty_directory_is_empty_list(self, fs: FileSystem, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        assert fs.scandir(tmp_path / "empty") == []


class TestScandirSymlinks:
    def test_symlink_to_dir_reports_dir_and_symlink(self, tree: Path) -> None:
        (tree / "link").symlink_to(tree / "sub")
        entry = next(e for e in LocalFileSystem().scandir(tree) if e.name == "link")
        assert entry.is_dir and entry.is_symlink and not entry.is_file

    def test_broken_symlink_is_neither_dir_nor_file(self, tree: Path) -> None:
        (tree / "broken").symlink_to(tree / "gone")
        entry = next(e for e in LocalFileSystem().scandir(tree) if e.name == "broken")
        assert not entry.is_dir and not entry.is_file and entry.is_symlink


class TestReadRange:
    def test_returns_requested_slice(self, fs: FileSystem, tree: Path) -> None:
        assert fs.read_range(tree / "file.txt", 2, 3) == b"cde"

    def test_short_read_at_eof(self, fs: FileSystem, tree: Path) -> None:
        assert fs.read_range(tree / "file.txt", 8, 100) == b"ij"

    def test_offset_past_eof_is_empty(self, fs: FileSystem, tree: Path) -> None:
        assert fs.read_range(tree / "file.txt", 50, 10) == b""

    def test_zero_length_is_empty(self, fs: FileSystem, tree: Path) -> None:
        assert fs.read_range(tree / "file.txt", 0, 0) == b""

    def test_negative_offset_raises_value_error(self, fs: FileSystem, tree: Path) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            fs.read_range(tree / "file.txt", -1, 5)

    def test_negative_length_raises_value_error(self, fs: FileSystem, tree: Path) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            fs.read_range(tree / "file.txt", 0, -5)

    def test_missing_file_raises_file_not_found(self, fs: FileSystem, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            fs.read_range(tmp_path / "nope", 0, 5)


class TestBulk:
    def test_no_batched_method_is_a_noop(self) -> None:
        with bulk(LocalFileSystem()):
            pass  # Must not raise.

    def test_enters_batched_when_available(self) -> None:
        import contextlib

        entered: list[str] = []

        class _Batching(_FallbackFS):
            @contextlib.contextmanager
            def batched(self):
                entered.append("in")
                yield
                entered.append("out")

        with bulk(_Batching()):
            assert entered == ["in"]
        assert entered == ["in", "out"]


class TestProtocolConformance:
    def test_local_filesystem_satisfies_protocol(self) -> None:
        assert isinstance(LocalFileSystem(), FileSystem)

    def test_bulk_members_are_declared_on_the_protocol(self) -> None:
        # Guards against the members being added to an implementation but not
        # the Protocol, which would let a third-party backend omit them.
        assert hasattr(FileSystem, "scandir")
        assert hasattr(FileSystem, "read_range")
