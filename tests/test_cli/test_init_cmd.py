"""``molab init`` writes a workspace a later command can open."""

from __future__ import annotations

import json
import shutil

import pytest
import typer
from typer.testing import CliRunner

from molab import frontmatter
from molab.cli.init_cmd import init
from molab.workspace import Workspace
from molab.workspace.errors import UnmigratedLayoutError
from molab.workspace.run import compute_run_definition_hash
from tests.support.records import read_index_block, read_record, write_record


@pytest.fixture
def app():
    cli = typer.Typer()
    cli.command("init")(init)
    cli.command("noop")(lambda: None)
    return cli


def test_init_writes_the_workspace_marker(tmp_path, app):
    target = tmp_path / "lab"
    result = CliRunner().invoke(app, ["init", str(target), "--name", "lab"])
    assert result.exit_code == 0, result.output
    marker = read_record(target)
    assert marker["name"] == "lab"
    assert marker["type"] == "workspace.root"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_init_starts_the_history(tmp_path, app):
    target = tmp_path / "lab"
    CliRunner().invoke(app, ["init", str(target)])
    assert (target / ".git").is_dir()
    assert "**/assets/*/payload" in (target / ".gitignore").read_text()


def test_init_is_idempotent_and_keeps_the_id(tmp_path, app):
    target = tmp_path / "lab"
    CliRunner().invoke(app, ["init", str(target)])
    first = read_record(target)["id"]
    CliRunner().invoke(app, ["init", str(target)])
    assert read_record(target)["id"] == first


def test_init_adopts_an_existing_directory_and_keeps_its_notes(tmp_path, app):
    target = tmp_path / "lab"
    target.mkdir()
    (target / "index.md").write_text("plain notes\n", encoding="utf-8")
    (target / "datasets").mkdir()
    (target / "datasets" / "a.txt").write_text("a", encoding="utf-8")

    result = CliRunner().invoke(app, ["init", str(target), "--name", "lab"])

    assert result.exit_code == 0, result.output
    record = read_record(target)
    assert record["type"] == "workspace.root"
    assert record["name"] == "lab"
    assert (
        frontmatter.split((target / "index.md").read_text(encoding="utf-8"))[1] == "plain notes\n"
    )
    assert (target / "datasets" / "a.txt").read_text(encoding="utf-8") == "a"
    assert Workspace.enclosing_root(target / "datasets" / "a.txt") == target


def test_init_rewrites_a_legacy_tree_without_keeping_the_old_files(tmp_path, app):
    target = tmp_path / "lab"
    project = target / "projects" / "polymer-tg"
    experiment = project / "experiments" / "cool-schedule"
    run = experiment / "runs" / "dp=5"
    bare = experiment / "runs" / "other"
    for path in (run, bare, project / "experiments" / "__pycache__", experiment / "scratch"):
        path.mkdir(parents=True)
    (target / "index.md").write_text("# The lab\n\nNotes stay.\n", encoding="utf-8")
    (target / "workspace.json").write_text(
        json.dumps(
            {
                "id": "lab",
                "name": "lab",
                "type": "workspace.root",
                "created_at": "2020-01-02T03:04:05",
                "targets": [],
                "schema_version": 5,
                "removed_field": True,
            }
        ),
        encoding="utf-8",
    )
    (project / "project.json").write_text(
        json.dumps(
            {
                "id": "p1",
                "name": "Polymer Tg",
                "description": "glass",
                "type": "workspace.project",
            }
        ),
        encoding="utf-8",
    )
    (project / "meta.json").write_text("{}\n", encoding="utf-8")
    (experiment / "experiment.json").write_text(
        json.dumps(
            {
                "id": "e1",
                "name": "Cool",
                "revision_id": "rev-1",
                "parameter_space": {"dp": 25},
                "legacy_workflow": {"path": "old"},
            }
        ),
        encoding="utf-8",
    )
    (experiment / "notes.txt").write_text("keep", encoding="utf-8")
    (experiment / "scratch" / "meta.json").write_text("{}\n", encoding="utf-8")
    (run / "run.json").write_text(
        json.dumps({"id": "r1", "parameters": {"dp": 5}, "experiment_revision_id": "stale"}),
        encoding="utf-8",
    )
    (run / "density.csv").write_text("1\n", encoding="utf-8")
    with pytest.raises(UnmigratedLayoutError):
        Workspace(target)

    result = CliRunner().invoke(app, ["init", str(target)])

    assert result.exit_code == 0, result.output
    root = read_record(target)
    assert root["id"] == "lab"
    assert root["name"] == "lab"
    assert str(root["created_at"]).startswith("2020-01-02T03:04:05")
    assert frontmatter.split((target / "index.md").read_text(encoding="utf-8"))[1] == (
        "# The lab\n\nNotes stay.\n"
    )
    assert read_record(project)["id"] == "p1"
    assert read_record(project)["description"] == "glass"
    assert read_record(experiment)["revision_id"] == "rev-1"
    assert read_record(experiment)["parameter_space"] == {"dp": 25}
    assert "legacy_workflow" not in read_record(experiment)
    assert read_record(run)["id"] == "r1"
    assert read_record(run)["parameters"] == {"dp": 5}
    assert read_record(run)["experiment_revision_id"] == "rev-1"
    assert read_record(run)["definition_hash"] == compute_run_definition_hash(
        experiment_revision_id="rev-1",
        parameters={"dp": 5},
        input_asset_ids=(),
    )
    assert read_record(bare)["type"] == "workspace.run"
    assert not (project / "experiments" / "__pycache__" / "index.md").exists()
    for directory in (target, project, experiment, run):
        for name in ("workspace.json", "project.json", "experiment.json", "run.json", "meta.json"):
            assert not (directory / name).exists()
    assert (experiment / "scratch" / "meta.json").read_text(encoding="utf-8") == "{}\n"
    assert (run / "density.csv").read_text(encoding="utf-8") == "1\n"
    assert (experiment / "notes.txt").read_text(encoding="utf-8") == "keep"
    children = read_index_block(target)["children"]
    assert children[0]["path"] == "projects/polymer-tg/index.md"
    assert children[0]["id"] == "p1"
    ws = Workspace(target)
    assert [item.name for item in ws.list_projects()] == ["Polymer Tg"]
    assert Workspace.enclosing_root(run / "density.csv") == target

    write_record(target, read_record(target), index={"children": [{"name": "stale"}]})
    again = CliRunner().invoke(app, ["init", str(target)])
    assert again.exit_code == 0, again.output
    assert read_record(target)["id"] == "lab"
    assert read_record(project)["id"] == "p1"
    assert read_index_block(target)["children"][0]["id"] == "p1"


def test_init_replaces_an_unreadable_meta_file(tmp_path, app):
    target = tmp_path / "lab"
    target.mkdir()
    (target / "workspace.json").write_text("[]", encoding="utf-8")
    (target / "index.md").write_text("kept\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["init", str(target), "--name", "lab"])

    assert result.exit_code == 0, result.output
    assert not (target / "workspace.json").exists()
    assert read_record(target)["type"] == "workspace.root"
    assert read_record(target)["name"] == "lab"
    assert frontmatter.split((target / "index.md").read_text(encoding="utf-8"))[1] == "kept\n"
