"""Filesystem-call budgets over the synthetic workspace (``-m perf``).

Every test resets its counter right before the measured call and, on
failure, prints the full ``dict(fs.calls)`` so the regression is readable.
Budgets are the P1 targets from the loading/caching plan; the P3-only ones
(read-model snapshot, ETag 304) are ``xfail(strict=False)`` until that phase
lands. N / P / E below are the fixture's run / project / experiment counts.
"""

from __future__ import annotations

import pytest

from molexp.workspace import Workspace
from molexp.workspace.assets.scan import scan_assets
from molexp.workspace.events import WorkspaceEventLog
from tests.support.counting_fs import CountingFileSystem

from .conftest import AuditCollector, Scale, SynthLayout, make_client

pytestmark = pytest.mark.perf


def _calls(fs: CountingFileSystem) -> str:
    return f"fs calls: {dict(fs.calls)!r}"


# ── fixture sanity ─────────────────────────────────────────────────────────


class TestFixture:
    def test_fixture_parses_back(
        self, synth: SynthLayout, scale: Scale, plain_workspace: Workspace
    ) -> None:
        projects = plain_workspace.list_projects()
        assert len(projects) == scale.projects
        n_runs = 0
        statuses: set[str] = set()
        for project in projects:
            experiments = project.list_experiments()
            assert len(experiments) == scale.experiments
            for experiment in experiments:
                runs = experiment.list_runs()
                assert len(runs) == scale.runs
                for run in runs:
                    ops = run.read_ops()
                    assert len(ops.executions) == 2
                    statuses.add(ops.status.value)
                    assert run.metadata.config_hash
                n_runs += len(runs)
        assert n_runs == scale.n_runs == synth.n_runs
        assert statuses >= {"succeeded", "failed", "running", "pending", "cancelled"}
        assert len(scan_assets(synth.root)) == 2 * scale.n_runs
        from molexp.workspace.events import read_workspace_events

        assert len(read_workspace_events(synth.root, limit=5)) == 5

    def test_fixture_notes_parse_back(self, synth: SynthLayout, plain_workspace: Workspace) -> None:
        from molexp.workspace import Bundle

        names = {n.name for n in Bundle(synth.root).notes()}
        assert "lab-wiki" in names
        assert len(names) == len(synth.note_paths)


# ── GET /api/workspace/runs ────────────────────────────────────────────────


class TestWorkspaceRuns:
    def test_cold_budget(self, client, counting_fs: CountingFileSystem, scale: Scale) -> None:
        n, p, e = scale.n_runs, scale.projects, scale.n_experiments
        counting_fs.reset()
        resp = client.get("/api/workspace/runs", params={"limit": 2000})
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= min(n, 2000)
        # exact cold cost: root project index + P project entities + P experiment
        # indices + E experiment entities + (run.json + _ops/run.json) per run
        assert counting_fs.opens() <= 2 * n + 2 * p + e + 4, _calls(counting_fs)
        assert counting_fs.calls["is_dir"] == 0, _calls(counting_fs)
        assert counting_fs.calls["exists"] == 0, _calls(counting_fs)

    def test_warm_zero_opens(self, client, counting_fs: CountingFileSystem, scale: Scale) -> None:
        n, p, e = scale.n_runs, scale.projects, scale.n_experiments
        assert client.get("/api/workspace/runs", params={"limit": 2000}).status_code == 200
        counting_fs.reset()
        resp = client.get("/api/workspace/runs", params={"limit": 2000})
        assert resp.status_code == 200
        assert counting_fs.opens() == 0, _calls(counting_fs)
        # warm = stat-validated memo: run.json + _ops/run.json per run, plus the
        # project/experiment entity + index files
        assert counting_fs.stats() <= 2 * n + e + 2 * p + 2, _calls(counting_fs)

    def test_warm_zero_stats_and_304(self, client, counting_fs: CountingFileSystem) -> None:
        """A repeat poll validates against the read-model version, not the disk."""
        first = client.get("/api/workspace/runs", params={"limit": 2000})
        etag = first.headers.get("etag")
        assert etag, "no ETag header"
        counting_fs.reset()
        second = client.get(
            "/api/workspace/runs", params={"limit": 2000}, headers={"If-None-Match": etag}
        )
        assert second.status_code == 304
        assert counting_fs.total() == 0, _calls(counting_fs)


