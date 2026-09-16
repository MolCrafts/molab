"""Windowed text reads: bounded memory, correct cursors, safe line alignment."""

from __future__ import annotations

import tracemalloc
from pathlib import Path

import pytest

from molexp.fs import LocalFileSystem
from molexp.fs.window import (
    DEFAULT_TEXT_WINDOW_BYTES,
    MAX_TEXT_WINDOW_BYTES,
    read_text_window,
)


@pytest.fixture
def fs() -> LocalFileSystem:
    return LocalFileSystem()


@pytest.fixture
def log(tmp_path: Path) -> Path:
    target = tmp_path / "run.log"
    target.write_text("".join(f"line{i}\n" for i in range(10)))
    return target


class TestTailMode:
    def test_returns_the_end_of_the_file(self, fs: LocalFileSystem, log: Path) -> None:
        window = read_text_window(fs, log, max_bytes=20)
        assert window.text.endswith("line9\n")
        assert window.truncated

    def test_whole_file_when_it_fits(self, fs: LocalFileSystem, log: Path) -> None:
        window = read_text_window(fs, log, max_bytes=MAX_TEXT_WINDOW_BYTES)
        assert window.text == log.read_text()
        assert not window.truncated
        assert (window.start, window.end) == (0, window.total_bytes)

    def test_drops_a_partial_leading_line(self, fs: LocalFileSystem, log: Path) -> None:
        window = read_text_window(fs, log, max_bytes=14)
        assert not window.text.startswith("ne"), "a split line must not be shown"
        assert window.text.startswith("line")


class TestHeadMode:
    def test_returns_the_start_of_the_file(self, fs: LocalFileSystem, log: Path) -> None:
        window = read_text_window(fs, log, max_bytes=20, mode="head")
        assert window.text.startswith("line0\n")
        assert window.start == 0
        assert window.truncated

    def test_drops_a_partial_trailing_line(self, fs: LocalFileSystem, log: Path) -> None:
        # 14 bytes spans "line0\nline1\nli" — the dangling "li" must go.
        window = read_text_window(fs, log, max_bytes=14, mode="head")
        assert window.text == "line0\nline1\n"
        assert window.end == 12


class TestIncrementalFollow:
    def test_since_offset_returns_only_new_bytes(self, fs: LocalFileSystem, log: Path) -> None:
        first = read_text_window(fs, log, max_bytes=MAX_TEXT_WINDOW_BYTES)
        with log.open("a") as fh:
            fh.write("line10\n")

        second = read_text_window(fs, log, since_offset=first.end)

        assert second.text == "line10\n"
        assert second.start == first.end

    def test_cursor_on_a_boundary_keeps_its_first_line(
        self, fs: LocalFileSystem, log: Path
    ) -> None:
        # Regression: forward line-alignment used to fire on a caller-supplied
        # cursor too, silently swallowing one whole line per poll.
        window = read_text_window(fs, log, since_offset=12)
        assert window.text.startswith("line2\n")

    def test_no_new_data_returns_empty(self, fs: LocalFileSystem, log: Path) -> None:
        size = log.stat().st_size
        window = read_text_window(fs, log, since_offset=size)
        assert window.text == ""
        assert window.end == size

    def test_follow_loop_reconstructs_the_whole_file(self, fs: LocalFileSystem, log: Path) -> None:
        cursor, seen = 0, ""
        for _ in range(50):
            window = read_text_window(fs, log, since_offset=cursor, max_bytes=8)
            if window.end == cursor:
                break
            seen += window.text
            cursor = window.end
        assert seen == log.read_text()

    def test_offset_past_eof_restarts_and_flags_rewound(
        self, fs: LocalFileSystem, log: Path
    ) -> None:
        window = read_text_window(fs, log, since_offset=10**9)
        assert window.rewound
        assert window.start == 0
        assert window.text == log.read_text()


class TestErrors:
    def test_directory_raises(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        with pytest.raises(IsADirectoryError):
            read_text_window(fs, tmp_path)

    def test_missing_file_raises(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_text_window(fs, tmp_path / "nope.log")

    def test_non_positive_max_bytes_raises(self, fs: LocalFileSystem, log: Path) -> None:
        with pytest.raises(ValueError, match="max_bytes"):
            read_text_window(fs, log, max_bytes=0)

    def test_negative_since_offset_raises(self, fs: LocalFileSystem, log: Path) -> None:
        with pytest.raises(ValueError, match="since_offset"):
            read_text_window(fs, log, since_offset=-1)


class TestBoundedCost:
    def test_huge_file_reads_only_the_window(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        big = tmp_path / "huge.log"
        with big.open("wb") as fh:
            fh.truncate(100 * 1024 * 1024)  # Sparse 100 MB.
            fh.seek(100 * 1024 * 1024 - 12)
            fh.write(b"last line\n")

        reads: list[int] = []
        real_range = LocalFileSystem.read_range

        class _Recording(LocalFileSystem):
            @staticmethod
            def read_range(path, offset, length):  # noqa: ANN205
                reads.append(length)
                return real_range(path, offset, length)

        window = read_text_window(_Recording(), big, max_bytes=4096)

        assert len(reads) == 1, "exactly one range read per window"
        assert reads[0] <= 4096
        assert window.total_bytes == 100 * 1024 * 1024
        assert window.truncated

    def test_peak_memory_stays_near_the_cap(self, fs: LocalFileSystem, tmp_path: Path) -> None:
        big = tmp_path / "huge.log"
        with big.open("wb") as fh:
            fh.write(b"x" * (8 * 1024 * 1024))

        cap = 64 * 1024
        tracemalloc.start()
        read_text_window(fs, big, max_bytes=cap)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert peak < 4 * cap, f"peak {peak} should track the cap, not the file"


class TestDefaults:
    def test_default_window_is_capped_by_the_maximum(self, fs: LocalFileSystem, log: Path) -> None:
        window = read_text_window(fs, log, max_bytes=MAX_TEXT_WINDOW_BYTES * 10)
        assert window.total_bytes == log.stat().st_size
        assert DEFAULT_TEXT_WINDOW_BYTES <= MAX_TEXT_WINDOW_BYTES
