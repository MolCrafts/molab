"""``molab asset import`` and ``molab asset promote`` register workspace assets."""

from __future__ import annotations

import base64
from pathlib import Path

from typer.testing import CliRunner

from molab.cli import app
from molab.workspace import Workspace
from molab.workspace.domain import ArtifactOrigin

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _lab_with_hair(tmp_path: Path) -> tuple[Workspace, str]:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    run = workspace.add_project("portraits").add_experiment("portrait").add_run(params={"seed": 1})
    with run.start() as ctx:
        image = ctx.get_dir("work") / "hair.png"
        image.write_bytes(_PNG)
        ctx.emit_artifact(image, name="hair.png", media_type="image/png", tags={"part": "hair"})
        notes = ctx.get_dir("work") / "parts.json"
        notes.write_text("{}\n", encoding="utf-8")
        ctx.emit_artifact(notes, name="parts.json", media_type="application/json")
    return workspace, run.id


def test_import_copies_once_and_promote_keeps_the_image(tmp_path: Path) -> None:
    workspace, run_id = _lab_with_hair(tmp_path)
    source = tmp_path / "c001.png"
    source.write_bytes(_PNG)
    root = str(workspace.root)

    imported = CliRunner().invoke(
        app, ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", root]
    )
    assert imported.exit_code == 0, imported.output
    assert imported.output.startswith("imported\tc001\t")

    again = CliRunner().invoke(
        app, ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", root]
    )
    assert again.exit_code == 0, again.output
    assert again.output.startswith("present\tc001\t")

    promoted = CliRunner().invoke(app, ["asset", "promote", run_id, "-ws", root])
    assert promoted.exit_code == 0, promoted.output
    assert promoted.output.startswith("promoted\thair\t")
    assert "parts.json" not in promoted.output

    repeat = CliRunner().invoke(app, ["asset", "promote", run_id, "-ws", root])
    assert repeat.exit_code == 0, repeat.output
    assert repeat.output.startswith("present\thair\t")

    assets = workspace.project("portraits").data_assets.list()
    titles = {asset.title for asset in assets}
    assert titles == {"c001", "hair"}
    hair = next(asset for asset in assets if asset.title == "hair")
    origin = workspace.project("portraits").data_assets.versions(hair.id)[-1].origin
    assert isinstance(origin, ArtifactOrigin)


def test_import_refuses_a_path_that_is_not_a_workspace(tmp_path: Path) -> None:
    source = tmp_path / "c001.png"
    source.write_bytes(_PNG)
    result = CliRunner().invoke(
        app,
        ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "No workspace found" in result.output
