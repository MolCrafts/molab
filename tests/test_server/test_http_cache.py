"""Conditional GETs on the list routes (P3-3d).

A validator is only useful if it is *sound* — it must change whenever the body
would, and must not change when the body would not. Both directions are
asserted here, plus the header-parsing corners (``W/`` prefix, comma lists,
``*``) that decide whether a real browser's revalidation works at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.server.http_cache import etag_matches, weak_etag
from molexp.workspace import Workspace
from molexp.workspace.run_ops import RunStatus


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="lab")
    experiment = ws.add_project("proj").add_experiment("exp")
    for i in range(2):
        experiment.add_run(params={"i": i})
    return ws


@pytest.fixture
def client(workspace: Workspace):
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: workspace
    with TestClient(app) as c:
        yield c


class TestEtagHelpers:
    def test_weak_etag_is_weak_and_includes_the_parts(self) -> None:
        assert weak_etag("runs", 42) == 'W/"runs-42"'
        assert weak_etag("runs", 42, "proj", None, "") == 'W/"runs-42-proj"'

    @pytest.mark.parametrize(
        "header",
        ['W/"runs-1"', '"runs-1"', "*", 'W/"other", W/"runs-1"', ' W/"runs-1" '],
    )
    def test_if_none_match_forms_all_select_the_tag(self, header: str) -> None:
        assert etag_matches(header, 'W/"runs-1"')

    @pytest.mark.parametrize("header", [None, "", 'W/"runs-2"', '"nope"'])
    def test_non_matching_headers_do_not_select(self, header: str | None) -> None:
        assert not etag_matches(header, 'W/"runs-1"')


class TestRunsListValidator:
    def test_repeat_request_is_304(self, client: TestClient) -> None:
        first = client.get("/api/workspace/runs")
        assert first.status_code == 200
        etag = first.headers["etag"]
        assert first.headers["cache-control"] == "private, no-cache"

        second = client.get("/api/workspace/runs", headers={"If-None-Match": etag})
        assert second.status_code == 304
        assert second.content == b""

    def test_validator_changes_immediately_after_a_mutation(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """A write through the API invalidates the view, so the next read is fresh."""
        first = client.get("/api/workspace/runs")
        run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
        assert (
            client.post(f"/api/projects/proj/experiments/exp/runs/{run.id}/cancel").status_code
            == 200
        )

        second = client.get("/api/workspace/runs", headers={"If-None-Match": first.headers["etag"]})
        assert second.status_code == 200
        assert second.headers["etag"] != first.headers["etag"]
        statuses = {r["id"]: r["status"] for r in second.json()["runs"]}
        assert statuses[run.id] == "cancelled"

    def test_external_write_is_seen_once_the_snapshot_ages_out(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """A write by another process is picked up by the staleness sweep.

        Deliberately not instant: a poll serves the current snapshot and
        revalidates behind it, so the window is ``runs_max_age`` wide.
        """
        import time

        first = client.get("/api/workspace/runs")
        run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
        other = Workspace(root=workspace.resolve())
        other_run = other.get_project("proj").get_experiment("exp").get_run(run.id)
        other_run.update_ops(lambda s: s.model_copy(update={"status": RunStatus.FAILED}))

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            resp = client.get("/api/workspace/runs")
            statuses = {r["id"]: r["status"] for r in resp.json()["runs"]}
            if statuses[run.id] == "failed":
                assert resp.headers["etag"] != first.headers["etag"]
                return
            time.sleep(0.2)
        pytest.fail("external status change never became visible")

    def test_different_filters_get_different_validators(self, client: TestClient) -> None:
        plain = client.get("/api/workspace/runs").headers["etag"]
        filtered = client.get("/api/workspace/runs", params={"status": "pending"}).headers["etag"]
        assert plain != filtered

    def test_offset_pages_without_changing_total(self, client: TestClient) -> None:
        body = client.get("/api/workspace/runs", params={"limit": 1, "offset": 0}).json()
        assert len(body["runs"]) == 1
        assert body["total"] == 2, "total counts matches, not the page"
        assert body["truncated"] is True

        page2 = client.get("/api/workspace/runs", params={"limit": 1, "offset": 1}).json()
        assert len(page2["runs"]) == 1
        assert page2["runs"][0]["id"] != body["runs"][0]["id"]
        assert page2["truncated"] is False


class TestOtherValidators:
    @pytest.mark.parametrize(
        "url",
        [
            "/api/workspace/info",
            "/api/workspace/context",
            "/api/workspace/copilot",
            "/api/assets",
            "/api/knowledge",
            "/api/events",
        ],
    )
    def test_route_round_trips_a_304(self, client: TestClient, url: str) -> None:
        first = client.get(url)
        assert first.status_code == 200, first.text
        etag = first.headers.get("etag")
        assert etag, f"{url} sent no ETag"
        assert client.get(url, headers={"If-None-Match": etag}).status_code == 304

    def test_experiment_detail_has_a_per_experiment_validator(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """Activity in one experiment must not invalidate another's page."""
        other = workspace.get_project("proj").add_experiment("quiet")
        other.add_run(params={"i": 0})

        url_a = "/api/projects/proj/experiments/exp"
        url_b = "/api/projects/proj/experiments/quiet"
        etag_b = client.get(url_b).headers["etag"]
        etag_a = client.get(url_a).headers["etag"]

        run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
        client.post(f"/api/projects/proj/experiments/exp/runs/{run.id}/cancel")

        # ``exp`` changed, ``quiet`` did not: only ``exp``'s page revalidates.
        assert client.get(url_a, headers={"If-None-Match": etag_a}).status_code == 200
        assert client.get(url_b, headers={"If-None-Match": etag_b}).status_code == 304

    def test_info_reports_view_versions(self, client: TestClient) -> None:
        versions = client.get("/api/workspace/info").json()["versions"]
        assert set(versions) == {"runs", "assets", "knowledge"}
