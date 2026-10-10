"""Public-API golden for the Phase 3 close-out.

A healing workflow: ``stage_a(x) = x + 1`` with ``params={"x": 1}`` so
``stage_a == 2``; ``stage_b`` raises ``RuntimeError`` until a flag file
exists, then returns ``stage_a * 100`` (200). The first ``run.execute``
fails; resume after the flag keeps ``stage_a`` and finishes ``stage_b``.

Hard-coded assertions (no third-party oracle), then exactly one stdout line.

Provenance: ``.claude/specs/arch-own-03j-prune.acceptance.md`` ac-014,
2026-10-01. In-process temporary directory; molab public API and the
stdlib only. ``RunMetadata`` is ``molab.workspace.models.RunMetadata``
(not re-exported from ``molab.workspace``). ``read_outputs`` and
``read_journal`` are the public names on ``molab.workflow``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab.workspace
from molab.workflow import RunFailedError, Workflow, WorkflowResult, read_journal, read_outputs
from molab.workspace import Run, Workspace
from molab.workspace.models import RunMetadata

# Provenance: ac-014 goldens, 2026-10-01, no third-party oracle.
_EXECUTION_ERA = frozenset(
    {"status", "owner_pid", "owner_host", "started_at", "finished_at", "error"}
)


def _healing_wf(flag: Path) -> Workflow:
    wf = Workflow(name="healing")

    @wf.task
    def stage_a(x: int) -> int:
        return x + 1

    @wf.task(depends_on=["stage_a"])
    def stage_b(stage_a: int) -> int:
        if not flag.exists():
            raise RuntimeError("not healed yet")
        return stage_a * 100

    return wf


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        flag = root / "healed.flag"
        wf = _healing_wf(flag)
        ws = Workspace(root / "ws", name="lab")
        run = ws.add_project("demo").add_experiment("pipeline").add_run(params={"x": 1})

        try:
            run.execute(wf)
        except RunFailedError as exc:
            evidence = f"Execution evidence under {run.execution_dir('e01')}"
            assert evidence in str(exc), str(exc)
        else:
            raise AssertionError("first execute did not raise RunFailedError")

        assert read_outputs(run, "e01") == {"stage_a": 2}

        flag.write_text("ok", encoding="utf-8")
        resumed = run.execute(wf, resume=True)
        assert isinstance(resumed, WorkflowResult)
        assert resumed.outputs["stage_b"] == 200

        executions = run.executions
        assert [item.id for item in executions] == ["e01", "e02"]
        assert [item.mode.value for item in executions] == ["initial", "resume"]
        assert executions[1].based_on_execution_id == "e01"

        journal = read_journal(run, "e02")
        assert journal is not None
        assert journal["based_on_execution_id"] == "e01"
        assert "status" not in journal
        digest = journal["workflow_digest"]
        assert isinstance(digest, str) and digest.startswith("sha256:")

        assert sorted(set(RunMetadata.model_fields) & _EXECUTION_ERA) == []
        assert hasattr(molab.workspace, "ErrorInfo") is False

        run_id = run.id
        source = Path(run.run_dir)
        renamed = source.with_name("renamed-by-hand")
        source.rename(renamed)
        loaded = Run.load(renamed)
        assert loaded.id == run_id
        assert [item.id for item in loaded.executions] == ["e01", "e02"]

    print("arch-own-03j-prune: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
