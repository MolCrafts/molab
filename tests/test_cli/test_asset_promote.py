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


def test_import_same_title_new_bytes_keeps_the_id(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    workspace.add_project("portraits")
    source = tmp_path / "c001.png"
    source.write_bytes(_PNG)
    root = str(workspace.root)
    first = CliRunner().invoke(
        app, ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", root]
    )
    assert first.exit_code == 0, first.output
    asset_id = first.output.split()[-1]
    source.write_bytes(_PNG + b"\n")

    again = CliRunner().invoke(
        app, ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", root]
    )

    assert again.exit_code == 0, again.output
    assert again.output.startswith("replaced\tc001\t")
    assert again.output.split()[-1] == asset_id
    assert [asset.id for asset in workspace.project("portraits").assets.list()] == [asset_id]


def test_list_prints_the_full_id_and_info_accepts_the_slot(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        asset = ctx.register(b"old\n", title="network.data")
    root = str(workspace.root)
    slot = next(
        path.relative_to(Path(root)).as_posix() for path in Path(root).rglob("asset.json")
    ).removesuffix("/asset.json")

    listed = CliRunner().invoke(app, ["asset", "list", "-ws", root])
    assert listed.exit_code == 0, listed.output
    assert asset.id in listed.output
    assert f"{asset.id[:12]}..." not in listed.output

    info = CliRunner().invoke(app, ["asset", "info", slot, "-ws", root])
    assert info.exit_code == 0, info.output
    assert asset.id in info.output
    assert slot in info.output

    by_ref = CliRunner().invoke(app, ["asset", "info", asset.ref, "-ws", root])
    assert by_ref.exit_code == 0, by_ref.output
    assert asset.content.digest in by_ref.output

    lineage = CliRunner().invoke(app, ["asset", "lineage", slot, "-ws", root])
    assert lineage.exit_code == 0, lineage.output
    assert "ancestors" in lineage.output


def test_replace_prints_the_same_id(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        asset = ctx.register(b"old\n", title="network.data")
    source = tmp_path / "network.data"
    source.write_bytes(b"new\n")
    root = str(workspace.root)

    replaced = CliRunner().invoke(app, ["asset", "replace", asset.id, str(source), "-ws", root])

    assert replaced.exit_code == 0, replaced.output
    assert replaced.output.startswith(f"replaced\tnetwork.data\t{asset.id}\t")
    info = CliRunner().invoke(app, ["asset", "info", asset.id, "-ws", root])
    assert info.exit_code == 0, info.output
    assert "assets/" in info.output
    assert asset.content.digest not in info.output


def test_import_refuses_a_path_that_is_not_a_workspace(tmp_path: Path) -> None:
    source = tmp_path / "c001.png"
    source.write_bytes(_PNG)
    result = CliRunner().invoke(
        app,
        ["asset", "import", "c001", str(source), "--project", "portraits", "-ws", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "No workspace found" in result.output
