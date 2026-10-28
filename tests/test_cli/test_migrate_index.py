"""``molab migrate index`` — fold v5 ``<kind>.json`` / ``meta.json`` records into ``index.md``.

The v5 fixture is a tree the current code wrote, turned back into the JSON
layout: each record becomes ``<kind>.json`` (schema 5) and each ``index.md``
keeps only its narrative, un-fenced. Migration must rebuild the same records,
keep every narrative byte, remove the JSON, leave every run's
``definition_hash`` alone, be idempotent, and write nothing on a dry run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from molab import frontmatter
from molab.cli import app
from molab.cli.migrate_cmd import migrate_index
from molab.workspace import Workspace
from molab.workspace.validate import validate_workspace

_KIND_FILE = {
    "workspace.root": "workspace.json",
    "workspace.project": "project.json",
    "workspace.experiment": "experiment.json",
    "workspace.run": "run.json",
}


def _v6_lab(root: Path) -> dict[str, str]:
    """A small current workspace; returns run id → definition_hash."""
    ws = Workspace(root, name="lab")
    ws.materialize()
    ws.write_index("# Lab\n\nSee [alpha](projects/alpha/index.md).\n")
    project = ws.add_project("alpha")
    project.write_index("# Alpha\n")
    experiment = project.add_experiment("sweep", params={"lr": 1e-3})
    experiment.write_index("# Sweep\n\nnotes: on\n")
    runs = [experiment.add_run(params={"seed": seed, "switch": "on"}) for seed in (0, 1)]
    with runs[0].start() as ctx:
        ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
    mount = Path(str(project.resolve())) / "researcher"
    mount.mkdir()
    (mount / "index.md").write_text(
        frontmatter.dump({"type": "agent.session", "created_at": "2026-01-01T00:00:00"}, "hi\n")
    )
    return {run.id: run.metadata.definition_hash for run in runs}


def _downgrade(root: Path) -> dict[str, str]:
    """Rewrite every record as v5 JSON; returns path → narrative body kept."""
    bodies: dict[str, str] = {}
    for index in sorted(root.rglob("index.md")):
        if ".molab" in index.parts or "knowledges" in index.parts:
            continue
        meta, body = frontmatter.split(index.read_text(encoding="utf-8"))
        meta.pop("index", None)
        kind = str(meta.get("type", ""))
        payload = {**meta, "schema_version": 5}
        name = _KIND_FILE.get(kind, "meta.json")
        if name == "meta.json":
            payload.pop("schema_version")
        (index.parent / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if body:
            index.write_text(body, encoding="utf-8")
            bodies[str(index.relative_to(root))] = body
        else:
            index.unlink()
    return bodies


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }


class TestMigrateIndex:
    def test_a_v5_tree_becomes_index_md_records(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        hashes = _v6_lab(root)
        bodies = _downgrade(root)
        assert (root / "workspace.json").is_file()

        report = migrate_index(root)

        assert not report.failed
        assert not [p for p in root.rglob("*.json") if p.name in _KIND_FILE.values()]
        assert not list(root.rglob("meta.json"))
        for rel, body in bodies.items():
            assert frontmatter.split((root / rel).read_text(encoding="utf-8"))[1] == body
        ws = Workspace(root)
        experiment = ws.get_project("alpha").get_experiment("sweep")
        assert {run.id: run.metadata.definition_hash for run in experiment.list_runs()} == hashes
        assert [e.id for e in experiment.list_runs()[0].executions] == ["e01"]
        mount, _ = frontmatter.split((root / "projects/alpha/researcher/index.md").read_text())
        assert mount["type"] == "agent.session"
        # The legacy agent mount survives the migration untouched; the layout
        # law calls it a stray (D90), and nothing else is wrong.
        errors = [(v.rule, v.path) for v in validate_workspace(root).errors]
        assert errors == [("layout.stray", "projects/alpha/researcher")]
        assert report.synced == 5

    def test_it_is_idempotent(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        _v6_lab(root)
        _downgrade(root)
        migrate_index(root)
        before = _tree(root)

        again = migrate_index(root)

        assert again.planned == []
        assert again.written == []
        assert _tree(root) == before

    def test_a_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        _v6_lab(root)
        _downgrade(root)
        before = _tree(root)

        report = migrate_index(root, dry_run=True)

        assert report.dry_run
        assert {rel for rel, _legacy in report.planned} >= {
            ".",
            "projects/alpha",
            "projects/alpha/experiments/sweep",
            "projects/alpha/researcher",
        }
        assert _tree(root) == before

    def test_the_cli_reports_and_refuses_a_non_workspace(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        _v6_lab(root)
        _downgrade(root)

        dry = CliRunner().invoke(app, ["migrate", "index", str(root), "--dry-run"])
        assert dry.exit_code == 0, dry.output
        assert "DRY-RUN" in dry.output
        assert "workspace.json -> index.md" in dry.output

        done = CliRunner().invoke(app, ["migrate", "index", str(root)])
        assert done.exit_code == 0, done.output
        assert "records written" in done.output

        bare = tmp_path / "bare"
        bare.mkdir()
        refused = CliRunner().invoke(app, ["migrate", "index", str(bare)])
        assert refused.exit_code == 2

    def test_a_record_that_fails_its_model_is_kept_and_reported(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        _v6_lab(root)
        _downgrade(root)
        bad = root / "projects" / "alpha" / "project.json"
        bad.write_text(json.dumps({"name": "no id"}), encoding="utf-8")

        report = migrate_index(root)

        assert [rel for rel, _error in report.failed] == ["projects/alpha"]
        assert bad.is_file()


class TestIndexSync:
    def test_sync_rebuilds_a_hand_edited_tree(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        _v6_lab(root)
        project_index = root / "projects" / "alpha" / "index.md"
        meta, body = frontmatter.split(project_index.read_text())
        meta["index"] = {"children": [], "notes": [{"path": "knowledges/a.md"}]}
        project_index.write_text(frontmatter.dump(meta, body))
        assert not validate_workspace(root).ok

        result = CliRunner().invoke(app, ["index", "sync", "-ws", str(root)])

        assert result.exit_code == 0, result.output
        errors = [(v.rule, v.path) for v in validate_workspace(root).errors]
        assert errors == [("layout.stray", "projects/alpha/researcher")]
        meta, _ = frontmatter.split(project_index.read_text())
        assert cast("dict[str, object]", meta["index"])["notes"] == [{"path": "knowledges/a.md"}]
