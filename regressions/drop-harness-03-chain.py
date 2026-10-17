"""Public-API goldens for drop-harness-03-chain.

D-5 keeps ``plan_run_id`` as a legacy, read-only experiment field: an old
record that carries it still loads and is still surfaced, but nothing binds a
workflow through it. The rescoped arch-own 04a-04e must keep this contract.

Only facts that hold both before and after arch-own-04c are asserted (which
error is raised, what it does and does not contain). The message wording that
04c rewrites (``workflow_entrypoint``) is deliberately not asserted.

1. A ``plan_run_id`` of ``"legacy-plan-run"`` saved on an experiment survives
   a reopen of the workspace (``Workspace(root=...)`` then
   ``get_folder("p", cls=Project).get_folder("e", cls=Experiment)``).
2. The reopened experiment surfaces it as
   ``ExperimentResponse.from_model(exp).planRunId == "legacy-plan-run"``.
3. A run of that experiment is not recoverable:
   ``can_recover_workflow(run) is False``.
4. ``compiled_workflow_for_run(run)`` raises ``WorkflowRecoveryError`` whose
   message contains ``run.id`` and not ``"molab plan"``.
5. ``molab.workflow`` has no ``set_workflow_recoverer``.

Expected stdout (exactly this line, exit code 0):

    drop-harness-03-chain: ok

Provenance: goldens hard-coded from the spec
``.claude/specs/drop-harness-03-chain.md`` (Testing strategy, "Regression
example") and acceptance ac-006, plus molab's own behaviour (no third-party
oracle), recorded 2026-09-29 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no subprocess, no network, no
third-party runtime.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import molab.workflow
from molab.server.schemas import ExperimentResponse
from molab.workflow.recovery import (
    WorkflowRecoveryError,
    can_recover_workflow,
    compiled_workflow_for_run,
)
from molab.workspace import Experiment, Project, Workspace

_GOLDEN_OK = "drop-harness-03-chain: ok"
_LEGACY_PLAN_RUN_ID = "legacy-plan-run"


def _seed_legacy_record(tmp: Path) -> None:
    ws = Workspace(root=tmp / "lab", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    exp.metadata = exp.metadata.model_copy(update={"plan_run_id": _LEGACY_PLAN_RUN_ID})
    exp.save()


def _check(tmp: Path) -> list[str]:
    _seed_legacy_record(tmp)

    project = Workspace(root=tmp / "lab").get_folder("p", cls=Project)
    exp2 = project.get_folder("e", cls=Experiment)
    assert exp2.metadata.plan_run_id == _LEGACY_PLAN_RUN_ID, exp2.metadata.plan_run_id
    surfaced = ExperimentResponse.from_model(exp2).planRunId
    assert surfaced == _LEGACY_PLAN_RUN_ID, surfaced

    run = exp2.add_run(params={"seed": 1})
    run.materialize()
    assert can_recover_workflow(run) is False

    try:
        compiled_workflow_for_run(run)
    except WorkflowRecoveryError as exc:
        message = str(exc)
    else:
        raise AssertionError("compiled_workflow_for_run did not raise")
    print(f"recovery error: {message}", file=sys.stderr)
    assert run.id in message, message
    assert "molab plan" not in message, message

    assert not hasattr(molab.workflow, "set_workflow_recoverer")
    return [_GOLDEN_OK]


def main() -> None:
    saved_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        os.chdir(raw)
        try:
            lines = _check(Path(raw))
        finally:
            os.chdir(saved_cwd)
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
