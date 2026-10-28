"""Tests for workspace schema versioning.

Writes stamp the current version, so a file records the build that made it.
Reads do **not** gate on it: while the format is still moving the tree
routinely holds files an older build wrote, and refusing to open a workspace
over a version stamp costs more than the mismatch does.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab import frontmatter
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


def _every_record(workspace_root) -> list:
    root = Path(workspace_root)
    out = []
    out.append(root / "index.md")
    for proj in (root / "projects").iterdir():
        out.append(proj / "index.md")
        for exp in (proj / "experiments").iterdir():
            out.append(exp / "index.md")
            for run in (exp / "runs").iterdir():
                out.append(run / "index.md")
                exec_root = run / "executions"
                if exec_root.exists():
                    for ex in exec_root.iterdir():
                        if ex.is_dir():
                            out.append(ex / "execution.json")
    return [p for p in out if p.exists()]


def _payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return frontmatter.split(text)[0]


def _write_root_record(root: Path, canonical: dict) -> None:
    root.mkdir()
    (root / "index.md").write_text(frontmatter.dump(canonical, ""), encoding="utf-8")


class TestSchemaVersionEmitted:
    def test_current_version_is_6(self):
        # D88: entity records moved from <kind>.json into index.md frontmatter (5 → 6).
        assert MOLAB_SCHEMA_VERSION == 6

    def test_every_record_carries_schema_version(self, tmp_path):
        ws = _seed_workspace(tmp_path / "lab")
        targets = _every_record(ws.root)
        assert targets, "test seed produced no records"

        for path in targets:
            data = _payload(path)
            assert "schema_version" in data, f"missing schema_version: {path}"
            assert data["schema_version"] == MOLAB_SCHEMA_VERSION


class TestMissingSchemaAccepted:
    def test_workspace_without_schema_version_loads(self, tmp_path):
        root = tmp_path / "ws_v0"
        _write_root_record(
            root,
            {
                "type": "workspace.root",
                "id": "ws_v0",
                "name": "Lab",
                "created_at": "2024-01-01T00:00:00",
                "targets": [],
            },
        )

        assert Workspace.load(root).name == "Lab"


class TestOtherSchemaAccepted:
    def test_workspace_future_schema_loads(self, tmp_path):
        root = tmp_path / "ws_future"
        _write_root_record(
            root,
            {
                "type": "workspace.root",
                "schema_version": MOLAB_SCHEMA_VERSION + 99,
                "id": "ws_future",
                "name": "From Tomorrow",
                "created_at": "2099-01-01T00:00:00",
                "targets": [],
            },
        )
        assert Workspace.load(root).name == "From Tomorrow"

    def test_workspace_older_schema_loads(self, tmp_path):
        # The real case: `lab` on disk is one schema behind the version this build writes.
        root = tmp_path / "ws_old"
        _write_root_record(
            root,
            {
                "type": "workspace.root",
                "schema_version": MOLAB_SCHEMA_VERSION - 1,
                "id": "ws_old",
                "name": "Yesterday",
                "created_at": "2020-01-01T00:00:00",
                "targets": [],
            },
        )
        assert Workspace.load(root).name == "Yesterday"
