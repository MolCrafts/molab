"""Resume-seed integrity on real RESUME contexts.

A resumed attempt (``run.start(mode=RESUME, predecessor=…)``) seeds
completed-node outputs from its predecessor's journal. The runtime's one seed
gate verifies every seed against the ``based_on`` journal before the new
attempt's journal is opened: a seed survives only when its task's code,
``dependent_params`` and fidelity match AND every upstream is itself verified.
The ``execute(seed_outputs=…)`` fail-fast on unknown names is pinned here too.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from molab.workflow import (
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
    read_journal,
    read_outputs,
    read_resume_seeds,
)
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode

# ── module-level counters + failure switch ──────────────────────────────────
_COUNTERS: dict[str, int] = {}
_FAIL = {"on": True}


def _bump(name: str) -> None:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + 1


@pytest.fixture(autouse=True)
def _reset() -> None:
    _COUNTERS.clear()
    _FAIL["on"] = True


# ── task bodies: a → b → c, where c fails while the switch is on ────────────


def a_v1() -> int:
    _bump("a")
    return 1


def a_v2() -> int:
    _bump("a")
    return 2


def b_v1(a: int) -> int:
    _bump("b")
    return a + 10


def b_v2(a: int) -> int:
    _bump("b")
    return a + 100


def c(b: int) -> int:
    _bump("c")
    if _FAIL["on"]:
        raise RuntimeError("c is not ready")
    return b


class _Opaque:
    """A non-JSON-safe output (stored through the lossy rendering)."""


def opaque() -> object:
    _bump("opaque")
    return _Opaque()


def after(opaque: object) -> str:
    _bump("after")
    if _FAIL["on"]:
        raise RuntimeError("after is not ready")
    return "done"


def step() -> str:
    _bump("step")
    return "computed"


def _chain(a_body=a_v1, b_body=b_v1):
    wf = Workflow(name="chain")
    wf.add(a_body, name="a")
    wf.add(b_body, name="b", depends_on=["a"])
    wf.add(c, name="c", depends_on=["b"])
    return WorkflowCompiler().compile(wf)


def _run(tmp_path: Path):
    ws = Workspace(tmp_path / "ws", name="lab")
    return ws.add_project("p").add_experiment("e").add_run(params={"x": 1})


def _attempt(run, compiled, *, mode=None, based_on=None, seed_outputs=None):
    kwargs = {} if mode is None else {"mode": mode, "predecessor": based_on}
    with run.start(**kwargs) as ctx:
        return asyncio.run(
            WorkflowRuntime().execute(compiled, run_context=ctx, seed_outputs=seed_outputs)
        )


def _resume(run, compiled, seed_outputs, *, bypass_cache=False):
    with run.start(mode=ExecutionMode.RESUME, predecessor="e01", bypass_cache=bypass_cache) as ctx:
        return asyncio.run(
            WorkflowRuntime().execute(compiled, run_context=ctx, seed_outputs=seed_outputs)
        )


def _failed_e01(run, compiled) -> None:
    result = _attempt(run, compiled)
    assert result.status == "failed"
    _FAIL["on"] = False


class TestResumeSeedIntegrity:
    def test_completed_node_persists_identity(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _chain()
        _failed_e01(run, compiled)
        doc = read_journal(run, "e01")
        (record,) = [t for t in doc["task_configs"] if t["task_id"] == "a"]
        assert record["status"] == "completed"
        assert record["snapshot_key"] == compiled.snapshots["a"].key
        assert "outputs_lossy" not in record

    def test_intact_seed_skips_body(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = _chain()
        _failed_e01(run, compiled)
        seeds = read_resume_seeds(run, "e01", compiled)
        assert seeds == {"a": 1, "b": 11}

        result = _resume(run, compiled, seeds)

        assert result.status == "succeeded"
        assert result.execution_id == "e02"
        assert result.outputs == {"a": 1, "b": 11, "c": 11}
        assert _COUNTERS == {"a": 1, "b": 1, "c": 2}
        assert read_journal(run, "e02")["based_on_execution_id"] == "e01"

    def test_changed_code_seed_dropped_and_recomputed(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _failed_e01(run, _chain())
        v2 = _chain(b_body=b_v2)

        result = _resume(run, v2, read_outputs(run, "e01"))

        assert result.status == "succeeded"
        assert result.outputs["b"] == 101
        assert _COUNTERS["a"] == 1
        assert _COUNTERS["b"] == 2

    def test_changed_upstream_recomputes_downstream(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _failed_e01(run, _chain())
        v2 = _chain(a_body=a_v2)

        result = _resume(run, v2, {"a": 1, "b": 11})

        assert result.status == "succeeded"
        assert _COUNTERS["a"] == 2
        assert _COUNTERS["b"] == 2
        assert result.outputs["b"] == 12

    def test_lossy_seed_recomputed(self, tmp_path: Path) -> None:
        wf = Workflow(name="lossy")
        wf.add(opaque, name="opaque")
        wf.add(after, name="after", depends_on=["opaque"])
        compiled = WorkflowCompiler().compile(wf)
        run = _run(tmp_path)
        _failed_e01(run, compiled)
        doc = read_journal(run, "e01")
        (record,) = [t for t in doc["task_configs"] if t["task_id"] == "opaque"]
        assert record["outputs_lossy"] is True
        assert read_resume_seeds(run, "e01", compiled) == {}

        result = _resume(run, compiled, {"opaque": record["outputs"]})

        assert result.status == "succeeded"
        assert _COUNTERS["opaque"] == 2

    def test_unverifiable_record_recomputed(self, tmp_path: Path) -> None:
        """A pre-upgrade journal (no digest, no snapshot keys) cannot vouch for
        its outputs, so they are recomputed."""
        run = _run(tmp_path)
        compiled = _chain()
        _failed_e01(run, compiled)
        path = run.execution_dir("e01") / "workflow.json"
        doc = json.loads(path.read_text())
        doc.pop("workflow_digest")
        for task in doc["task_configs"]:
            task.pop("snapshot_key", None)
        path.write_text(json.dumps(doc))

        # Bypass the node cache so a recompute is observable as a body run.
        result = _resume(run, compiled, read_outputs(run, "e01"), bypass_cache=True)

        assert result.status == "succeeded"
        assert _COUNTERS["a"] == 2

    def test_seeds_pass_through_on_initial_context(self, tmp_path: Path) -> None:
        """With no predecessor there is nothing to verify against, so
        programmatic seeds are honoured."""
        wf = Workflow(name="one")
        wf.add(step, name="step")
        run = _run(tmp_path)

        result = _attempt(run, WorkflowCompiler().compile(wf), seed_outputs={"step": "from-memory"})

        assert result.status == "succeeded"
        assert result.outputs["step"] == "from-memory"
        assert _COUNTERS.get("step", 0) == 0

    def test_unknown_seed_name_fails_fast(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        with pytest.raises(ValueError, match="unknown task name"):
            _attempt(run, _chain(), seed_outputs={"nope": 1})
