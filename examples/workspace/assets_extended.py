"""Import actions, digest lookup, and artifact scans.

Walks through:

1. ``import_asset`` with ``copy``, ``symlink``, and ``reference``.
2. Checkpoints via ``ctx.checkpoint``.
3. A version-digest lookup over ``scan_asset_repositories``.
4. ``scan_artifacts`` for products an attempt emitted.
5. Title lookup on ``ws.assets.list``.

Run directly::

    python examples/workspace/assets_extended.py
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import molab as me
from molab.ids import compute_content_hash
from molab.workflow import Workflow, WorkflowCompiler, WorkflowRuntime
from molab.workspace import Asset
from molab.workspace.artifact_repository import scan_artifacts, scan_asset_repositories

wf = Workflow(name="extended")


@wf.task
def prepare(seed: int = 42) -> dict:
    return {"data": [1.0, 2.0, 3.0]}


@wf.task(depends_on=["prepare"])
def total(data: list[float]) -> float:
    return sum(data)


compiled = WorkflowCompiler().compile(wf)


def find_by_digest(ws: me.Workspace, digest: str) -> Asset | None:
    """Return the named asset whose latest versions include *digest*."""
    for repo in scan_asset_repositories(ws):
        for asset in repo.list():
            for version in repo.versions(asset.id):
                if version.content is not None and version.content.digest == digest:
                    return asset
    return None


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-assets-ext-"))
    ws = me.Workspace(root, name="assets-ext-demo")

    external = root / "dataset.csv"
    external.write_text("x,y\n1,2\n3,4\n")
    ws.data_assets.import_asset("dataset-copy", external)
    ws.data_assets.import_asset("dataset-link", external, action="symlink")
    ws.data_assets.import_asset("dataset-ref", external, action="reference")
    print(f"workspace root: {root}")

    exp = ws.add_project("demo").add_experiment("train").define(compiled, params={"seed": [42]})
    run = exp.list_runs()[0]
    with run.start() as ctx:
        await WorkflowRuntime().execute(compiled, run_context=ctx)
        ctx.checkpoint("epoch-1", data={"step": 1, "loss": 0.5})
        ctx.checkpoint("epoch-2", data={"step": 2, "loss": 0.2})
        ctx.emit_artifact({"ok": True}, name="result.json")
        ctx.log("run").append("training complete")

    test_file = root / "query-me.txt"
    test_file.write_text("hello reproducibility")
    file_hash = compute_content_hash(test_file)
    ws.data_assets.import_asset("query-target", test_file)
    found = find_by_digest(ws, file_hash)
    print(f"\ncontent-digest lookup: {file_hash[:20]}...")
    if found is not None:
        print(f"  found: {found.title} at {ws.assets.payload_path(found.id)}")

    named = [asset for repo in scan_asset_repositories(ws) for asset in repo.list()]
    print(f"\nnamed assets: {len(named)}")
    for asset in named:
        print(f"  [{asset.kind:<11}] {asset.title:<25} scope={asset.scope.kind}")

    emitted = scan_artifacts(ws)
    print(f"\nemitted artifacts: {len(emitted)}")
    for artifact in emitted:
        print(f"  {artifact.name}")

    dataset = next((asset for asset in ws.assets.list() if asset.title == "dataset-copy"), None)
    location = ""
    if dataset is not None:
        version = ws.assets.versions(dataset.id)[-1]
        location = version.origin.location or version.origin.uri
    print(f"\nlist title 'dataset-copy': {location or 'not found'}")


if __name__ == "__main__":
    asyncio.run(main())
