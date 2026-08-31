"""Tests for ``JsonlEventLog`` (JSONL audit-timeline persistence).

Locks persist-one-03-harness-files:
- ``append()`` assigns a monotonic per-``run_id`` ``seq`` starting at 1
- ``list_events`` == ``get_timeline``
- the file is ``tmp_path/events.jsonl``, never under ``artifacts/`` or ``ops/``
- a missing file yields ``[]``
- two ``run_id``s count from 1 independently
- a bad JSON line makes ``list_events`` raise ``ValueError``
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from molexp.harness.store.jsonl_event_log import JsonlEventLog


@pytest.fixture()
def events_path(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture()
def log(events_path: Path) -> JsonlEventLog:
    from molexp.harness.store.jsonl_event_log import JsonlEventLog

    return JsonlEventLog(path=events_path)


class TestJsonlEventLog:
    def test_append_assigns_seq_one_two_three(self, log: JsonlEventLog) -> None:
        log.append(run_id="run-A", type="run_created", actor="harness")
        log.append(run_id="run-A", type="stage_started", actor="harness")
        log.append(run_id="run-A", type="stage_completed", actor="harness")
        assert [e.seq for e in log.list_events("run-A")] == [1, 2, 3]

    def test_list_events_equals_get_timeline(self, log: JsonlEventLog) -> None:
        log.append(run_id="run-A", type="run_created", actor="harness")
        log.append(run_id="run-A", type="stage_started", actor="harness")
        assert log.list_events("run-A") == log.get_timeline("run-A")

    def test_file_is_events_jsonl_not_under_artifacts_or_ops(
        self, log: JsonlEventLog, events_path: Path, tmp_path: Path
    ) -> None:
        log.append(run_id="run-A", type="run_created", actor="harness")
        assert events_path.is_file()
        assert events_path == tmp_path / "events.jsonl"
        assert "artifacts" not in events_path.parts
        assert "ops" not in events_path.parts
        assert not (tmp_path / "artifacts" / "events.jsonl").exists()
        assert not (tmp_path / "ops" / "events.jsonl").exists()

    def test_missing_file_list_events_returns_empty(self, events_path: Path) -> None:
        from molexp.harness.store.jsonl_event_log import JsonlEventLog

        assert not events_path.exists()
        log = JsonlEventLog(path=events_path)
        assert log.list_events("run-A") == []

    def test_two_run_ids_count_from_one_independently(self, log: JsonlEventLog) -> None:
        a1 = log.append(run_id="run-A", type="run_created", actor="harness")
        b1 = log.append(run_id="run-B", type="run_created", actor="harness")
        a2 = log.append(run_id="run-A", type="stage_started", actor="harness")
        b2 = log.append(run_id="run-B", type="stage_started", actor="harness")
        assert [a1.seq, a2.seq] == [1, 2]
        assert [b1.seq, b2.seq] == [1, 2]
        assert [e.seq for e in log.list_events("run-A")] == [1, 2]
        assert [e.seq for e in log.list_events("run-B")] == [1, 2]

    def test_bad_json_line_list_events_raises_value_error(
        self, log: JsonlEventLog, events_path: Path
    ) -> None:
        log.append(run_id="run-A", type="run_created", actor="harness")
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write("{not-json\n")
        with pytest.raises(ValueError):
            log.list_events("run-A")
