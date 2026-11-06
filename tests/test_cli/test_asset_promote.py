"""``molab asset import`` registers a project asset. The same bytes stay one asset."""

from __future__ import annotations

import base64
from pathlib import Path

from typer.testing import CliRunner

from molab.cli import app
from molab.workspace import Workspace
from molab.workspace.domain import ImportOrigin

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_import_prints_imported_and_keeps_one_asset(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    workspace.add_project("portraits")
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
    assert again.output.startswith("imported\tc001\t")
    assert again.output.split()[-1] == imported.output.split()[-1]

    assets = workspace.project("portraits").assets.list()
    assert [asset.title for asset in assets] == ["c001"]
    assert isinstance(assets[0].origin, ImportOrigin)
    assert assets[0].ref.startswith("molab:asset/")

    info = CliRunner().invoke(app, ["asset", "info", assets[0].id, "-ws", root])
    assert info.exit_code == 0, info.output
    assert assets[0].ref in info.output
    assert "image/png" in info.output
    assert assets[0].content.digest in info.output
    assert "import" in info.output


def test_import_refuses_a_path_that_is_not_a_workspace(tmp_path: Path) -> None:
    source = tmp_path / "c001.png"
    source.write_bytes(_PNG)
    result = CliRunner().invoke(
        app,
        ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "No workspace found" in result.output
