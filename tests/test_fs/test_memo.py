"""``StatMemo`` — stat-validated read memo (``molab.fs.memo``).

Locks the contract the workspace read paths rely on: a repeat read of an
unchanged file is exactly one ``stat`` and zero opens; a changed file is
re-loaded; absence is never memoized; a failing loader stores nothing.
"""

from __future__ import annotations

import os
import time

import pytest

from molab.fs import LocalFileSystem, StatMemo
from tests.support.counting_fs import CountingFileSystem


def _write(path: str, text: str, *, mtime: float | None = None) -> None:
    with open(path, "w", encoding="utf-8") as fh:  # noqa: PTH123
        fh.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.fixture
def fs() -> CountingFileSystem:
    return CountingFileSystem(LocalFileSystem())


class TestStatMemo:
    def test_hit_is_one_stat_and_zero_opens(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one")
        memo = StatMemo(fs)
        assert memo.get(p, fs.read_text) == "one"
        fs.reset()
        assert memo.get(p, fs.read_text) == "one"
        assert fs.calls["stat"] == 1
        assert fs.opens() == 0

    def test_changed_file_is_reloaded(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one", mtime=1_000_000.0)
        memo = StatMemo(fs)
        assert memo.get(p, fs.read_text) == "one"
        _write(p, "two-longer", mtime=1_000_001.0)
        assert memo.get(p, fs.read_text) == "two-longer"

    def test_same_size_different_mtime_is_reloaded(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "aaa", mtime=1_000_000.0)
        memo = StatMemo(fs)
        assert memo.get(p, fs.read_text) == "aaa"
        _write(p, "bbb", mtime=1_000_005.0)
        assert memo.get(p, fs.read_text) == "bbb"

    def test_absence_raises_and_is_never_memoized(self, tmp_path, fs) -> None:
        p = str(tmp_path / "missing.txt")
        memo = StatMemo(fs)
        with pytest.raises(FileNotFoundError):
            memo.get(p, fs.read_text)
        assert memo.get_or_none(p, fs.read_text) is None
        assert len(memo) == 0
        _write(p, "now here")
        assert memo.get_or_none(p, fs.read_text) == "now here"

    def test_not_a_directory_maps_to_none(self, tmp_path, fs) -> None:
        f = str(tmp_path / "file")
        _write(f, "x")
        memo = StatMemo(fs)
        assert memo.get_or_none(f + "/child.json", fs.read_text) is None

    def test_failing_loader_stores_nothing(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one")
        memo = StatMemo(fs)

        def boom(_path: str) -> str:
            raise ValueError("bad content")

        with pytest.raises(ValueError, match="bad content"):
            memo.get(p, boom)
        assert len(memo) == 0

    def test_fetch_reports_hit_and_is_fresh(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one", mtime=1_000_000.0)
        memo = StatMemo(fs)
        assert memo.is_fresh(p) is False
        _value, hit = memo.fetch(p, fs.read_text)
        assert hit is False
        assert memo.is_fresh(p) is True
        _value, hit = memo.fetch(p, fs.read_text)
        assert hit is True
        _write(p, "two", mtime=1_000_001.0)
        assert memo.is_fresh(p) is False

    def test_slots_are_independent_and_invalidated_together(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one")
        memo = StatMemo(fs)
        assert memo.get(p, fs.read_text) == "one"
        assert memo.get(p, lambda q: fs.read_text(q).upper(), slot="upper") == "ONE"
        assert len(memo) == 2
        memo.invalidate(p)
        assert len(memo) == 0

    def test_invalidate_none_clears_everything(self, tmp_path, fs) -> None:
        a, b = str(tmp_path / "a"), str(tmp_path / "b")
        _write(a, "a")
        _write(b, "b")
        memo = StatMemo(fs)
        memo.get(a, fs.read_text)
        memo.get(b, fs.read_text)
        memo.invalidate()
        assert len(memo) == 0

    def test_put_seeds_a_hit_without_a_read(self, tmp_path, fs) -> None:
        p = str(tmp_path / "a.txt")
        _write(p, "one")
        st = fs.stat(p)
        memo = StatMemo(fs)
        memo.put(p, "seeded", st)
        fs.reset()
        assert memo.get(p, fs.read_text) == "seeded"
        assert fs.opens() == 0
        assert fs.calls["stat"] == 1

    def test_stat_before_load_ordering_never_pins_stale_content(self, tmp_path, fs) -> None:
        # A loader that rewrites the file *while loading* (simulating a writer
        # racing the read) must not leave the memo serving the pre-write value.
        p = str(tmp_path / "a.txt")
        _write(p, "old", mtime=1_000_000.0)
        memo = StatMemo(fs)

        def racy_load(path: str) -> str:
            content = fs.read_text(path)
            _write(path, "new!", mtime=1_000_010.0)
            return content

        assert memo.get(p, racy_load) == "old"
        # Next read: the stored key is the pre-write stat, so it misses and reloads.
        assert memo.get(p, fs.read_text) == "new!"

    def test_accepts_pathlike(self, tmp_path, fs) -> None:
        p = tmp_path / "a.txt"
        _write(str(p), "one")
        memo = StatMemo(fs)
        assert memo.get(p, fs.read_text) == "one"
        assert memo.is_fresh(p)
        time.sleep(0)  # keep the import used on platforms with coarse clocks
