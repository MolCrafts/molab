"""``molexp.workspace.assets.lineage`` — ancestors/descendants over the asset DAG.

Owns lineage traversal (``ancestors`` / ``descendants``) over the upstream edge
data — ``Producer.inputs`` for legacy ``DataAsset`` imports and
``input_entity_ids`` for v2 ``Artifact`` emissions (recorded via
``emit_artifact(..., consumed=...)``).  Asset content-hash correctness is
owned by ``test_ids`` (``compute_content_hash``) and ``test_asset_scan``,
not here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from molexp.workspace import Workspace
from molexp.workspace.assets import ArtifactAsset, AssetManifest, AssetScope, Producer, lineage


class TestConsumedInputs:
    def test_consumed_inputs_recorded_on_artifact(self, tmp_path):
        src = tmp_path / "input.txt"
        src.write_bytes(b"raw\n")

        ws = Workspace(tmp_path / "lab", name="Lab")
        upstream = ws.data_assets.import_asset("input", src)

        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            mid = ctx.emit_artifact({"x": 1}, name="mid.json", consumed=[upstream.asset_id])
            final = ctx.emit_artifact(
                {"y": 2}, name="final.json", consumed=[upstream.asset_id, mid.id]
            )

        assert mid.input_entity_ids == (upstream.asset_id,)
        assert final.input_entity_ids == (upstream.asset_id, mid.id)


class TestLineageTraversal:
    def test_ancestors_and_descendants_trace_three_step_dag(self, tmp_path):
        src = tmp_path / "raw.txt"
        src.write_bytes(b"raw\n")

        ws = Workspace(tmp_path / "lab", name="Lab")
        a = ws.data_assets.import_asset("a", src)

        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            b = ctx.emit_artifact({"step": "b"}, name="b.json", consumed=[a.asset_id])
            c = ctx.emit_artifact({"step": "c"}, name="c.json", consumed=[b.id])

        assert lineage.ancestors(ws, c.id) == {a.asset_id, b.id}
        assert lineage.descendants(ws, a.asset_id) == {b.id, c.id}

    def test_self_loop_terminates(self, tmp_path):
        # Defensive: if a producer somehow lists its own asset_id, traversal
        # must terminate via the visited set.
        ws = Workspace(tmp_path / "lab", name="Lab")
        run = ws.add_project("p").add_experiment("e").add_run()

        now = datetime.now()
        scope = AssetScope(kind="run", ids=(run.experiment.project.id, run.experiment.id, run.id))
        asset = ArtifactAsset(
            asset_id="solo",
            name="solo.json",
            scope=scope,
            path=Path("artifacts/solo.json"),
            created_at=now,
            updated_at=now,
            producer=Producer(inputs=("solo",)),
        )
        AssetManifest(Path(run.run_dir)).register(asset)

        assert lineage.ancestors(ws, "solo") == set()  # self-loop excluded
