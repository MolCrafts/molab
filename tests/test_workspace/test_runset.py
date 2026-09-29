"""RunSet / RunSetResult — the workspace-layer batch container (runset-api sub-task 2).

Pure-container behaviour only: sequence protocol, record building, summary
helpers (``to_records`` / ``min_by`` / ``max_by``), persisted outputs read
through the run-executor seam, and lazy seam resolution. Execution through the workflow layer is locked in
``tests/test_workflow/test_runset_execute.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from molab.workspace import GridSpace, Run, Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.runset import RunRecord, RunSet, RunSetResult


@pytest.fixture
def experiment(tmp_path: Path):
    ws = Workspace(root=tmp_path / "ws", name="lab")
    return ws.add_project("demo").add_experiment("sweep")


def _seeded_runset(experiment) -> RunSet:
    runs = experiment.add_runs(GridSpace({"lr": [0.1, 0.2], "batch": [16, 32]}))
    return RunSet(runs)


class TestRunSetContainer:
    def test_sequence_protocol(self, experiment) -> None:
        rs = _seeded_runset(experiment)
        assert len(rs) == 4
        assert rs[0].parameters == {"lr": 0.1, "batch": 16}
        assert [r.id for r in rs] == [r.id for r in rs.runs]

    def test_collect_unexecuted_runs_reports_pending(self, experiment) -> None:
        summary = _seeded_runset(experiment).collect()
        assert len(summary) == 4
        assert all(rec["status"] == "pending" for rec in summary.to_records())

    def test_execute_resolves_workflow_layer_lazily(self, tmp_path: Path) -> None:
        """``import molab`` wires the seam lazily: ``RunSet.execute`` in a
        process that never imported ``molab.workflow`` loads it on demand."""
        code = (
            "import sys\n"
            "from molab.workspace import GridSpace, Workspace\n"
            "from molab.workspace.runset import RunSet\n"
            "assert 'molab.workflow' not in sys.modules\n"
            f"ws = Workspace(root={str(tmp_path / 'ws2')!r}, name='lab')\n"
            "exp = ws.add_project('p').add_experiment('e')\n"
            "rs = RunSet(exp.add_runs(GridSpace({'x': [1]})))\n"
            "[record] = rs.execute().to_records()\n"
            "assert record['status'] == 'pending', record\n"
            "assert record['error'].startswith('RuntimeError: '), record\n"
            "assert 'no workflow bound' in record['error'], record\n"
            "assert 'molab.workflow' in sys.modules\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout


class TestRunSetPersistedOutputs:
    def test_collect_reads_latest_execution_through_seam(self, experiment, stub_executor) -> None:
        run = experiment.add_run(params={"lr": 0.1})
        with run.start() as ctx:
            first = ctx.id
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            second = ctx.id
        assert (first, second) == ("e01", "e02")
        stub_executor.outputs = {"e01": {"loss": 1}, "e02": {"loss": 2}}

        records = RunSet([run]).collect().to_records()

        assert records[0]["loss"] == 2
        assert stub_executor.calls == [(run.id, "e02")]

    def test_collect_skips_seam_for_unexecuted_runs(self, experiment, stub_executor) -> None:
        summary = _seeded_runset(experiment).collect()
        assert stub_executor.calls == []
        assert all(rec["status"] == "pending" for rec in summary.to_records())

    def test_outputs_are_not_refiltered(self, experiment, stub_executor) -> None:
        run = experiment.add_run(params={"lr": 0.1})
        with run.start() as ctx:
            eid = ctx.id
        outputs = {"train": {"loss": 0.5}, "model": "<obj>", "none": None}
        stub_executor.outputs[eid] = outputs

        [record] = RunSet([run]).collect()

        assert record.outputs == outputs


def _result_fixture() -> RunSetResult:
    return RunSetResult(
        entries=(
            RunRecord(
                run_id="r1",
                status="succeeded",
                params={"lr": 0.1},
                outputs={"loss": 0.5},
            ),
            RunRecord(
                run_id="r2",
                status="succeeded",
                params={"lr": 0.2},
                outputs={"loss": 0.3},
            ),
            RunRecord(
                run_id="r3",
                status="failed",
                params={"lr": 0.4},
                outputs={},
                error="ZeroDivisionError: bad cell",
            ),
        )
    )


class TestRunSetResult:
    def test_to_records_flattens_params_and_outputs(self) -> None:
        records = _result_fixture().to_records()
        assert records[0] == {
            "run_id": "r1",
            "status": "succeeded",
            "error": None,
            "lr": 0.1,
            "loss": 0.5,
        }
        assert records[2]["status"] == "failed"
        assert "ZeroDivisionError" in records[2]["error"]

    def test_reserved_keys_win_over_collisions(self) -> None:
        result = RunSetResult(
            entries=(
                RunRecord(
                    run_id="r1",
                    status="succeeded",
                    params={"status": "sneaky", "run_id": "fake"},
                    outputs={},
                ),
            )
        )
        record = result.to_records()[0]
        assert record["run_id"] == "r1"
        assert record["status"] == "succeeded"

    def test_min_by_and_max_by(self) -> None:
        result = _result_fixture()
        assert result.min_by("loss")["run_id"] == "r2"
        assert result.max_by("loss")["run_id"] == "r1"

    def test_min_by_missing_key_raises(self) -> None:
        with pytest.raises(ValueError, match="nope"):
            _result_fixture().min_by("nope")

    def test_no_dataframe_bridge(self) -> None:
        """molab deliberately ships NO pandas bridge — ``to_records()`` rows
        are plain dicts for whatever analysis stack the operator uses."""
        assert not hasattr(_result_fixture(), "to_dataframe")


def _fail_then_retry(run: Run) -> None:
    """e01 fails, e02 (a RETRY of e01) succeeds — built through the public API."""
    with pytest.raises(RuntimeError), run.start():
        raise RuntimeError("boom")
    with run.start(mode=ExecutionMode.RETRY, based_on_execution_id="e01"):
        pass


class TestRunSetStatus:
    """arch-own-02e D70: a RunSet row's status is its run's ``status_label``."""

    def test_row_status_is_status_label(self, experiment) -> None:
        run_a = experiment.add_run(params={"k": 1})
        _fail_then_retry(run_a)
        run_b = experiment.add_run(params={"k": 2})

        rows = RunSet([run_a, run_b]).collect().to_records()

        assert [r["status"] for r in rows] == [run_a.status_label, run_b.status_label]
        assert [r["status"] for r in rows] == ["succeeded", "pending"]


class TestRunSetResultFailed:
    """``failed`` keeps every terminal non-success row, not only ``failed``."""

    def test_failed_keeps_cancelled_and_interrupted(self) -> None:
        statuses = [
            "succeeded",
            "failed",
            "cancelled",
            "interrupted",
            "running",
            "queued",
            "pending",
        ]
        result = RunSetResult(
            entries=tuple(
                RunRecord(run_id=f"r{i}", status=s, params={}, outputs={})
                for i, s in enumerate(statuses)
            )
        )

        assert [rec.status for rec in result.failed] == ["failed", "cancelled", "interrupted"]
