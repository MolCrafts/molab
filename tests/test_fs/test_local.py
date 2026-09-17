"""``LocalFileSystem`` syscall budgets and type reporting.

The counts matter, not just the answers: every ``stat`` is a round-trip on the
network mounts molab runs on, so "one stat per stat" is a contract, not an
implementation detail.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from molab.fs import LocalFileSystem


class _StatCounter:
    """Counts ``os.stat`` / ``os.lstat`` / ``Path.is_dir`` / ``Path.is_file``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.stat = 0
        self.lstat = 0
        self.path_type_checks = 0
        real_stat, real_lstat = os.stat, os.lstat
        real_is_dir, real_is_file = Path.is_dir, Path.is_file

        def counted_stat(*a, **kw):  # noqa: ANN002, ANN003
            self.stat += 1
            return real_stat(*a, **kw)

        def counted_lstat(*a, **kw):  # noqa: ANN002, ANN003
            self.lstat += 1
            return real_lstat(*a, **kw)

        def counted_is_dir(p, *a, **kw):  # noqa: ANN002, ANN003
            self.path_type_checks += 1
            return real_is_dir(p, *a, **kw)

        def counted_is_file(p, *a, **kw):  # noqa: ANN002, ANN003
            self.path_type_checks += 1
            return real_is_file(p, *a, **kw)

        monkeypatch.setattr(os, "stat", counted_stat)
        monkeypatch.setattr(os, "lstat", counted_lstat)
        monkeypatch.setattr(Path, "is_dir", counted_is_dir)
        monkeypatch.setattr(Path, "is_file", counted_is_file)


class TestStatSyscallBudget:
    def test_stat_costs_exactly_one_syscall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "f.txt"
        target.write_text("x")
        counter = _StatCounter(monkeypatch)

        result = LocalFileSystem().stat(target)

        assert (counter.stat, counter.path_type_checks) == (1, 0), (
            "stat must not re-probe the type with is_dir/is_file — that is two "
            "extra round-trips on a network mount"
        )
        assert result.is_file and not result.is_dir

    def test_lstat_costs_exactly_one_syscall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "f.txt"
        target.write_text("x")
        counter = _StatCounter(monkeypatch)

        LocalFileSystem().lstat(target)

        assert (counter.lstat, counter.path_type_checks) == (1, 0)

    def test_stat_reports_directories(self, tmp_path: Path) -> None:
        result = LocalFileSystem().stat(tmp_path)
        assert result.is_dir and not result.is_file


class TestLstatSymlinkSemantics:
    def test_lstat_describes_the_link_not_its_target(self, tmp_path: Path) -> None:
        target = tmp_path / "real.txt"
        target.write_text("hello")
        link = tmp_path / "link"
        link.symlink_to(target)

        fs = LocalFileSystem()
        assert fs.stat(link).is_file, "stat follows the link"
        # lstat describes the symlink itself, which is neither a dir nor a
        # regular file; the old body called Path.is_file() and followed it.
        assert not fs.lstat(link).is_file
        assert not fs.lstat(link).is_dir


class TestScandirWithStat:
    def test_with_stat_false_skips_entry_stat_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        seen: list[str] = []
        real = os.DirEntry.stat

        def counted(self, *a, **kw):  # noqa: ANN002, ANN003
            seen.append(self.name)
            return real(self, *a, **kw)

        monkeypatch.setattr(os.DirEntry, "stat", counted, raising=False)

        entries = LocalFileSystem().scandir(tmp_path, with_stat=False)

        assert len(entries) == 5
        assert seen == [], "with_stat=False must not stat each entry"
        assert all(e.size == 0 and e.mtime == 0.0 for e in entries)
        assert all(e.is_file for e in entries), "type must stay exact without stat"

    def test_with_stat_true_fills_size_and_mtime(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("12345")
        entry = LocalFileSystem().scandir(tmp_path)[0]
        assert entry.size == 5 and entry.mtime > 0


class TestListdir:
    def test_returns_plain_names(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "d").mkdir()
        assert sorted(LocalFileSystem().listdir(tmp_path)) == ["a.txt", "d"]


class TestReadRangeMemory:
    def test_reads_only_the_window_of_a_large_file(self, tmp_path: Path) -> None:
        big = tmp_path / "big.bin"
        with big.open("wb") as fh:
            fh.truncate(200 * 1024 * 1024)  # Sparse: 200 MB that costs no disk.

        chunk = LocalFileSystem().read_range(big, 100 * 1024 * 1024, 64)

        assert len(chunk) == 64, "a range read must not scale with the file"
