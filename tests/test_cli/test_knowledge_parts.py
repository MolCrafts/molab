"""``molab knowledge parts`` lists a run's images. It does not write a Report."""

from __future__ import annotations

import base64
from pathlib import Path

from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.workspace import Workspace

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _lab_with_hair(tmp_path: Path) -> tuple[Workspace, str]:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        image = ctx.get_dir("work") / "hair.png"
        image.write_bytes(_PNG)
        ctx.register(image, title="hair.png", mime="image/png", tags={"part": "hair"})
    return workspace, run.id


def test_parts_prints_the_image(tmp_path: Path) -> None:
    workspace, run_id = _lab_with_hair(tmp_path)

    listed = CliRunner().invoke(knowledge_app, ["parts", run_id, "--path", str(workspace.root)])
    assert listed.exit_code == 0, listed.output
    assert "hair\tmolab:asset/" in listed.output
    assert not list(Path(str(workspace.root)).rglob("knowledges/*.md"))


def test_parts_exits_when_the_path_is_not_a_workspace(tmp_path: Path) -> None:
    result = CliRunner().invoke(knowledge_app, ["parts", "missing", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "not a molab workspace" in result.output