# ── run detail + experiment runs ───────────────────────────────────────────


class TestRunDetail:
    def test_cold_two_files(
        self, client, counting_fs: CountingFileSystem, synth: SynthLayout
    ) -> None:
        p, e, r = synth.first
        counting_fs.reset()
        resp = client.get(f"/api/projects/{p}/experiments/{e}/runs/{r}")
        assert resp.status_code == 200, resp.text
        # run.json + _ops/run.json (both named run.json), plus the project and
        # experiment entity files on the resolution chain (cold workspace).
        run_json_opens = sum(counting_fs.for_basename("run.json", m) for m in ("open", "read_text"))
        assert run_json_opens <= 2, _calls(counting_fs)
        assert counting_fs.opens() <= 4, _calls(counting_fs)
        assert counting_fs.calls["exists"] == 0, _calls(counting_fs)

    def test_warm_zero_opens(
        self, client, counting_fs: CountingFileSystem, synth: SynthLayout
    ) -> None:
        p, e, r = synth.first
        url = f"/api/projects/{p}/experiments/{e}/runs/{r}"
        assert client.get(url).status_code == 200
        counting_fs.reset()
        assert client.get(url).status_code == 200
        assert counting_fs.opens() == 0, _calls(counting_fs)
        assert counting_fs.stats() <= 2, _calls(counting_fs)


class TestExperimentRuns:
    def test_cold_touches_only_that_experiment(
        self, client, counting_fs: CountingFileSystem, synth: SynthLayout, scale: Scale
    ) -> None:
        p, e, _r = synth.first
        counting_fs.reset()
        resp = client.get(f"/api/projects/{p}/experiments/{e}/runs")
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == scale.runs
        own = f"/experiments/{e}/runs/"
        foreign = [
            path
            for name, path, _kw in counting_fs.log
            if name in ("open", "read_text", "read_bytes")
            and "/runs/run-" in path
            and own not in path
        ]
        assert not foreign, f"touched other experiments' runs: {foreign[:5]}"
        assert counting_fs.opens() <= 2 * scale.runs + 6, _calls(counting_fs)
        assert counting_fs.calls["exists"] == 0, _calls(counting_fs)


# ── assets ─────────────────────────────────────────────────────────────────


class TestAssets:
    def test_scoped_scan_reads_one_manifest(
        self, counting_workspace: Workspace, counting_fs: CountingFileSystem, synth: SynthLayout
    ) -> None:
        p, e, r = synth.first
        run = counting_workspace.get_project(p).get_experiment(e).get_run(r)
        counting_fs.reset()
        found = scan_assets(synth.root, scope=run.scope, fs=counting_fs)
        assert len(found) == 2
        assert counting_fs.for_basename("assets.json") <= 2, _calls(counting_fs)  # ≤ probe + read
        assert counting_fs.count("listdir", "scandir") <= 1, _calls(counting_fs)

    def test_run_files_route_opens_one_manifest(
        self, client, audit: AuditCollector, synth: SynthLayout
    ) -> None:
        p, e, r = synth.first
        with audit.collect():
            resp = client.get(f"/api/projects/{p}/experiments/{e}/runs/{r}/files")
        assert resp.status_code == 200, resp.text
        assert audit.opens_of("assets.json") <= 1, (
            f"assets.json opened {audit.opens_of('assets.json')} times"
        )

    def test_lineage_single_scan(
        self, client, audit: AuditCollector, synth: SynthLayout, scale: Scale
    ) -> None:
        # the last asset has the longest ancestor chain (cross-run inputs)
        asset_id = synth.asset_ids[-1]
        scopes = 1 + scale.projects + scale.n_experiments + scale.n_runs
        with audit.collect():
            resp = client.get(f"/api/assets/{asset_id}/lineage")
        assert resp.status_code == 200, resp.text
        assert audit.opens_of("assets.json") <= scopes, (
            f"assets.json opened {audit.opens_of('assets.json')} times (one full scan = {scopes})"
        )

    def test_workspace_info_counts_without_full_scan(
        self, client, audit: AuditCollector, scale: Scale
    ) -> None:
        with audit.collect():
            resp = client.get("/api/workspace/info")
        assert resp.status_code == 200
        # P1: still one full scan (1+P+E+N manifests); P3 makes it zero.
        assert (
            audit.opens_of("assets.json") <= 1 + scale.projects + scale.n_experiments + scale.n_runs
        )


