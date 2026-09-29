"""The node journal (``_engine/persistence.py``): writer, readers and the seed gate.

The journal is ``executions/eNN/workflow.json``, written by the workflow layer
into the directory the workspace hands it and read back through the
workspace ``FileSystem``. The seed gate (``_verify_seeds``, reached here
through ``read_resume_seeds``) keeps a predecessor's output only when that
task and every upstream of it are verified.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import molab.workflow
from molab.fs import LocalFileSystem
from molab.workflow import (
    Next,
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
    read_journal,
    read_outputs,
    read_resume_seeds,
)
from molab.workflow._engine import persistence
from molab.workflow._engine.persistence import (
    close_execution_document,
    mark_task_status,
    mark_workflow_finished,
    open_execution_document,
    write_initial_workflow_json,
)
from molab.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem
from tests.support.journal import poison_node_output

# ── module-level task bodies (v1 / v2 differ in exactly one body) ───────────


def a_v1() -> int:
    return 1


def a_v2() -> int:
    return 2


def b(a: int) -> int:
    return a + 10


def params_v1(prev: object) -> dict:
    return {"k": 1}


def params_v2(prev: object) -> dict:
    return {"k": 2}


def route() -> Next:
    return Next("left")


def left() -> str:
    return "L"


def right_v1() -> str:
    return "R"


def right_v2() -> str:
    return "R2"


def acc(value: int | None = None) -> int:
    return (value or 0) + 1


def check_v1(acc: int) -> tuple[int, Next]:
    return acc, Next("exit" if acc >= 2 else "continue")


def check_v2(acc: int) -> tuple[int, Next]:
    return acc, Next("exit" if acc > 1 else "continue")


# ── builders / helpers ──────────────────────────────────────────────────────


def _ab(a_body=a_v1, *, dependent_params=None, name: str = "ab"):
    wf = Workflow(name=name)
    wf.add(a_body, name="a")
    wf.add(b, name="b", depends_on=["a"], dependent_params=dependent_params)
    return WorkflowCompiler().compile(wf)


def _branchy(right_body):
    wf = Workflow(name="branchy", entry="route")
    wf.add(route, name="route")
    wf.add(left, name="left")
    wf.add(right_body, name="right")
    wf.branch("route", routes={"left": "left", "right": "right"})
    return WorkflowCompiler().compile(wf)


def _loop(check_body):
    wf = Workflow(name="looping", entry="acc")
    wf.add(acc, name="acc")
    wf.add(check_body, name="check", depends_on=["acc"])
    wf.loop(body=["acc"], until="check", max_iters=3)
    return WorkflowCompiler().compile(wf)


def _run(tmp_path: Path, *, fs=None):
    ws = Workspace(tmp_path / "ws", name="lab", fs=fs)
    return ws.add_project("p").add_experiment("e").add_run(params={"x": 1})


def _execute(run, compiled):
    with run.start() as ctx:
        result = asyncio.run(WorkflowRuntime().execute(compiled, run_context=ctx))
    return result


def _journal_file(run, execution_id: str = "e01") -> Path:
    return run.execution_dir(execution_id) / "workflow.json"


def _rewrite(run, mutate, execution_id: str = "e01") -> None:
    path = _journal_file(run, execution_id)
    doc = json.loads(path.read_text())
    mutate(doc)
    path.write_text(json.dumps(doc))


def _record(doc: dict, name: str) -> dict:
    return next(t for t in doc["task_configs"] if t["task_id"] == name)


class _Collect:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def handle(self, record) -> None:
        self.messages.append(getattr(record, "message", str(record)))


def _collect_warnings(fn):
    from mollog import get_logger

    logger = get_logger(persistence.__name__)
    handler = _Collect()
    logger.add_handler(handler)
    try:
        value = fn()
    finally:
        logger.remove_handler(handler)
    return value, handler.messages


# ── writer ──────────────────────────────────────────────────────────────────


class TestOpenExecutionDocument:
    def test_v3_header(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _ab()
        result = _execute(run, compiled)
        assert result.status == "succeeded"

        doc = read_journal(run, result.execution_id)
        assert doc is not None
        assert doc["schema_version"] == 3
        assert doc["execution_id"] == "e01"
        assert doc["based_on_execution_id"] is None
        assert doc["workflow_digest"] == compiled.workflow_digest
        assert doc["workflow_name"] == "ab"
        assert doc["started_at"] is not None
        assert doc["finished_at"] is not None
        assert {"status", "outputs", "error"}.isdisjoint(doc)
        if "workflow_id" in doc:
            assert doc["workflow_id"] == compiled.to_ir(strict=False)["workflow_id"]

    def test_writes_into_the_given_directory(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _ab()
        with run.start() as ctx:
            journal_dir = run.execution_dir(ctx.id)
            open_execution_document(journal_dir, execution_id=ctx.id, compiled=compiled)
            close_execution_document(journal_dir)
        doc = json.loads((journal_dir / "workflow.json").read_text())
        assert {_record(doc, "a")["status"], _record(doc, "b")["status"]} == {"pending"}

    def test_none_directory_is_a_no_op(self) -> None:
        open_execution_document(None, execution_id="e01", compiled=_ab())
        close_execution_document(None)


class TestMarkTaskStatus:
    def test_completion_flushes_synchronously_with_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(persistence, "WORKFLOW_JSON_MAX_STALENESS_S", 60)
        run = _run(tmp_path)
        compiled = _ab()
        with run.start() as ctx:
            journal_dir = run.execution_dir(ctx.id)
            open_execution_document(journal_dir, execution_id=ctx.id, compiled=compiled)
            try:
                mark_task_status(journal_dir, "a", "running")
                on_disk = json.loads((journal_dir / "workflow.json").read_text())
                assert _record(on_disk, "a")["status"] == "pending"

                mark_task_status(
                    journal_dir,
                    "a",
                    "completed",
                    output=1,
                    snapshot_key="k",
                    dependent_params_hash="p",
                )
                on_disk = json.loads((journal_dir / "workflow.json").read_text())
                record = _record(on_disk, "a")
                assert record["status"] == "completed"
                assert record["outputs"] == 1
                assert record["snapshot_key"] == "k"
                assert record["dependent_params_hash"] == "p"
            finally:
                close_execution_document(journal_dir)

    def test_failure_flushes_synchronously(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(persistence, "WORKFLOW_JSON_MAX_STALENESS_S", 60)
        run = _run(tmp_path)
        with run.start() as ctx:
            journal_dir = run.execution_dir(ctx.id)
            open_execution_document(journal_dir, execution_id=ctx.id, compiled=_ab())
            try:
                mark_task_status(journal_dir, "a", "failed", error="RuntimeError: x")
                on_disk = json.loads((journal_dir / "workflow.json").read_text())
                assert _record(on_disk, "a")["status"] == "failed"
                assert _record(on_disk, "a")["error"] == "RuntimeError: x"
            finally:
                close_execution_document(journal_dir)

    def test_none_directory_is_a_no_op(self) -> None:
        mark_task_status(None, "a", "completed", output=1)


class TestMarkWorkflowFinished:
    def test_closes_the_window_without_a_status(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        with run.start() as ctx:
            journal_dir = run.execution_dir(ctx.id)
            open_execution_document(journal_dir, execution_id=ctx.id, compiled=_ab())
            mark_task_status(journal_dir, "a", "completed", output=1)
            mark_workflow_finished(journal_dir, succeeded=True)
        doc = json.loads((journal_dir / "workflow.json").read_text())
        assert doc["finished_at"] is not None
        assert {"status", "outputs", "error"}.isdisjoint(doc)
        # The link a → b was running once a completed; success settles it.
        assert {link["status"] for link in doc["links"]} == {"completed"}

    def test_failure_leaves_running_links(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        with run.start() as ctx:
            journal_dir = run.execution_dir(ctx.id)
            open_execution_document(journal_dir, execution_id=ctx.id, compiled=_ab())
            mark_task_status(journal_dir, "a", "completed", output=1)
            mark_workflow_finished(journal_dir, succeeded=False)
        doc = json.loads((journal_dir / "workflow.json").read_text())
        assert doc["finished_at"] is not None
        assert "status" not in doc
        assert {link["status"] for link in doc["links"]} == {"running"}


# ── readers ─────────────────────────────────────────────────────────────────


class TestReadJournal:
    def test_reads_through_workspace_fs(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        run = _run(tmp_path, fs=fs)
        compiled = _ab()
        _execute(run, compiled)

        fs.reset()
        doc = read_journal(run, "e01")
        assert doc is not None and doc["execution_id"] == "e01"
        assert fs.for_basename("workflow.json", "read_text") == 1
        assert fs.for_basename("workflow.json", "is_file") == 1

        fs.reset()
        assert read_journal(run, "e09") is None
        assert fs.for_basename("workflow.json", "read_text") == 0

        fs.reset()
        assert read_resume_seeds(run, "e01", compiled) == {"a": 1, "b": 11}
        assert fs.for_basename("workflow.json", "read_text") == 1

    @pytest.mark.parametrize("content", ["{not json", "[]", '"text"'])
    def test_malformed_or_non_object_is_none(self, tmp_path: Path, content: str) -> None:
        run = _run(tmp_path)
        with run.start() as ctx:
            eid = ctx.id
        path = _journal_file(run, eid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        assert read_journal(run, eid) is None

    def test_exported_from_molab_workflow(self) -> None:
        exported = set(molab.workflow.__all__)
        assert {"read_journal", "read_outputs", "read_resume_seeds"} <= exported
        assert "compute_workflow_digest" in exported


def _hand_journal(run, tasks: list[dict]) -> str:
    with run.start() as ctx:
        eid = ctx.id
    path = _journal_file(run, eid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 3, "task_configs": tasks, "links": []}))
    return eid


class TestReadOutputs:
    @pytest.mark.parametrize("status", ["failed", "running", "pending"])
    def test_omits_non_completed(self, tmp_path: Path, status: str) -> None:
        run = _run(tmp_path)
        eid = _hand_journal(
            run,
            [
                {"task_id": "a", "status": "completed", "outputs": 1},
                {"task_id": "b", "status": status, "outputs": 2},
            ],
        )
        assert read_outputs(run, eid) == {"a": 1}

    @pytest.mark.parametrize("content", ["{not json", "[]"])
    def test_malformed_journal_is_empty(self, tmp_path: Path, content: str) -> None:
        run = _run(tmp_path)
        with run.start() as ctx:
            eid = ctx.id
        path = _journal_file(run, eid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        assert read_outputs(run, "e01") == {}

    def test_omits_lossy_with_warning(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        eid = _hand_journal(
            run,
            [
                {"task_id": "a", "status": "completed", "outputs": 1},
                {
                    "task_id": "model",
                    "status": "completed",
                    "outputs": "<obj>",
                    "outputs_lossy": True,
                },
            ],
        )
        outputs, messages = _collect_warnings(lambda: read_outputs(run, eid))
        assert outputs == {"a": 1}
        assert any("'model'" in message and "lossy" in message for message in messages), messages
        # The reader serves read-back (Run.get_result / RunSet) as well as
        # resume seeding: its warning must not speak of resume (arch-own-03d).
        assert not any("resume" in m or "recomputed" in m for m in messages), messages
        assert any("JSON-safe" in m for m in messages), messages

    def test_returns_poisoned_value(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _execute(run, _ab())
        poison_node_output(run.run_dir, "e01", "a", 41)
        assert read_outputs(run, "e01") == {"a": 41, "b": 11}


class TestReadResumeSeeds:
    def test_no_predecessor_journal_is_empty(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        with run.start():
            pass
        assert read_resume_seeds(run, "e01", _ab()) == {}

    def test_matching_workflow_offers_every_output(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _ab()
        _execute(run, compiled)
        assert read_resume_seeds(run, "e01", compiled) == {"a": 1, "b": 11}


# ── the seed gate ───────────────────────────────────────────────────────────


class TestVerifySeeds:
    def test_changed_upstream_drops_downstream(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        v1, v2 = _ab(a_v1), _ab(a_v2)
        assert v2.snapshots["b"].key == v1.snapshots["b"].key
        _execute(run, v1)
        assert read_resume_seeds(run, "e01", v1) == {"a": 1, "b": 11}
        seeds, messages = _collect_warnings(lambda: read_resume_seeds(run, "e01", v2))
        assert seeds == {}
        assert any("upstream 'a' is not verified" in message for message in messages), messages

    def test_changed_dependent_params_drops_task(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        v1 = _ab(dependent_params=params_v1)
        v2 = _ab(dependent_params=params_v2)
        assert v1.snapshots["b"].key == v2.snapshots["b"].key
        _execute(run, v1)
        seeds, messages = _collect_warnings(lambda: read_resume_seeds(run, "e01", v2))
        assert seeds == {"a": 1}
        assert any("dependent_params function changed" in m for m in messages), messages

    def test_unfired_branch_route_does_not_block(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        v1, v2 = _branchy(right_v1), _branchy(right_v2)
        assert v1.workflow_digest != v2.workflow_digest
        _execute(run, v1)
        assert _record(read_journal(run, "e01"), "right")["status"] == "pending"
        assert read_resume_seeds(run, "e01", v2) == {"left": "L"}

    def test_loop_back_edge_source_blocks_body(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        v1, v2 = _loop(check_v1), _loop(check_v2)
        assert v1.snapshots["acc"].key == v2.snapshots["acc"].key
        _execute(run, v1)
        assert read_resume_seeds(run, "e01", v1) == {"acc": 2, "check": 2}
        assert read_resume_seeds(run, "e01", v2) == {}

    def test_fast_path_trusts_matching_digest(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _ab()
        _execute(run, compiled)

        _rewrite(run, lambda doc: _record(doc, "a").__setitem__("snapshot_key", "tampered"))
        assert read_resume_seeds(run, "e01", compiled) == {"a": 1, "b": 11}

        _rewrite(run, lambda doc: doc.__setitem__("workflow_digest", "sha256:" + "0" * 64))
        assert read_resume_seeds(run, "e01", compiled) == {}

    def test_filter_resume_seeds_is_removed(self) -> None:
        assert not hasattr(persistence, "filter_resume_seeds")


# ── writer ⟷ reader contract (moved from test_run_result_fallback.py) ───────


class TestWorkflowWriterContract:
    """The journal the writer produces is what both readers consume."""

    @staticmethod
    def _seed_pending_task(run, name: str) -> tuple[str, Path]:
        with run.start() as ctx:
            eid = ctx.id
        journal_dir = run.execution_dir(eid)
        write_initial_workflow_json(journal_dir, execution_id=eid)
        path = journal_dir / "workflow.json"
        doc = json.loads(path.read_text())
        doc["task_configs"] = [{"task_id": name, "status": "pending"}]
        path.write_text(json.dumps(doc))
        return eid, journal_dir

    def test_both_readers_return_the_written_output(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        eid, journal_dir = self._seed_pending_task(run, "train")
        mark_task_status(journal_dir, "train", "completed", output={"loss": 0.5}, snapshot_key="k")
        assert read_outputs(run, eid) == {"train": {"loss": 0.5}}
        assert run.get_result("train", execution_id=eid) == {"loss": 0.5}

    def test_lossy_output_is_offered_by_neither_reader(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        eid, journal_dir = self._seed_pending_task(run, "train")
        mark_task_status(journal_dir, "train", "completed", output=object(), snapshot_key="k")
        assert read_outputs(run, eid) == {}
        assert run.get_result("train", execution_id=eid) is None
