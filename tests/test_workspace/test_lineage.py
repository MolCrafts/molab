"""Lineage walks a run's input asset ids. An import has no upstream."""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.assets import lineage

HELLO = b"hello\n"


def _lab(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "lab", name="Lab")


class TestLineageTraversal:
    def test_a_produced_asset_points_at_the_run_inputs(self, tmp_path: Path) -> None:
        src = tmp_path / "input.txt"
        src.write_bytes(b"raw\n")
        ws = _lab(tmp_path)
        project = ws.add_project("p")
        upstream = project.import_asset("input", src)
        run = project.add_experiment("e").add_run(inputs=(upstream.id,))
        with run.start() as ctx:
            mid = ctx.register({"x": 1}, title="mid.json")
        assert lineage.ancestors(ws, mid.id) == {upstream.id}
        assert lineage.descendants(ws, upstream.id) == {mid.id}

    def test_ancestors_and_descendants_trace_three_step_dag(self, tmp_path: Path) -> None:
        src = tmp_path / "raw.txt"
        src.write_bytes(b"raw\n")
        ws = _lab(tmp_path)
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        raw = project.import_asset("a", src)
        first = experiment.add_run(inputs=(raw.id,))
        with first.start() as ctx:
            mid = ctx.register({"step": "b"}, title="b.json")
        second = experiment.add_run(params={"n": 2}, inputs=(mid.id,))
        with second.start() as ctx:
            leaf = ctx.register({"step": "c"}, title="c.json")
        assert lineage.ancestors(ws, leaf.id) == {raw.id, mid.id}
        assert lineage.descendants(ws, raw.id) == {mid.id, leaf.id}

    def test_an_import_has_no_upstream(self, tmp_path: Path) -> None:
        src = tmp_path / "raw.txt"
        src.write_bytes(HELLO)
        other = tmp_path / "other.txt"
        other.write_bytes(b"other\n")
        ws = _lab(tmp_path)
        project = ws.add_project("p")
        raw = project.import_asset("a", src)
        child = project.import_asset("x", other)
        assert lineage.ancestors(ws, child.id) == set()
        assert lineage.descendants(ws, raw.id) == set()

    def test_a_self_input_terminates(self, tmp_path: Path) -> None:
        ws = _lab(tmp_path)
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            asset = ctx.register(b"x", title="solo")
        run._update_metadata(inputs=(asset.id,))
        assert lineage.ancestors(ws, asset.id) == set()
