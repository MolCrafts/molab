"""The run file tree is bounded in depth and in entries per directory.

A run that wrote 100k frames into one directory used to produce a 100k-node
response built from an unbounded recursive walk. These tests pin the caps and,
just as importantly, that the default depth still reaches the files the UI
feeds into plugin discovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.server.routes.run import DEFAULT_RUN_FILES_DEPTH


def _touch(run, rel: str, text: str = "x") -> None:
    target = Path(str(run.run_dir)) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _find(nodes: list[dict], rel: str) -> dict | None:
    """Depth-first search for a node by ``relPath``."""
    for node in nodes:
        if node["relPath"] == rel:
            return node
        hit = _find(node.get("children") or [], rel)
        if hit is not None:
            return hit
    return None


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/files"


class TestEntryCap:
    def test_wide_directory_is_capped_and_reports_the_real_count(self, client, run, url):
        for i in range(120):
            _touch(run, f"artifacts/frame_{i:04d}.dat")

        body = client.get(url, params={"max_entries": 25}).json()
        artifacts = _find(body["nodes"], "artifacts")
        assert artifacts is not None
        assert len(artifacts["children"]) == 25
        assert artifacts["entryCount"] == 120
        assert artifacts["truncated"] is True

    def test_directory_within_the_cap_is_not_marked_truncated(self, client, run, url):
        _touch(run, "artifacts/only.dat")
        body = client.get(url, params={"max_entries": 25}).json()
        artifacts = _find(body["nodes"], "artifacts")
        assert artifacts["truncated"] is False
        assert artifacts["entryCount"] == 1

    def test_entry_cap_above_the_ceiling_is_rejected(self, client, url):
        assert client.get(url, params={"max_entries": 99_999}).status_code == 422


class TestDepthCap:
    def test_depth_cap_stops_the_walk_and_marks_the_boundary(self, client, run, url):
        _touch(run, "a/b/c/d/deep.txt")
        body = client.get(url, params={"max_depth": 2}).json()

        b_dir = _find(body["nodes"], "a/b")
        assert b_dir is not None
        assert b_dir["children"] == []
        assert b_dir["truncated"] is True
        assert _find(body["nodes"], "a/b/c/d/deep.txt") is None

    def test_default_depth_reaches_execution_logs(self, client, run, url):
        """Regression guard for plugin discovery.

        ``flattenFileNodes`` feeds this tree to the UI's file-type discovery,
        and ``executions/<id>/logs/<name>.log`` sits at depth 4. A shallower
        default would make those files silently undiscoverable rather than
        merely unlisted.
        """
        _touch(run, "executions/exec-1/logs/run.log")
        _touch(run, "executions/exec-1/jobs/abc-123/manifest.json")

        body = client.get(url).json()
        assert _find(body["nodes"], "executions/exec-1/logs/run.log") is not None
        assert _find(body["nodes"], "executions/exec-1/jobs/abc-123/manifest.json") is not None
        assert DEFAULT_RUN_FILES_DEPTH >= 5


class TestNodeShape:
    def test_files_carry_size_and_folders_do_not(self, client, run, url):
        _touch(run, "artifacts/one.dat", "hello")
        body = client.get(url).json()
        f = _find(body["nodes"], "artifacts/one.dat")
        d = _find(body["nodes"], "artifacts")
        assert f["type"] == "file" and f["size"] == 5
        assert d["type"] == "folder" and d["size"] is None

    def test_dirs_sort_before_files(self, client, run, url):
        _touch(run, "zzz_dir/inner.txt")
        _touch(run, "aaa_file.txt")
        body = client.get(url).json()
        types = [n["type"] for n in body["nodes"]]
        assert types == sorted(types, key=lambda t: t == "file")
