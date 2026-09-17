"""Tests for workspace JSON schema versioning.

Writes stamp the current version, so a file records the build that made it.
Reads do **not** gate on it: while the format is still moving the tree
routinely holds files an older build wrote, and refusing to open a workspace
over a version stamp costs more than the mismatch does.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION


def _seed_workspace(root) -> Workspace:
    ws = Workspace(root=root, name="Lab")
    proj = ws.add_project("p")
    exp = proj.add_experiment("e", params={"lr": 1e-3})
    run = exp.add_run()
    with run.start() as ctx:
        ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
    return ws


def _every_entity_json(workspace_root) -> list:
    root = Path(workspace_root)
    out = []
    out.append(root / "workspace.json")
    for proj in (root / "projects").iterdir():
        out.append(proj / "project.json")
        for exp in (proj / "experiments").iterdir():
            out.append(exp / "experiment.json")
            for run in (exp / "runs").iterdir():
                out.append(run / "run.json")
                exec_root = run / "executions"
                if exec_root.exists():
                    for ex in exec_root.iterdir():
                        if ex.is_dir():
                            out.append(ex / "execution.json")
    return [p for p in out if p.exists()]


class TestSchemaVersionEmitted:
    def test_every_entity_json_carries_schema_version(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        targets = _every_entity_json(ws.root)
        assert targets, "test seed produced no entity JSON files"

        for path in targets:
            with open(path) as fh:  # noqa: PTH123
                data = json.load(fh)
            assert "schema_version" in data, f"missing schema_version: {path}"
            assert data["schema_version"] == MOLAB_SCHEMA_VERSION


class TestMissingSchemaAccepted:
    def test_workspace_without_schema_version_loads(self, tmp_path):
        root = tmp_path / "ws_v0"
        root.mkdir()
        (root / "workspace.json").write_text(
            json.dumps(
                {
                    "id": "ws_v0",
                    "name": "Lab",
                    "created_at": "2024-01-01T00:00:00",
                    "targets": [],
                }
            )
        )

        assert Workspace.load(root).name == "Lab"


class TestOtherSchemaAccepted:
    def test_workspace_future_schema_loads(self, tmp_path):
        root = tmp_path / "ws_future"
        root.mkdir()
        (root / "workspace.json").write_text(
            json.dumps(
                {
                    "schema_version": MOLAB_SCHEMA_VERSION + 99,
                    "id": "ws_future",
                    "name": "From Tomorrow",
                    "created_at": "2099-01-01T00:00:00",
                    "targets": [],
                }
            )
        )
        assert Workspace.load(root).name == "From Tomorrow"

    def test_workspace_older_schema_loads(self, tmp_path):
        # The real case: `lab` on disk is schema 2 while the build writes 3.
        root = tmp_path / "ws_old"
        root.mkdir()
        (root / "workspace.json").write_text(
            json.dumps(
                {
                    "schema_version": MOLAB_SCHEMA_VERSION - 1,
                    "id": "ws_old",
                    "name": "Yesterday",
                    "created_at": "2020-01-01T00:00:00",
                    "targets": [],
                }
            )
        )
        assert Workspace.load(root).name == "Yesterday"
