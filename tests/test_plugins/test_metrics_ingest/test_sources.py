"""Paging a source: a cursor counts raw records, so resuming never repeats or skips.

``since`` is a raw index — records are skipped before the type/key filters and
before striding (molpy's ``apply_request`` and molab's :func:`apply` agree on
that). A cursor counted in *delivered* records therefore lands somewhere else
in the raw stream as soon as a filter or a stride drops anything: resuming
from it re-reads what the viewer already has, or jumps past what it lacks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab._typing import JSONValue
from molab.plugins.metrics_ingest.readers import ReadProgress, ReadRequest, apply
from molab.plugins.metrics_ingest.sources import (
    MetricSource,
    SourceRead,
    discover_sources,
    read_source,
)

from .conftest import FAKE_FORMAT, FAKE_SUFFIX

KEYS = ("temp", "press", "volume")


def _write_table(path: Path, rows: range) -> None:
    """A thermo-like table: every row carries every column, interleaved."""
    lines = [f"{key} {row}" for row in rows for key in KEYS]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(f"{line}\n" for line in lines))


@pytest.fixture
def table(tmp_path: Path) -> MetricSource:
    path = tmp_path / f"thermo{FAKE_SUFFIX}"
    _write_table(path, range(40))
    (source,) = discover_sources(tmp_path)
    assert source.format == FAKE_FORMAT
    return source


def _identity(read: SourceRead) -> list[tuple[JSONValue, JSONValue]]:
    return [(record["k"], record["v"]) for record in read.records]


def _page_through(
    source: MetricSource, *, limit: int, stride: int = 1, key: str | None = None
) -> list[SourceRead]:
    pages: list[SourceRead] = []
    since = 0
    while True:
        page = read_source(source, since=since, limit=limit, stride=stride, key=key)
        assert page.error is None
        assert page.cursor is not None
        assert page.cursor >= since, "a cursor never moves backwards"
        pages.append(page)
        since = page.cursor
        if page.exhausted:
            return pages
        assert len(pages) < 100, "paging does not terminate"


class TestPagingYieldsEveryWantedRecordOnce:
    @pytest.mark.parametrize(
        ("stride", "key", "limit"),
        [
            (1, "press", 3),
            (3, "press", 4),
            (5, "volume", 1),
            (2, "temp", 7),
            (1, None, 5),
        ],
    )
    def test_pages_concatenate_to_the_single_read(self, table, stride, key, limit):
        whole = read_source(table, limit=None, stride=stride, key=key)
        assert whole.exhausted

        pages = _page_through(table, limit=limit, stride=stride, key=key)
        paged = [item for page in pages for item in _identity(page)]

        assert len(paged) == len(set(paged)), "a record was delivered twice"
        assert paged == _identity(whole), "paging skipped or added records"
        assert len(pages) > 2, "the limit should force several pages"

    @pytest.mark.parametrize(("stride", "limit"), [(4, 5), (2, 7)])
    def test_a_stride_over_several_series_never_repeats_a_record(self, table, stride, limit):
        """One integer cannot carry every series' stride phase, so a page that
        ends mid-row restarts the phase of the series after it. What paging
        still guarantees is that no record arrives twice and none goes back."""
        pages = _page_through(table, limit=limit, stride=stride)
        paged = [item for page in pages for item in _identity(page)]

        assert len(paged) == len(set(paged)), "a record was delivered twice"
        for key in KEYS:
            rows = [row for name, row in paged if name == key]
            assert rows == sorted(rows), f"{key} went back in time"
            assert rows[0] == 0.0
            assert rows[-1] > 40 - stride * 2, f"{key} stopped short of the end"

    def test_the_cursor_counts_raw_records_not_delivered_ones(self, table):
        page = read_source(table, limit=2, key="volume")
        assert [record["v"] for record in page.records] == [0.0, 1.0]
        # volume is the third column: rows 0 and 1 are raw records 0..5, and the
        # next wanted record — row 2's volume — sits at raw index 8.
        assert page.cursor == 8
        assert not page.exhausted

    def test_an_exhausted_read_resumes_after_its_whole_stream(self, table):
        pages = _page_through(table, limit=50, key="temp")
        assert pages[-1].cursor == 40 * len(KEYS)

        _write_table(table.path, range(40, 43))  # the run keeps going
        tail = read_source(table, since=pages[-1].cursor, key="temp")
        assert [record["v"] for record in tail.records] == [40.0, 41.0, 42.0]
        assert tail.cursor == 43 * len(KEYS)

    def test_a_reader_that_does_not_report_leaves_the_cursor_unknown(self, tmp_path):
        """No guessing: a delivered count is not a raw position."""
        path = tmp_path / "series.striding"
        path.write_text("\n".join(f"k {i}" for i in range(20)), encoding="utf-8")
        (source,) = discover_sources(tmp_path)

        page = read_source(source, limit=3, stride=2)

        assert len(page.records) == 3
        assert page.cursor is None


class TestApplyReportsItsRawPosition:
    STREAM: tuple[dict[str, JSONValue], ...] = tuple(
        {"t": "scalar", "k": key, "v": float(row)} for row in range(4) for key in ("a", "b")
    )

    def test_position_points_at_the_record_in_hand_then_at_the_end(self):
        progress = ReadProgress()
        request = ReadRequest(since=1, keys=("a",), progress=progress)
        seen = []
        for record in apply(request, self.STREAM):
            seen.append((record["v"], progress.position))
        assert seen == [(1.0, 2), (2.0, 4), (3.0, 6)]
        assert progress.position == len(self.STREAM)

    def test_a_limit_stop_reports_the_position_after_the_last_record(self):
        progress = ReadProgress()
        kept = list(apply(ReadRequest(limit=2, keys=("b",), progress=progress), self.STREAM))
        assert [record["v"] for record in kept] == [0.0, 1.0]
        assert progress.position == 4

    def test_a_since_past_the_end_never_moves_the_cursor_back(self):
        progress = ReadProgress()
        assert list(apply(ReadRequest(since=50, progress=progress), self.STREAM)) == []
        assert progress.position == 50

    @pytest.mark.parametrize("limit", [0, -3])
    def test_a_non_positive_limit_yields_nothing(self, limit):
        """Matches molpy's ``apply_request``: ``limit <= 0`` is an empty read."""
        progress = ReadProgress()
        assert list(apply(ReadRequest(since=2, limit=limit, progress=progress), self.STREAM)) == []
        assert progress.position == 2
