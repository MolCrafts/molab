"""Public-API goldens for arch-own-00-safety-net.

Chain-invariant behaviours every arch-own spec must keep (none is an xfail
target):

1. ``Run.execute`` INITIAL returns the per-task outputs
   ``{"double": 6, "summarize": "got 6"}`` for ``x=3``.
2. A failed run re-executed with ``rerun=True`` opens a second attempt:
   modes ``["initial", "rerun"]`` and ``outputs["stage_b"] == 200`` for ``x=1``.
3. ``POST .../runs/{id}/executions`` with ``{}`` on an empty run answers 201
   with ``{"id": "e01", "mode": "initial", "status": "queued"}``.
4. An e01 that emitted ``metrics.json``: its ``/files`` node
   ``artifacts/metrics.json`` carries a non-empty ``assetId``, and promoting
   the artifact answers 201 with ``asset.versionCount == 1``.

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no network, no subprocess.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.workflow import RunFailedError, Workflow, WorkflowCompiler
from molab.workspace import Experiment, Run, Workspace

_INITIAL_OUTPUTS_GOLDEN = {"double": 6, "summarize": "got 6"}
_RERUN_MODES_GOLDEN = ["initial", "rerun"]
_RERUN_STAGE_B_GOLDEN = 200
_CREATE_EXECUTION_GOLDEN = {"id": "e01", "mode": "initial", "status": "queued"}
_METRICS_REL_PATH = "artifacts/metrics.json"


def _build_pipeline() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


def _build_healing(flag: Path) -> Workflow:
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


def _run_url(exp: Experiment, run: Run) -> str:
    return f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}"


def _find_node(nodes: list[dict[str, object]], rel_path: str) -> dict[str, object] | None:
    for node in nodes:
        if node.get("relPath") == rel_path:
            return node
        children = node.get("children")
        if isinstance(children, list):
            found = _find_node(children, rel_path)
            if found is not None:
                return found
    return None


def _check_initial(root: Path) -> None:
    ws = Workspace(root / "ws-initial", name="lab")
    run = ws.add_project("demo").add_experiment("pipeline").add_run(params={"x": 3})
    result = run.execute(WorkflowCompiler().compile(_build_pipeline()))
    assert result.status == "succeeded", result.status
    outputs = {name: result.outputs[name] for name in _INITIAL_OUTPUTS_GOLDEN}
    assert outputs == _INITIAL_OUTPUTS_GOLDEN, outputs
    print(f"[1] INITIAL outputs: {outputs}")


def _check_failed_then_rerun(root: Path) -> None:
    ws = Workspace(root / "ws-rerun", name="lab")
    run = ws.add_project("demo").add_experiment("pipeline").add_run(params={"x": 1})
    flag = root / "healed"
    try:
        run.execute(_build_healing(flag))
    except RunFailedError:
        pass
    else:
        raise AssertionError("first attempt should fail before the flag exists")
    assert [e.status.value for e in run.executions] == ["failed"]

    flag.write_text("ok")
    result = run.execute(_build_healing(flag), rerun=True)
    assert result.status == "succeeded", result.status
    modes = [e.mode.value for e in run.executions]
    assert modes == _RERUN_MODES_GOLDEN, modes
    assert result.outputs["stage_b"] == _RERUN_STAGE_B_GOLDEN, result.outputs
    print(f"[2] failed->rerun modes: {modes}, stage_b: {result.outputs['stage_b']}")


def _check_server(root: Path) -> None:
    ws = Workspace(root / "ws-server", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    empty_run = exp.add_run(params={"x": 1})
    emitted_run = exp.add_run(params={"x": 2})
    with emitted_run.start() as ctx:
        artifact = ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
    artifact_id = artifact.id

    set_workspace_path_override(Path(str(ws.root)))
    try:
        with TestClient(create_app(serve_static=False)) as client:
            created = client.post(f"{_run_url(exp, empty_run)}/executions", json={})
            assert created.status_code == 201, created.text
            body = created.json()
            subset = {key: body[key] for key in _CREATE_EXECUTION_GOLDEN}
            assert subset == _CREATE_EXECUTION_GOLDEN, subset
            print(f"[3] POST executions {{}} -> 201 {subset}")

            files = client.get(f"{_run_url(exp, emitted_run)}/executions/e01/files")
            assert files.status_code == 200, files.text
            node = _find_node(files.json()["nodes"], _METRICS_REL_PATH)
            assert node is not None, files.json()
            asset_id = node.get("assetId")
            assert isinstance(asset_id, str) and asset_id, node
            print(f"[4] /files {_METRICS_REL_PATH} assetId: {asset_id}")

            promoted = client.post(
                f"{_run_url(exp, emitted_run)}/executions/e01/artifacts/{artifact_id}/promote",
                json={},
            )
            assert promoted.status_code == 201, promoted.text
            version_count = promoted.json()["asset"]["versionCount"]
            assert version_count == 1, promoted.json()
            print(f"[4] promote -> 201 versionCount: {version_count}")
    finally:
        set_workspace_path_override(None)


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _check_initial(root)
        _check_failed_then_rerun(root)
        _check_server(root)
    print("arch-own-00-safety-net: all goldens hold")


if __name__ == "__main__":
    main()
