"""arch-own-05c-asset-model: one Asset schema, public API only.

New imports use a UUIDv7 version id (arch-own-05e). The ``<id>-v001`` id belongs
to ``rewrite_legacy`` of an old ``asset_id`` record, not to ``import_asset``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.workspace import AgentRef, Workspace
from molab.workspace.errors import RefNotFoundError

HELLO = b"hello\n"
DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
ACTOR = AgentRef(id="molab", type="system")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ws = Workspace(root / "lab", name="lab")
        project = ws.add_project("alpha")
        exp = project.add_experiment("sweep")
        run = exp.add_run(params={"seed": 1})
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(HELLO)
            art = ctx.emit_artifact(path, name="hello.txt")
        asset, version = project.assets.promote(art, created_by=ACTOR)
        assert version.origin.ref == (  # type: ignore[union-attr]
            f"molab:experiment/{exp.id}/run/{run.id}/artifact/{art.id}"
        )
        assert version.content is not None
        assert version.content.digest == DIGEST
        assert version.content.size == 6
        assert Path(project.assets.payload_path(asset.id)).read_bytes() == HELLO

        src = root / "raw.txt"
        src.write_bytes(HELLO)
        copied = project.data_assets.import_asset("raw", src, action="copy")
        assert project.assets.get(copied.id).title == "raw"
        assert len(project.assets.list()) == 2
        only = project.assets.versions(copied.id)
        assert len(only) == 1
        assert only[0].origin.action == "copy"  # type: ignore[union-attr]
        assert only[0].content is not None
        assert only[0].content.digest == DIGEST

        root_src = root / "root.txt"
        root_src.write_bytes(HELLO)
        root_asset = ws.data_assets.import_asset("root", root_src, action="reference")
        found = ws.find(f"molab:asset/{root_asset.id}")
        assert found.scope.kind == "workspace"  # type: ignore[union-attr]
        try:
            ws.find("molab:asset/missing")
        except RefNotFoundError:
            pass
        else:
            raise SystemExit("missing asset did not raise")
    print("arch-own-05c-asset-model: ok")


if __name__ == "__main__":
    main()
