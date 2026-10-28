"""``molab init`` writes a workspace a later command can open."""

from __future__ import annotations

import shutil

import pytest
import typer
from typer.testing import CliRunner

from molab.cli.init_cmd import init
from tests.support.records import read_record


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
