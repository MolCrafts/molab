"""Scope-aware manifest scanning (``assets/scan.py``) — cost locks.

``test_asset_scan.py`` owns *what* each query returns. This module owns *how
much disk I/O* it costs: a scoped query reads its own scope's manifest and
nothing else, a full scan opens every manifest exactly once with no
``exists`` pre-probes, lineage scans the workspace once (not once per node),
and ``scope_dir_for`` is pure layout math that agrees with the server's
folder-walking resolver.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.assets import AssetScope, lineage, scan
from molexp.workspace.fs_local import LocalFileSystem
from tests.support.counting_fs import CountingFileSystem

MANIFEST = "assets.json"
P, E, R = 5, 4, 10  # projects x experiments x runs in the synthetic layout


def _record(asset_id: str, scope: dict, path: str = "out.dat") -> dict:
    return {
        "asset_id": asset_id,
        "name": asset_id,
        "kind": "artifact",
        "scope": scope,
        "path": path,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "content_hash": f"sha256:{asset_id}",
        "tags": {},
        "producer": None,
    }


def _write_manifest(scope_dir: Path, assets: dict) -> None:
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / MANIFEST).write_text(
        json.dumps({"schema_version": 1, "assets": assets}), encoding="utf-8"
    )


@pytest.fixture
def synth_root(tmp_path: Path) -> Path:
    """A PxExR layout written directly (no ``add_run``), one asset per scope."""
    root = tmp_path / "ws"
    _write_manifest(root, {"ws": _record("ws", {"kind": "workspace", "ids": []})})
    for p in range(P):
        pid = f"p{p}"
        pdir = root / "projects" / pid
        _write_manifest(pdir, {pid: _record(pid, {"kind": "project", "ids": [pid]})})
        for e in range(E):
            eid = f"e{e}"
            edir = pdir / "experiments" / eid
            aid = f"{pid}-{eid}"
            _write_manifest(edir, {aid: _record(aid, {"kind": "experiment", "ids": [pid, eid]})})
            for r in range(R):
                rid = f"r{r}"
                rdir = edir / "runs" / f"run-{rid}"
                aid = f"{pid}-{eid}-{rid}"
                _write_manifest(rdir, {aid: _record(aid, {"kind": "run", "ids": [pid, eid, rid]})})
    return root


@pytest.fixture
def counting() -> CountingFileSystem:
    return CountingFileSystem(LocalFileSystem())


def _manifests_read(fs: CountingFileSystem) -> int:
    return fs.for_basename(MANIFEST, "read_text")


class TestScopedScanCost:
    def test_run_scope_reads_exactly_one_manifest_and_no_probes(self, synth_root, counting):
        scope = AssetScope(kind="run", ids=("p0", "e0", "r0"))
        found = scan.scan_assets(synth_root, scope=scope, fs=counting)
        assert [a.asset_id for a in found] == ["p0-e0-r0"]
        assert _manifests_read(counting) == 1
        assert counting.probes() == 0, dict(counting.calls)

    def test_experiment_scope_recursive_walks_only_that_subtree(self, synth_root, counting):
        scope = AssetScope(kind="experiment", ids=("p1", "e2"))
        found = scan.scan_assets(synth_root, scope=scope, recursive=True, fs=counting)
        assert len(found) == 1 + R
        assert {a.scope.ids[:2] for a in found} == {("p1", "e2")}
        assert _manifests_read(counting) == 1 + R
        # One ``scandir`` on the ``runs/`` container answers both that it
        # exists and which entries are dirs — no probe of any kind. The rest
        # are the per-scope ``assets/`` listings (1 experiment + R runs).
        assert counting.calls["scandir"] == 1 + (1 + R)
        assert counting.probes() == 0, dict(counting.calls)

    def test_full_scan_opens_every_manifest_once_without_exists(self, synth_root, counting):
        found = scan.scan_assets(synth_root, fs=counting)
        n_scopes = 1 + P + P * E + P * E * R
        assert len(found) == n_scopes
        assert _manifests_read(counting) == n_scopes
        assert counting.probes() == 0, dict(counting.calls)
        # One ``scandir`` per container (``projects/`` + each ``experiments/``
        # + each ``runs/``) plus one per scope for its optional ``assets/``
        # dir. No per-entry call at any level, and no ``listdir`` left.
        assert counting.calls["scandir"] == (1 + P + P * E) + n_scopes
        assert counting.calls["listdir"] == 0

    def test_default_fs_is_the_same_walk(self, synth_root):
        via_default = scan.scan_assets(synth_root)
        via_fs = scan.scan_assets(str(synth_root), fs=LocalFileSystem())
        assert [a.asset_id for a in via_default] == [a.asset_id for a in via_fs]

    def test_loose_file_in_a_container_is_skipped(self, synth_root, counting):
        (synth_root / "projects" / ".DS_Store").write_text("junk")
        (synth_root / "projects" / "p0" / "experiments" / "e0" / "runs" / "notes.txt").write_text(
            "x"
        )
        found = scan.scan_assets(synth_root, fs=counting)
        assert len(found) == 1 + P + P * E + P * E * R


class TestMalformedScope:
    def test_missing_ids_yield_nothing_and_touch_nothing(self, synth_root, counting):
        assert (
            scan.scan_assets(
                synth_root, scope=AssetScope(kind="run", ids=("p0", "e0")), fs=counting
            )
            == []
        )
        assert counting.total() == 0

    @pytest.mark.parametrize("bad", ["../p0", "p0/e0", "", ".", ".."])
    def test_non_segment_ids_never_compose_a_path(self, synth_root, bad):
        assert scan.scope_dir_for(synth_root, AssetScope(kind="project", ids=(bad,))) is None


class TestScopeDirFor:
    def test_parity_with_server_resolver_on_real_folders(self, tmp_path):
        from molexp.server.routes._scope import resolve_scope_dir

        ws = Workspace(tmp_path / "lab", name="Lab")
        run = ws.add_project("Demo Proj").add_experiment("Base Line").add_run(params={"x": 1})
        exp = run.experiment
        for scope in (ws.scope, exp.project.scope, exp.scope, run.scope):
            assert scan.scope_dir_for(ws.root, scope) == str(resolve_scope_dir(ws, scope))

    def test_is_pure_path_math(self, synth_root, counting):
        scope = AssetScope(kind="run", ids=("p0", "e0", "r0"))
        assert scan.scope_dir_for(synth_root, scope, fs=counting) == str(
            synth_root / "projects" / "p0" / "experiments" / "e0" / "runs" / "run-r0"
        )
        # ``join`` is string math; nothing touches the disk.
        assert (
            counting.opens() + counting.stats() + counting.probes() + counting.calls["listdir"] == 0
        )


class TestPrescannedLookups:
    def test_get_asset_and_find_by_hash_do_no_io_with_assets(self, synth_root, counting):
        assets = scan.scan_assets(synth_root)
        counting.reset()
        hit = scan.get_asset(synth_root, "p2-e1-r3", fs=counting, assets=assets)
        assert hit is not None and hit.asset_id == "p2-e1-r3"
        by_hash = scan.find_by_content_hash(
            synth_root, "sha256:p2-e1-r3", fs=counting, assets=assets
        )
        assert by_hash is not None and by_hash.asset_id == "p2-e1-r3"
        assert scan.get_asset(synth_root, "nope", fs=counting, assets=assets) is None
        assert counting.total() == 0


def _seed_chain(tmp_path: Path, fs: CountingFileSystem) -> tuple[Workspace, str, str, str]:
    src = tmp_path / "raw.txt"
    src.write_bytes(b"raw\n")
    ws = Workspace(tmp_path / "lab", name="Lab", fs=fs)
    a = ws.data_assets.import_asset("a", src)
    run = ws.add_project("p").add_experiment("e").add_run()
    with run.start() as ctx:
        b = ctx.artifact.save("b.json", {"step": "b"}, consumed=[a])
        c = ctx.artifact.save("c.json", {"step": "c"}, consumed=[b])
    return ws, a.asset_id, b.asset_id, c.asset_id


class TestLineageCost:
    def test_ancestors_and_descendants_scan_manifests_once(self, tmp_path, counting):
        ws, a, b, c = _seed_chain(tmp_path, counting)
        n_scopes = 4  # workspace + project + experiment + run
        counting.reset()
        assert lineage.ancestors(ws, c) == {a, b}
        assert _manifests_read(counting) == n_scopes  # was (1 + depth) full scans
        counting.reset()
        assert lineage.descendants(ws, a) == {b, c}
        assert _manifests_read(counting) == n_scopes

    def test_prescanned_assets_make_lineage_free(self, tmp_path, counting):
        ws, a, b, c = _seed_chain(tmp_path, counting)
        assets = scan.scan_assets(ws.root, fs=counting)
        counting.reset()
        assert lineage.ancestors(ws, c, assets=assets) == {a, b}
        assert lineage.descendants(ws, a, assets=assets) == {b, c}
        assert counting.total() == 0


class TestAssetsViewRouting:
    def test_view_scans_through_the_folder_fs_and_only_its_scope(self, tmp_path, counting):
        ws, _a, b, _c = _seed_chain(tmp_path, counting)
        run = ws.project("p").experiment("e").list_runs()[0]
        counting.reset()
        listed = run.assets.list()
        assert b in {x.asset_id for x in listed}
        assert _manifests_read(counting) == 1  # the run's manifest, via the injected fs
        counting.reset()
        assert run.assets.get(b) is not None
        assert _manifests_read(counting) == 1
        assert run.assets.get("nope") is None


class TestSidecarResolution:
    def test_asset_has_sidecar_never_walks_the_folder_tree(self, tmp_path, monkeypatch):
        from molexp.server.preview import asset_has_sidecar

        ws = Workspace(tmp_path / "lab", name="Lab")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            asset = ctx.artifact.save("metrics.json", {"loss": 0.1})

        def _boom(*_a, **_k):
            raise AssertionError("folder walk must not be used to locate a scope dir")

        monkeypatch.setattr(ws, "get_project", _boom)
        assert asset_has_sidecar(ws, asset) is False
        sidecar = Path(run.run_dir) / asset.path.parent / "metrics.py"
        sidecar.write_text("def preview(path):\n    return path\n")
        assert asset_has_sidecar(ws, asset) is True
