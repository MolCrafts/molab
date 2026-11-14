"""molab against the real molq client, on molq's local Shell scheduler.

No stand-in for molq: a temporary stdio service with its own registry, one
local Shell destination registered as a compute target, and molab's own
commands driving it (``molab run --compute-target``, reconcile, ``molab runs
cancel``, ``molab exec``, the dashboard). A change in molq's public contract
breaks these tests, not a live cluster run.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
from molab.workspace import ComputeTarget, Workspace
from molab.workspace.domain import ExecutionStatus
from molab.workspace.run import Run

_SCRIPT = """\
import time
from pathlib import Path

import molab as me
from molab.workflow import TaskContext, Workflow

HOLD = Path({hold!r})
wf = Workflow(name="probe")


@wf.task
def write(ctx: TaskContext, seed: int) -> dict:
    ctx.workdir.mkdir(parents=True, exist_ok=True)
    data = ctx.workdir / "data.txt"
    data.write_text(f"seed={{seed}}")
    print("probe stdout", flush=True)
    while HOLD.exists():
        time.sleep(0.2)
    if seed == 2:
        raise RuntimeError("seed 2 fails after writing its output")
    return {{"data": ctx.register(data, title="data")}}


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={{"seed": [{seed}]}})
"""


@dataclass
class Lab:
    root: Path
    scratch: Path
    hold: Path
    client: object
    cluster_id: str


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Lab]:
    from molq import Molq

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    root = tmp_path / "ws"
    with Molq(registry=tmp_path / "registry.db") as client:
        cluster = client.clusters.register(name="here", scheduler="shell")
        registry_id = client.rpc("molq.hello")["registry_id"]
        cluster_id = cluster.definition()["id"]

        def owned(expected: str | None = None) -> Molq:
            assert expected in (None, registry_id)
            return client

        monkeypatch.setattr("molab.workspace.connection.get_client", owned)
        ws = Workspace(root, name="lab")
        ws.materialize()
        ws.add_target(
            ComputeTarget(
                name="here",
                registry_id=registry_id,
                cluster_id=cluster_id,
                scratch_root=str(scratch),
            )
        )
        monkeypatch.chdir(root)
        yield Lab(root, scratch, tmp_path / "hold", client, cluster_id)


def _molab(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, list(args))
    failure = "" if result.exception is None else f"\n{result.exception!r}"
    return result.exit_code, result.output + failure


def _submit(lab: Lab, seed: int) -> Run:
    script = lab.root / "probe.py"
    script.write_text(_SCRIPT.format(hold=str(lab.hold), seed=seed))
    code, output = _molab("run", str(script), "--compute-target", "here", "-ws", str(lab.root))
    assert code == 0, output
    [project] = Workspace.load(lab.root).list_projects()
    [experiment] = project.list_experiments()
    [run] = experiment.list_runs()
    return run


def _settle(run: Run, timeout: float = 120) -> ExecutionStatus:
    """Reconcile until the attempt is sealed here, as every status reader does."""
    from molab.plugins.submit_molq.submit import reconcile_latest

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        outcome = reconcile_latest(run)
        assert outcome is None or outcome.error is None, outcome.error
        status = run.executions[-1].status
        if status not in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
            return status
        time.sleep(0.3)
    raise AssertionError(f"attempt still {run.executions[-1].status} after {timeout}s")


def _job_ref(run: Run) -> dict:
    return json.loads(run.executions[-1].executor["job_id"])


def _remote_attempt(lab: Lab, run: Run) -> Path:
    [attempt] = lab.scratch.rglob(f"runs/*/executions/{run.executions[-1].id}")
    return attempt


class TestSubmitStatusLogsStageOut:
    def test_a_succeeded_job_comes_home_with_its_output_and_its_logs(self, lab: Lab) -> None:
        run = _submit(lab, seed=1)

        assert _settle(run) is ExecutionStatus.SUCCEEDED
        attempt = Path(str(run.execution_dir(run.executions[-1].id)))
        native = _job_ref(run)["native_id"]
        assert "probe stdout" in (attempt / "jobs" / f"{native}.out").read_text()
        assert list(attempt.rglob("data.txt")), "the succeeded attempt's output came home"
        # molq kept the job's files in the attempt's jobs/ on the target; once
        # what molab keeps is home, they are gone from both sides.
        remote = _remote_attempt(lab, run)
        assert _job_ref(run)["project_root"] == str(remote / "jobs")
        assert not (attempt / "jobs" / ".molq").exists()
        assert not (remote / "jobs" / ".molq").exists()

    def test_a_failed_job_brings_records_and_logs_but_leaves_its_output(self, lab: Lab) -> None:
        run = _submit(lab, seed=2)

        assert _settle(run) is ExecutionStatus.FAILED
        attempt = Path(str(run.execution_dir(run.executions[-1].id)))
        native = _job_ref(run)["native_id"]
        assert (attempt / "jobs" / f"{native}.err").is_file()
        assert (
            "seed 2 fails"
            in (attempt / "run.log").read_text()
            + "".join(path.read_text() for path in attempt.glob("*.txt"))
            + (attempt / "jobs" / f"{native}.err").read_text()
        )
        assert not list(attempt.rglob("data.txt")), "a failed attempt's output stays remote"
        remote = _remote_attempt(lab, run)
        assert list(remote.rglob("data.txt"))
        assert not (attempt / "jobs" / ".molq").exists()
        assert not (remote / "jobs" / ".molq").exists()


class TestCancel:
    def test_cancel_ends_the_job_and_seals_the_attempt(self, lab: Lab) -> None:
        lab.hold.write_text("")
        run = _submit(lab, seed=1)
        job = lab.client.job(_job_ref(run))
        deadline = time.monotonic() + 60
        while job.status()["snapshots"][0]["state"] != "running":
            assert time.monotonic() < deadline, job.status()
            time.sleep(0.2)

        code, output = _molab("runs", "cancel", run.id, "--yes", "-ws", str(lab.root))

        assert code == 0, output
        assert _settle(run) is ExecutionStatus.CANCELLED
        # Sealed from the scheduler's report, not from the cancel request.
        error = run.executions[-1].error
        assert error is not None
        assert "scheduler reported cancelled" in str(error["message"])

    def test_a_cancelled_job_comes_home_like_any_ended_job(self, lab: Lab) -> None:
        lab.hold.write_text("")
        run = _submit(lab, seed=1)
        native = _job_ref(run)["native_id"]
        remote = _remote_attempt(lab, run)
        deadline = time.monotonic() + 60
        while not list(remote.rglob("data.txt")):
            assert time.monotonic() < deadline, "the worker never wrote its output"
            time.sleep(0.2)

        code, output = _molab("runs", "cancel", run.id, "--yes", "-ws", str(lab.root))

        assert code == 0, output
        assert _settle(run) is ExecutionStatus.CANCELLED
        record = run.executions[-1]
        assert "host" in record.executor, "the worker's record came home"
        attempt = Path(str(run.execution_dir(record.id)))
        assert (attempt / "run.log").is_file()
        assert "probe stdout" in (attempt / "jobs" / f"{native}.out").read_text()
        assert not list(attempt.rglob("data.txt")), "a cancelled attempt's output stays remote"
        assert list(remote.rglob("data.txt"))
        assert not (attempt / "jobs" / ".molq").exists()
        assert not (remote / "jobs" / ".molq").exists()


class TestExec:
    def test_exec_prints_the_command_output_and_leaves_no_job_files(self, lab: Lab) -> None:
        code, output = _molab("exec", "-t", "@here", "--", "echo", "molq-exec-ok")

        assert code == 0, output
        assert "molq-exec-ok" in output
        assert not list(lab.scratch.rglob(".molq")), "exec cleans up the job it owned"


class TestDashboard:
    def test_a_shell_destination_is_listed_without_a_queue_error(self, lab: Lab) -> None:
        from molab.plugins.submit_molq.dashboard import list_jobs, list_targets

        [target] = list_targets()

        assert target.healthy, target.health_reason
        assert list_jobs() == []
