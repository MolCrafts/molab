"""Adopting an attempt that ran outside molab (``Run.adopt_execution``).

A finished scheduler job is recorded as a sealed attempt with its real
times, and its bytes are renamed — never copied — into the attempt.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.file_store import FileStore

T0 = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 28, 22, 30, tzinfo=UTC)


@pytest.fixture
def run(tmp_path):
    ws = Workspace(tmp_path / "lab", name="lab")
    return ws.add_project("p").add_experiment("e").add_run(params={"pot": "fp32", "seed": 0})


@pytest.fixture
def arm(tmp_path):
    root = tmp_path / "old" / "pot=fp32_seed=0"
    (root / "out").mkdir(parents=True)
    (root / "out" / "nve.csv").write_text("t,E\n0,1\n")
    (root / "out" / "nve.xyz").write_text("193\n\n")
    (root / "run.log").write_text("TARGET REACHED\n")
    (root / "slurm-1.out").write_text("chunk 1\n")
    (root / "slurm-2.out").write_text("chunk 2\n")
    return root


def test_a_finished_job_becomes_a_sealed_attempt_with_its_real_times(run, arm):
    inode = (arm / "out" / "nve.csv").stat().st_ino

    record = run.adopt_execution(
        started_at=T0,
        finished_at=T1,
        products={"nve": arm / "out"},
        jobs=[arm / "slurm-1.out", arm / "slurm-2.out"],
        log=arm / "run.log",
        executor={"scheduler": "slurm", "job_ids": ["1", "2"]},
    )

    assert record.id == "e01"
    assert record.status is ExecutionStatus.SUCCEEDED
    assert record.sealed
    assert (record.started_at, record.finished_at) == (T0, T1)
    attempt = run.execution_dir("e01")
    moved = attempt / "out" / "nve" / "nve.csv"
    assert moved.read_text() == "t,E\n0,1\n"
    assert moved.stat().st_ino == inode, "a rename keeps the inode; a copy would not"
    assert (attempt / "jobs" / "slurm-2.out").is_file()
    assert (attempt / "run.log").read_text() == "TARGET REACHED\n"
    assert not (arm / "out").exists()
    kinds = {(ev.kind, ev.rel_path) for ev in record.evidence}
    assert ("adopted", "out/nve") in kinds
    assert ("runtime", "run.log") in kinds
    assert ("adopted", "run.log") not in kinds, "an evidence file is recorded once, by its own kind"
    assert run.status_label == "succeeded"
    on_disk = json.loads((attempt / "execution.json").read_text())
    assert on_disk["executor"]["job_ids"] == ["1", "2"]


def test_a_single_file_product_lands_inside_the_task_directory(run, arm):
    run.adopt_execution(started_at=T0, finished_at=T1, products={"nve": arm / "out" / "nve.csv"})
    assert (run.execution_dir("e01") / "out" / "nve" / "nve.csv").is_file()


def test_a_refused_adoption_moves_everything_back_and_writes_nothing(run, arm):
    with pytest.raises(FileExistsError):
        run.adopt_execution(
            started_at=T0,
            finished_at=T1,
            products={"nve": [arm / "out" / "nve.csv", arm / "out" / "nve.csv"]},
        )
    assert (arm / "out" / "nve.csv").is_file()
    assert run.executions == []
    assert not run.execution_dir("e01").exists()


def test_a_missing_source_is_refused_before_anything_moves(run, arm):
    with pytest.raises(FileNotFoundError):
        run.adopt_execution(
            started_at=T0, finished_at=T1, products={"nve": [arm / "out", arm / "nope"]}
        )
    assert (arm / "out" / "nve.csv").is_file()


def test_a_non_terminal_status_is_refused(run, arm):
    with pytest.raises(ValueError, match="non-terminal"):
        run.adopt_execution(status="running", started_at=T0, finished_at=T1)


def test_a_second_adoption_follows_the_mode_rules(run, arm, tmp_path):
    run.adopt_execution(status="failed", started_at=T0, finished_at=T1, error={"type": "Timeout"})
    with pytest.raises(ValueError):
        run.adopt_execution(started_at=T0, finished_at=T1)
    record = run.adopt_execution(
        mode=ExecutionMode.RESUME, started_at=T0, finished_at=T1, products={"nve": arm / "out"}
    )
    assert record.id == "e02"
    assert record.based_on_execution_id == "e01"
    assert run.status_label == "succeeded"


def test_a_destination_outside_a_declared_directory_is_refused(run, tmp_path):
    from molab.workspace.execution_repository import _adopted_destination

    assert _adopted_destination("out/nve") == "out/nve"
    assert _adopted_destination("run.log") == "run.log"
    for bad in ("../x", "/abs", "notadir/x", "nve.csv"):
        with pytest.raises(ValueError):
            _adopted_destination(bad)


class TestMoveIn:
    def test_a_directory_is_renamed_in_and_keeps_its_inode(self, tmp_path):
        src = tmp_path / "src" / "scripts"
        src.mkdir(parents=True)
        (src / "a.py").write_text("x")
        inode = (src / "a.py").stat().st_ino
        store = FileStore(tmp_path / "dst")

        target = store.move_in("code/scripts", src)

        assert (target / "a.py").stat().st_ino == inode
        assert not src.exists()

    def test_an_existing_destination_is_refused(self, tmp_path):
        (tmp_path / "dst").mkdir()
        (tmp_path / "dst" / "a").write_text("keep")
        (tmp_path / "a").write_text("new")
        with pytest.raises(FileExistsError):
            FileStore(tmp_path / "dst").move_in("a", tmp_path / "a")
        assert (tmp_path / "dst" / "a").read_text() == "keep"

    def test_escape_is_refused(self, tmp_path):
        (tmp_path / "a").write_text("x")
        with pytest.raises(ValueError):
            FileStore(tmp_path / "dst").move_in("../a2", tmp_path / "a")


def test_the_fact_is_history_and_the_bytes_are_not(run, arm, tmp_path):
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    from molab.workspace.history import GitHistory

    root = tmp_path / "lab"
    GitHistory(root).init()
    (arm / "out" / "big.traj").write_bytes(b"\0" * (2 << 20))

    record = run.adopt_execution(
        started_at=T0, finished_at=T1, products={"nve": arm / "out"}, log=arm / "run.log"
    )

    assert record.sealed_commit is not None
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    assert "executions/e01/execution.json" in tracked
    assert "executions/e01/run.log" in tracked
    assert "big.traj" not in tracked and "nve.csv" not in tracked
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    assert subject.startswith("ExecutionAdopted:")


def test_products_dir_reads_the_newest_succeeded_attempt(run, arm):
    with pytest.raises(LookupError):
        run.products_dir("nve")
    run.adopt_execution(started_at=T0, finished_at=T1, products={"nve": arm / "out"})
    run.adopt_execution(mode=ExecutionMode.RERUN, status="failed", started_at=T0, finished_at=T1)
    assert run.products_dir("nve") == run.execution_dir("e01") / "out" / "nve"
    assert (run.products_dir("nve") / "nve.csv").is_file()
    assert run.products_dir("nve", execution_id="e02").parent.parent.name == "e02"


def test_a_project_import_records_what_it_consumed(tmp_path):
    ws = Workspace(tmp_path / "lab", name="lab")
    project = ws.add_project("p")
    src = tmp_path / "model.ckpt"
    src.write_bytes(b"weights")

    asset = project.import_asset("model", src, "move", consumed=["upstream-id"])

    (version,) = project.assets.versions(asset.id)
    assert version.origin.input_ids == ("upstream-id",)
    assert version.content is not None
    assert version.content.size == len(b"weights")


def test_a_cache_only_attempt_does_not_shadow_the_products(run, arm):
    run.adopt_execution(started_at=T0, finished_at=T1, products={"nve": arm / "out"})
    # a rerun served from the node cache: succeeded, but wrote no out/nve
    run.adopt_execution(mode=ExecutionMode.RERUN, started_at=T0, finished_at=T1)
    assert run.products_dir("nve") == run.execution_dir("e01") / "out" / "nve"


def test_an_empty_task_directory_does_not_count_as_products(run, arm):
    run.adopt_execution(started_at=T0, finished_at=T1, products={"nve": arm / "out"})
    run.adopt_execution(mode=ExecutionMode.RERUN, started_at=T0, finished_at=T1)
    (run.execution_dir("e02") / "out" / "nve").mkdir(parents=True)
    assert run.products_dir("nve") == run.execution_dir("e01") / "out" / "nve"
