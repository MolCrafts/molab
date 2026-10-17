"""Lineage walks origin ids. It does not parse ``molab:`` references."""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.assets import lineage
from molab.workspace.history import AgentRef

HELLO = b"hello\n"
ACTOR = AgentRef(id="t", type="system")


def _lab(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "lab", name="Lab")


class TestConsumedInputs:
    def test_consumed_inputs_recorded_on_artifact(self, tmp_path: Path) -> None:
        src = tmp_path / "input.txt"
        src.write_bytes(b"raw\n")
        ws = _lab(tmp_path)
        upstream = ws.data_assets.import_asset("input", src)
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            mid = ctx.emit_artifact({"x": 1}, name="mid.json", consumed=[upstream.id])
            final = ctx.emit_artifact({"y": 2}, name="final.json", consumed=[upstream.id, mid.id])
        assert mid.input_entity_ids == (upstream.id,)
        assert final.input_entity_ids == (upstream.id, mid.id)


class TestLineageTraversal:
    def test_promoted_asset_points_at_its_artifact(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        project = ws.add_project("p")
        run = project.add_experiment("e").add_run()
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"{}", name="model.json")
        asset, _version = project.assets.promote(artifact, created_by=ACTOR)
        assert lineage.ancestors(ws, asset.id) == {artifact.id}
        assert asset.id in lineage.descendants(ws, artifact.id)

    def test_ancestors_and_descendants_trace_three_step_dag(self, tmp_path: Path) -> None:
        src = tmp_path / "raw.txt"
        src.write_bytes(b"raw\n")
        ws = _lab(tmp_path)
        raw = ws.data_assets.import_asset("a", src)
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            mid = ctx.emit_artifact({"step": "b"}, name="b.json", consumed=[raw.id])
            leaf = ctx.emit_artifact({"step": "c"}, name="c.json", consumed=[mid.id])
        assert lineage.ancestors(ws, leaf.id) == {raw.id, mid.id}
        assert lineage.descendants(ws, raw.id) == {mid.id, leaf.id}

    def test_import_input_ids_are_ancestors(self, tmp_path: Path) -> None:
        src = tmp_path / "raw.txt"
        src.write_bytes(HELLO)
        ws = _lab(tmp_path)
        raw = ws.data_assets.import_asset("a", src)
        child = ws.data_assets.import_asset("x", src, action="copy", consumed=[raw.id])
        assert lineage.ancestors(ws, child.id) == {raw.id}

    def test_self_loop_terminates(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        record = Path(ws.root) / "assets" / "solo"
        (record / "versions").mkdir(parents=True)
        (record / "asset.json").write_text(
            json.dumps(
                {
                    "schema_version": 5,
                    "id": "solo",
                    "title": "solo",
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "t", "type": "system"},
                    "tags": {},
                }
            ),
            encoding="utf-8",
        )
        (record / "versions" / "v001.json").write_text(
            json.dumps(
                {
                    "schema_version": 5,
                    "id": "solo-v",
                    "asset_id": "solo",
                    "version": 1,
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "t", "type": "system"},
                    "origin": {
                        "kind": "import",
                        "uri": "/tmp/solo",
                        "action": "reference",
                        "location": None,
                        "input_ids": ["solo"],
                    },
                    "content": None,
                }
            ),
            encoding="utf-8",
        )
        assert lineage.ancestors(ws, "solo") == set()