# ── knowledge ──────────────────────────────────────────────────────────────


class TestKnowledge:
    def test_list_never_enters_run_internals(
        self, client, audit: AuditCollector, synth: SynthLayout
    ) -> None:
        with audit.collect():
            resp = client.get("/api/knowledge")
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= len(synth.note_paths)
        for fragment in ("/executions", "/artifacts", "/metrics"):
            assert audit.listings_under(fragment) == 0, (
                f"walk listed {audit.listings_under(fragment)} dirs under {fragment!r}"
            )

    def test_list_walks_each_directory_once(
        self, client, audit: AuditCollector, synth: SynthLayout
    ) -> None:
        """One listing per visited directory — never a second pass over the tree.

        ``GET /api/knowledge`` used to walk the tree twice (notes, then
        references) and probe every entry's type; it is now a single
        ``scandir``-driven walk. Listings are counted at the OS level, so a
        regression that reintroduced a per-entry probe would show up here even
        if it bypassed the ``FileSystem`` seam.
        """
        with audit.collect():
            resp = client.get("/api/knowledge")
        assert resp.status_code == 200, resp.text
        visited = len(audit.listings)
        scale = synth.scale
        # Scope dirs (workspace + projects + experiments + runs) plus their
        # ``projects/`` / ``experiments/`` / ``runs/`` containers and the
        # mounted notes — one listing each, not one per pass per entry.
        budget = 3 * (1 + scale.projects + scale.n_experiments + scale.n_runs)
        assert visited <= budget, f"{visited} directory listings (budget {budget})"

    def test_search_get_writes_nothing(self, client, synth: SynthLayout) -> None:
        index_json = synth.root / "index.json"
        index_md = synth.root / "INDEX.md"
        before = (index_json.exists(), index_md.exists())
        resp = client.get("/api/knowledge/search", params={"q": "loss plateau"})
        assert resp.status_code == 200, resp.text
        assert (index_json.exists(), index_md.exists()) == before, (
            "GET /knowledge/search wrote index files"
        )


# ── events ─────────────────────────────────────────────────────────────────


class TestEvents:
    def test_limit_bounds_materialized_rows(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = {"n": 0}
        original = WorkspaceEventLog._row_to_event

        def counting(row):
            seen["n"] += 1
            return original(row)

        monkeypatch.setattr(WorkspaceEventLog, "_row_to_event", staticmethod(counting))
        resp = client.get("/api/events", params={"limit": 50})
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 50
        assert 0 < seen["n"] <= 50, f"materialized {seen['n']} rows for limit=50"


# ── P3-only budgets ────────────────────────────────────────────────────────


class TestReadModel:
    def test_sweep_unchanged_is_stat_only(
        self, counting_workspace: Workspace, counting_fs: CountingFileSystem, scale: Scale
    ) -> None:
        from molexp.services.workspace_read_model import (
            WorkspaceReadModel,  # type: ignore[import-not-found]
        )

        model = WorkspaceReadModel(counting_workspace)
        model.runs()
        counting_fs.reset()
        model.refresh("runs", block=True)
        assert counting_fs.opens() == 0, _calls(counting_fs)
        assert counting_fs.stats() <= 2 * scale.n_runs + scale.n_experiments + scale.projects + 2

    def test_context_warm_zero_io(
        self, counting_workspace: Workspace, counting_fs: CountingFileSystem
    ) -> None:
        client = make_client(counting_workspace)
        assert client.get("/api/workspace/context").status_code == 200
        counting_fs.reset()
        assert client.get("/api/workspace/context").status_code == 200
        assert counting_fs.total() == 0, _calls(counting_fs)
