"""arch-own-05d-asset-readers: named-asset readers, public API only."""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge.embed import summarize_entity
from molab.workspace import AgentRef, Workspace
from molab.workspace.assets import lineage

ACTOR = AgentRef(id="molab", type="system")
HELLO = b"hello\n"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ws = Workspace(root / "lab", name="lab")
        project = ws.add_project("alpha")
        experiment = project.add_experiment("sweep")
        run = experiment.add_run(params={"seed": 1})
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(HELLO)
            artifact = ctx.emit_artifact(path, name="hello.txt")
        asset, _version = project.assets.promote(artifact, created_by=ACTOR, title="greeting")
        assert lineage.ancestors(ws, asset.id) == {artifact.id}
        summary = summarize_entity(asset)
        assert summary.kind == "asset"
        assert summary.title == "greeting"
        assert [row.asset_id for row in ws.context().artifacts] == [artifact.id]
    print("arch-own-05d-asset-readers: ok")


if __name__ == "__main__":
    main()
