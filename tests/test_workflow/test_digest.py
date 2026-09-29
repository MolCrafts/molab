"""``compute_workflow_digest`` / ``CompiledWorkflow.workflow_digest`` (``digest.py``).

The digest is the compiled workflow's content-addressed identity: sorted task
records (name, deps, task type, snapshot key, dependent_params hash) plus the
control topology. Declaration order, the display name and scheduling knobs
do not count; a task body does.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import molab.workflow
from molab.workflow import Next, Workflow, WorkflowCompiler, compute_workflow_digest
from molab.workflow.compiled import CompiledWorkflow
from molab.workflow.digest import _dependent_params_hashes

# ── module-level task bodies ────────────────────────────────────────────────


def a() -> int:
    return 1


def b(a: int) -> int:
    return a + 10


def b_other_body(a: int) -> int:
    return a + 20


def c() -> int:
    return 5


def params_v1(prev: object) -> dict:
    return {"k": 1}


def params_v2(prev: object) -> dict:
    return {"k": 2}


def acc(n: int | None = None) -> int:
    return (n or 0) + 1


def check(acc: int) -> tuple[int, Next]:
    return acc, Next("exit" if acc >= 2 else "continue")


def emit() -> list[int]:
    return [1, 2]


def square(x: int) -> int:
    return x * x


def collect(square: list[int]) -> int:
    return sum(square)


# ── builders ────────────────────────────────────────────────────────────────


def _ab(name: str = "ab", *, reverse: bool = False, b_body=b, dependent_params=None):
    wf = Workflow(name=name)
    if reverse:
        wf.add(b_body, name="b", depends_on=["a"], dependent_params=dependent_params)
        wf.add(a, name="a")
    else:
        wf.add(a, name="a")
        wf.add(b_body, name="b", depends_on=["a"], dependent_params=dependent_params)
    return WorkflowCompiler().compile(wf)


def _loop(max_iters: int):
    wf = Workflow(name="loop", entry="acc")
    wf.add(acc, name="acc")
    wf.add(check, name="check", depends_on=["acc"])
    wf.loop(body=["acc"], until="check", max_iters=max_iters)
    return WorkflowCompiler().compile(wf)


def _fanout(max_concurrency: int):
    wf = Workflow(name="fan", entry="emit")
    wf.add(emit, name="emit")
    wf.add(square, name="square")
    wf.add(collect, name="collect")
    wf.parallel(map_over="emit", body="square", join="collect", max_concurrency=max_concurrency)
    return WorkflowCompiler().compile(wf)


class TestComputeWorkflowDigest:
    def test_format(self) -> None:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", compute_workflow_digest(_ab()))

    def test_order_and_name_independent(self) -> None:
        assert compute_workflow_digest(_ab("one")) == compute_workflow_digest(
            _ab("two", reverse=True)
        )

    def test_same_named_task_body_change_differs(self) -> None:
        """The qualname bug: two decorator bodies named ``b`` must not collide."""
        v1, v2 = _ab(), _ab(b_body=b_other_body)
        assert v1.workflow_id == v2.workflow_id
        assert compute_workflow_digest(v1) != compute_workflow_digest(v2)

    def test_depends_on_change_differs(self) -> None:
        wf = Workflow(name="ab")
        wf.add(a, name="a")
        wf.add(c, name="b")
        assert compute_workflow_digest(WorkflowCompiler().compile(wf)) != compute_workflow_digest(
            _ab()
        )

    def test_loop_max_iters_change_differs(self) -> None:
        assert compute_workflow_digest(_loop(3)) != compute_workflow_digest(_loop(4))

    def test_dependent_params_body_change_differs(self) -> None:
        v1 = _ab(dependent_params=params_v1)
        v2 = _ab(dependent_params=params_v2)
        assert compute_workflow_digest(v1) != compute_workflow_digest(v2)
        assert v1.dependent_params_hashes["b"] != v2.dependent_params_hashes["b"]

    def test_max_concurrency_is_not_identity(self) -> None:
        assert compute_workflow_digest(_fanout(1)) == compute_workflow_digest(_fanout(8))

    def test_deterministic_across_processes(self, tmp_path: Path) -> None:
        module = tmp_path / "digest_probe.py"
        module.write_text(
            textwrap.dedent(
                """
                from molab.workflow import Workflow, WorkflowCompiler


                def a() -> int:
                    return 1


                def b(a: int) -> dict:
                    return {"x": a, "y": {1, 2, 3}}


                wf = Workflow(name="probe")
                wf.add(a, name="a")
                wf.add(b, name="b", depends_on=["a"])
                print(WorkflowCompiler().compile(wf).workflow_digest)
                """
            )
        )
        digests = []
        for seed in ("1", "2"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            out = subprocess.run(
                [sys.executable, str(module)],
                capture_output=True,
                text=True,
                check=True,
                env=env,
                cwd=tmp_path,
            )
            digests.append(out.stdout.strip().splitlines()[-1])
        assert digests[0] == digests[1]
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digests[0])

    def test_cached_properties_share_one_hasher(self) -> None:
        assert isinstance(CompiledWorkflow.__dict__["workflow_digest"], functools.cached_property)
        assert isinstance(
            CompiledWorkflow.__dict__["dependent_params_hashes"], functools.cached_property
        )
        plain = _ab()
        assert plain.workflow_digest == molab.workflow.compute_workflow_digest(plain)
        assert plain.dependent_params_hashes["b"] is None
        with_params = _ab(dependent_params=params_v1)
        assert dict(with_params.dependent_params_hashes) == _dependent_params_hashes(with_params)
        assert with_params.dependent_params_hashes["b"] is not None
        assert (
            with_params.dependent_params_hashes["b"]
            != _ab(dependent_params=params_v2).dependent_params_hashes["b"]
        )
