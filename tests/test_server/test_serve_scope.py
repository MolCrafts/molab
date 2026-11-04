"""HTTP scope: listings and opens stop at the directory molab serve opened."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import (
    ServedWorkspace,
    set_served_workspaces,
    set_workspace_path_override,
)
from molab.workspace import Workspace
from molab.workspace.folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    WORKSPACE_RUN_KIND,
)


@pytest.mark.parametrize("entry", ["cli", "api"])
@pytest.mark.parametrize("named", [False, True])
def test_remote_display_uses_registry_name_without_changing_identity(
    monkeypatch, tmp_path, entry, named
):
    from molq import Molq

    from molab.cli.workspace.serve import _resolve_served
    from molab.server.routes.workspaces import _build_remote_served
    from molab.server.workspace_targets import WorkspaceTarget, WorkspaceTargetRegistry

    with Molq(registry=tmp_path / "labels.db") as mq:
        cluster = mq.clusters.register(name="Arrhenius", scheduler="shell")
        cluster_id = cluster.definition()["id"]
        registry_id = mq.rpc("molq.hello")["registry_id"]
        monkeypatch.setattr("molab.workspace.connection.get_client", lambda *_args: mq)
        targets = WorkspaceTargetRegistry(tmp_path / "targets.json")
        target = WorkspaceTarget(
            name="experiment-root",
            registry_id=registry_id,
            cluster_id=cluster_id,
            root_path="/lab/nve-drift",
        )
        targets.add(target)
        monkeypatch.setattr(
            "molab.server.deps.targets.get_workspace_target_registry", lambda: targets
        )
        spec = "@experiment-root" if named else f"{cluster_id}:/lab/nve-drift"
        served = (
            _resolve_served(spec, set())
            if entry == "cli"
            else _build_remote_served(name="experiment-root" if named else None, path=spec)
        )
        assert served.label == "Arrhenius:/lab/nve-drift"
        assert served.remote_target.cluster_id == cluster_id
        assert served.remote_target.registry_id == registry_id


@pytest.mark.parametrize("kind", ["AUTH_REQUIRED", "TRANSPORT_UNAVAILABLE"])
def test_remote_failure_is_shared_across_concurrent_browser_probes(monkeypatch, kind):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep
    from types import SimpleNamespace

    from molq import MolqError

    from molab.server.deps import resolution, workspace_state
    from molab.server.exceptions import RemoteWorkspaceUnreachableError

    workspace_state.reset_workspace_cache()
    calls = []
    clock = [100.0]
    monkeypatch.setattr(resolution, "monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(
        "molab.server.deps.served.resolve_served_remote_target",
        lambda _name: SimpleNamespace(root_path="/remote"),
    )
    monkeypatch.setattr(
        "molab.server.workspace_targets.target_to_filesystem_for_workspace_target",
        lambda _target: object(),
    )

    def failing_open(*_args, **_kwargs):
        calls.append(kind)
        sleep(0.02)
        raise MolqError(kind, "fixture failure")

    monkeypatch.setattr(resolution, "open_serve_root", failing_open)

    def probe(_index):
        with pytest.raises(RemoteWorkspaceUnreachableError):
            resolution._open_remote_workspace("remote", served_key="remote")

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(probe, range(8)))
        assert calls == [kind]
        clock[0] += 59
        probe(0)
        assert calls == [kind]
        clock[0] += 2
        probe(0)
        assert len(calls) == (1 if kind == "AUTH_REQUIRED" else 2)
        workspace_state.reset_workspace_cache()
        probe(0)
        assert len(calls) == (2 if kind == "AUTH_REQUIRED" else 3)
    finally:
        workspace_state.reset_workspace_cache()


@pytest.mark.parametrize("reason", ["needs_auth", "unreachable"])
def test_workspace_list_requests_otp_only_for_authentication_failure(monkeypatch, reason):
    from molab.server.exceptions import RemoteWorkspaceUnreachableError
    from molab.server.routes import workspaces

    def failing_open(_key):
        raise RemoteWorkspaceUnreachableError("remote", reason)

    monkeypatch.setattr(workspaces, "get_workspace_by_key", failing_open)
    row = workspaces._to_response(
        ServedWorkspace(key="remote", label="remote", is_remote=True), active_key="remote"
    )
    assert row.unreachable
    assert row.needsAuth is (reason == "needs_auth")


def test_active_remote_auth_failure_uses_the_served_key(monkeypatch):
    from molab.server.deps import resolution, workspace_state
    from molab.server.exceptions import RemoteWorkspaceUnreachableError

    set_served_workspaces(
        [
            ServedWorkspace(
                key="remote-descriptor", label="remote", is_remote=True, target_name="descriptor"
            )
        ]
    )
    workspace_state.set_active_workspace_descriptor("descriptor")

    def failing_open(identifier, *, served_key=None):
        raise RemoteWorkspaceUnreachableError(served_key or identifier, "needs_auth")

    monkeypatch.setattr(resolution, "_open_remote_workspace", failing_open)
    try:
        with pytest.raises(RemoteWorkspaceUnreachableError) as caught:
            resolution.get_active_workspace()
        assert caught.value.details["workspace"] == "remote-descriptor"
    finally:
        workspace_state.set_active_workspace_descriptor(None)
        set_served_workspaces([])


@pytest.fixture
def client_at(tmp_path: Path) -> Iterator[tuple[Workspace, object]]:
    """A lab plus a client factory bound to whatever directory the test serves."""
    ws = Workspace(tmp_path / "lab", name="lab")
    alpha = ws.add_project("alpha")
    experiment = alpha.add_experiment("baseline")
    run = experiment.add_run(params={"x": 1})
    beta = ws.add_project("beta")

    def open_at(directory: Path) -> TestClient:
        set_workspace_path_override(directory)
        return TestClient(create_app(serve_static=False))

    try:
        yield ws, alpha, experiment, run, beta, open_at
    finally:
        set_workspace_path_override(None)
        set_served_workspaces([])


class TestServeScopeHttp:
    def test_scope_kind_follows_the_served_directory(self, client_at: tuple) -> None:
        ws, alpha, experiment, run, _beta, open_at = client_at
        cases = (
            (Path(str(ws.root)), WORKSPACE_ROOT_KIND, ws.id),
            (Path(str(alpha.resolve())), WORKSPACE_PROJECT_KIND, alpha.id),
            (Path(str(experiment.resolve())), WORKSPACE_EXPERIMENT_KIND, experiment.id),
            (Path(str(run.resolve())), WORKSPACE_RUN_KIND, run.id),
        )
        for directory, kind, ident in cases:
            with open_at(directory) as client:
                response = client.get("/api/workspace/scope")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == kind
            assert body["id"] == ident

    def test_scoped_remote_project_opens_without_access_to_its_ancestors(
        self, client_at: tuple, tmp_path: Path
    ) -> None:
        from molq import Molq

        from molab.workspace.fs_cached import CachedRemoteFS
        from molab.workspace.fs_remote import RemoteFS
        from molab.workspace.scope import open_serve_root

        ws, project, experiment, _run, _beta, _open_at = client_at
        directory = str(project.resolve())
        with Molq(registry=tmp_path / "scoped-registry.db") as mq:
            cluster = mq.clusters.register(name="scoped", scheduler="shell")
            inner = RemoteFS(mq, cluster.name, directory)
            fs = CachedRemoteFS(inner, mirror_root=tmp_path / "mirror")
            opened = open_serve_root(directory, fs=fs)
            assert opened.kind == WORKSPACE_PROJECT_KIND
            assert opened.id == project.id
            assert opened.parent is None
            assert [item.id for item in opened.list_experiments()] == [experiment.id]
            with pytest.raises(PermissionError):
                inner.read_text(inner.join(ws.root, "index.md"))

    def test_served_project_lists_itself_and_hides_the_sibling(self, client_at: tuple) -> None:
        _ws, alpha, experiment, _run, beta, open_at = client_at
        with open_at(Path(str(alpha.resolve()))) as client:
            listed = client.get("/api/projects")
            assert listed.status_code == 200, listed.text
            assert [row["id"] for row in listed.json()] == [alpha.id]
            experiments = client.get(f"/api/projects/{alpha.id}/experiments")
            assert experiments.status_code == 200, experiments.text
            assert [row["id"] for row in experiments.json()] == [experiment.id]
            missing = client.get(f"/api/projects/{beta.id}")
            assert missing.status_code == 404

    def test_experiment_listing_does_not_load_run_records(self, client_at, monkeypatch):
        from molab.workspace.experiment import Experiment

        _ws, project, experiment, _run, _beta, open_at = client_at

        def unexpected_run_walk(_self):
            raise AssertionError("A shallow experiment list must not read runs")

        monkeypatch.setattr(Experiment, "list_runs", unexpected_run_walk)
        with open_at(Path(str(project.resolve()))) as client:
            response = client.get(f"/api/projects/{project.id}/experiments")
            assert response.status_code == 200, response.text
            assert [item["id"] for item in response.json()] == [experiment.id]
            assert response.json()[0]["runCount"] is None
            assert response.json()[0]["runs"] == []

    def test_parentless_project_lists_assets(self, client_at, tmp_path):
        _ws, project, _experiment, _run, _beta, open_at = client_at
        standalone = tmp_path / "standalone-project"
        shutil.copytree(Path(str(project.resolve())), standalone)
        with open_at(standalone) as client:
            response = client.get(f"/api/projects/{project.id}/assets")
            assert response.status_code == 200, response.text
            assert response.json() == []

    def test_parentless_project_lists_run_execution_state(self, client_at, tmp_path):
        _ws, project, experiment, run, _beta, open_at = client_at
        standalone = tmp_path / "standalone-with-runs"
        shutil.copytree(Path(str(project.resolve())), standalone)
        with open_at(standalone) as client:
            response = client.get(f"/api/projects/{project.id}/experiments/{experiment.id}/runs")
            assert response.status_code == 200, response.text
            assert [item["id"] for item in response.json()] == [run.id]

    def test_cached_remote_experiment_list_batches_workflow_reads(
        self, client_at, tmp_path, monkeypatch
    ):
        from molq import Molq

        from molab.server.deps.scope_root import ScopeRoot
        from molab.server.routes.experiment import list_experiments
        from molab.workspace.fs_cached import CachedRemoteFS
        from molab.workspace.fs_remote import RemoteFS
        from molab.workspace.scope import open_serve_root

        _ws, project, experiment, _run, _beta, _open_at = client_at
        directory = str(project.resolve())
        with Molq(registry=tmp_path / "batch-workflow.db") as mq:
            cluster = mq.clusters.register(name="batch", scheduler="shell")
            fs = CachedRemoteFS(
                RemoteFS(mq, cluster.name, directory), mirror_root=tmp_path / "mirror"
            )
            root = ScopeRoot(open_serve_root(directory, fs=fs))
            requested = []
            rpc = mq.rpc

            def record(method: str, **params: object):
                if method == "files.read_many":
                    requested.extend(params["paths"])
                return rpc(method, **params)

            monkeypatch.setattr(mq, "rpc", record)
            response = list_experiments(project.id, workspace=root)
            assert [item.id for item in response] == [experiment.id]
            assert requested == [str(experiment.resolve() / "workflow.ir.json")]

    def test_served_experiment_has_no_project_and_returns_its_run(self, client_at: tuple) -> None:
        _ws, alpha, experiment, run, _beta, open_at = client_at
        with open_at(Path(str(experiment.resolve()))) as client:
            projects = client.get("/api/projects")
            assert projects.status_code == 200, projects.text
            assert projects.json() == []
            detail = client.get(f"/api/projects/{alpha.id}/experiments/{experiment.id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["projectId"] == ""
            assert detail.json()["id"] == experiment.id
            got = client.get(f"/api/projects/-/experiments/-/runs/{run.id}")
            assert got.status_code == 200, got.text
            assert got.json()["id"] == run.id
            assert got.json()["projectId"] == ""
            assert got.json()["experimentId"] == experiment.id
            sibling = client.get("/api/projects/-/experiments/not-this")
            assert sibling.status_code == 404

    def test_served_run_get_accepts_omitted_ancestors(self, client_at: tuple) -> None:
        _ws, _alpha, _experiment, run, _beta, open_at = client_at
        with open_at(Path(str(run.resolve()))) as client:
            got = client.get(f"/api/projects/-/experiments/-/runs/{run.id}")
            assert got.status_code == 200, got.text
            body = got.json()
            assert body["id"] == run.id
            assert body["projectId"] == ""
            assert body["experimentId"] == ""
            rows = client.get("/api/workspace/runs")
            assert rows.status_code == 200, rows.text
            assert [item["id"] for item in rows.json()["runs"]] == [run.id]

    def test_workspace_still_lists_both_projects(self, client_at: tuple) -> None:
        ws, alpha, _experiment, _run, beta, open_at = client_at
        with open_at(Path(str(ws.root))) as client:
            listed = client.get("/api/projects")
        assert listed.status_code == 200, listed.text
        assert {row["id"] for row in listed.json()} == {alpha.id, beta.id}

    def test_open_outside_a_non_empty_served_set_is_forbidden(
        self, client_at: tuple, tmp_path: Path
    ) -> None:
        ws, _alpha, _experiment, _run, _beta, open_at = client_at
        outside = tmp_path / "outside"
        outside.mkdir()
        set_served_workspaces(
            [
                ServedWorkspace(
                    key="lab",
                    label=str(ws.root),
                    is_remote=False,
                    path=str(ws.root),
                )
            ]
        )
        with open_at(Path(str(ws.root))) as client:
            blocked = client.post(
                "/api/workspace/open",
                json={"kind": "local", "path": str(outside)},
            )
            assert blocked.status_code == 403, blocked.text
            allowed = client.post(
                "/api/workspace/open",
                json={"kind": "local", "path": str(ws.root)},
            )
            assert allowed.status_code == 200, allowed.text

    def test_parentless_project_serves_without_a_workspace(
        self, client_at: tuple, tmp_path: Path
    ) -> None:
        _ws, alpha, experiment, _run, _beta, open_at = client_at
        alone = tmp_path / "alone"
        shutil.copytree(alpha.resolve(), alone)
        with open_at(alone) as client:
            scope = client.get("/api/workspace/scope")
            assert scope.status_code == 200, scope.text
            assert scope.json()["kind"] == WORKSPACE_PROJECT_KIND
            assert scope.json()["id"] == alpha.id
            projects = client.get("/api/projects")
            assert [row["id"] for row in projects.json()] == [alpha.id]
            experiments = client.get(f"/api/projects/{alpha.id}/experiments")
            assert [row["id"] for row in experiments.json()] == [experiment.id]
            assert experiments.json()[0]["projectId"] == alpha.id
            # The copy keeps its project record; no workspace record is invented.
            assert "workspace.root" not in (alone / "index.md").read_text()


class TestScopedFind:
    """A served node resolves refs at or below itself, so sourced documents can be written."""

    def test_project_root_writes_a_sourced_document(self, client_at: tuple) -> None:
        _ws, alpha, experiment, run, _beta, open_at = client_at
        with open_at(Path(str(alpha.resolve()))) as client:
            for kind, ref in (
                ("project", f"molab:project/{alpha.id}"),
                ("experiment", f"molab:experiment/{experiment.id}"),
                ("run", f"molab:experiment/{experiment.id}/run/{run.id}"),
            ):
                response = client.post(
                    "/api/knowledge/doc",
                    json={
                        "name": f"From {kind}",
                        "cls": "Report",
                        "sources": [{"kind": kind, "ref": ref}],
                    },
                )
                assert response.status_code == 201, response.text

    def test_refs_outside_the_served_node_are_not_found(self, client_at: tuple) -> None:
        from molab.server.deps.scope_root import ScopeRoot
        from molab.workspace.errors import RefNotFoundError
        from molab.workspace.scope import open_serve_root

        _ws, alpha, experiment, run, beta, _open_at = client_at
        root = ScopeRoot(open_serve_root(Path(str(experiment.resolve()))))
        assert root.find(f"molab:experiment/{experiment.id}/run/{run.id}").id == run.id
        with pytest.raises(RefNotFoundError):
            root.find(f"molab:project/{beta.id}")
        with pytest.raises(RefNotFoundError):
            root.find(f"molab:project/{alpha.id}")
        run_root = ScopeRoot(open_serve_root(Path(str(run.resolve()))))
        assert run_root.find(f"molab:experiment/{experiment.id}/run/{run.id}").id == run.id
        with pytest.raises(RefNotFoundError):
            run_root.find(f"molab:experiment/{experiment.id}")


class TestScopedKnowledgeListing:
    """A served node lists the knowledge documents of itself and every host below it."""

    def test_project_root_lists_documents_below_it(self, client_at: tuple) -> None:
        from molab.knowledge import Note

        _ws, alpha, experiment, run, beta, open_at = client_at
        Note(alpha, "project note").write("# p\n")
        Note(experiment, "experiment note").write("# e\n")
        Note(run, "run note").write("# r\n")
        Note(beta, "other project").write("# b\n")
        with open_at(Path(str(alpha.resolve()))) as client:
            response = client.get("/api/knowledge")
        assert response.status_code == 200, response.text
        names = {row["name"] for row in response.json()["notes"]}
        assert {"project-note", "experiment-note", "run-note"} <= names
        assert "other-project" not in names
        assert all(not row["relPath"].endswith("index.md") for row in response.json()["notes"])


class TestScopedRecordHistory:
    def test_record_replacement_is_committed_at_the_workspace_root(self, client_at: tuple) -> None:
        import subprocess

        from molab.workspace.history import GitHistory

        ws, alpha, _experiment, _run, _beta, open_at = client_at
        assert GitHistory(str(ws.root)).init()
        with open_at(Path(str(alpha.resolve()))) as client:
            created = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Study",
                    "cls": "Delegation",
                    "sources": [{"kind": "project", "ref": f"molab:project/{alpha.id}"}],
                    "record": {"goal": "g", "scope": f"molab:project/{alpha.id}"},
                },
            )
            assert created.status_code == 201, created.text
            path = created.json()["relPath"]
            got = client.get("/api/knowledge/doc/record", params={"path": path}).json()
            replaced = client.patch(
                "/api/knowledge/doc/record",
                params={"path": path},
                json={"record": {**got["record"], "state": "waiting"}, "ifMatch": got["digest"]},
            )
            assert replaced.status_code == 200, replaced.text
        log = subprocess.run(
            ["git", "-C", str(ws.root), "log", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "knowledge.record_replaced" in log


class TestServedValidation:
    def _paper(self, host: object, name: str) -> None:
        folder = Path(str(host.resolve())) / "knowledges"  # type: ignore[attr-defined]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text(f"---\nclass: Literature\nname: {name}\n---\n")

    def test_workspace_root_reports_everything(self, client_at: tuple) -> None:
        ws, alpha, _experiment, _run, beta, open_at = client_at
        self._paper(alpha, "a")
        self._paper(beta, "b")
        with open_at(Path(str(ws.root))) as client:
            body = client.get("/api/workspace/validate").json()
        paths = {
            row["path"]
            for row in body["violations"]
            if row["rule"] == "knowledge.literature_metadata"
        }
        assert paths == {"projects/alpha/knowledges/a.md", "projects/beta/knowledges/b.md"}
        assert body["ok"] is True and body["warningCount"] >= 2

    def test_a_served_project_sees_only_itself(self, client_at: tuple) -> None:
        ws, alpha, _experiment, _run, beta, open_at = client_at
        self._paper(ws, "root")
        self._paper(alpha, "a")
        self._paper(beta, "b")
        with open_at(Path(str(alpha.resolve()))) as client:
            response = client.get("/api/workspace/validate")
        assert response.status_code == 200, response.text
        paths = {row["path"] for row in response.json()["violations"]}
        assert "knowledges/a.md" in paths
        assert not any("b.md" in path or "root.md" in path for path in paths)

    def test_errors_only_skips_warnings(self, client_at: tuple) -> None:
        ws, alpha, _experiment, _run, _beta, open_at = client_at
        self._paper(alpha, "a")
        with open_at(Path(str(ws.root))) as client:
            body = client.get("/api/workspace/validate", params={"errorsOnly": "true"}).json()
        assert body["warningCount"] == 0


class TestScopedContext:
    """``/api/workspace/context`` works from any served node and stays inside it."""

    def test_each_served_level_gets_its_own_subtree(self, client_at: tuple) -> None:
        ws, alpha, experiment, run, beta, open_at = client_at
        cases = (
            (Path(str(ws.root)), {alpha.id, beta.id}, 1),
            (Path(str(alpha.resolve())), {alpha.id}, 1),
            (Path(str(experiment.resolve())), set(), 1),
            (Path(str(run.resolve())), set(), 1),
        )
        for directory, projects, runs in cases:
            with open_at(directory) as client:
                response = client.get("/api/workspace/context")
            assert response.status_code == 200, (directory, response.text)
            body = response.json()
            assert {row["id"] for row in body["projects"]} == projects
            assert [row["runId"] for row in body["recentRuns"]] == [run.id] * runs
            assert body["workspace"]["root"] == str(directory)

    def test_ids_above_the_boundary_are_not_exposed(self, client_at: tuple) -> None:
        _ws, _alpha, experiment, run, _beta, open_at = client_at
        with open_at(Path(str(experiment.resolve()))) as client:
            body = client.get("/api/workspace/context").json()
        assert body["experiments"][0]["projectId"] == ""
        assert body["recentRuns"][0]["experimentId"] == experiment.id
        assert body["recentRuns"][0]["projectId"] == ""
        with open_at(Path(str(run.resolve()))) as client:
            body = client.get("/api/workspace/context").json()
        assert body["recentRuns"][0]["experimentId"] == ""


class TestKnowledgeEditHistory:
    def test_edits_meta_moves_and_deletes_are_committed(self, client_at: tuple) -> None:
        import subprocess

        from molab.workspace.history import GitHistory

        ws, _alpha, _experiment, _run, _beta, open_at = client_at
        assert GitHistory(str(ws.root)).init()
        with open_at(Path(str(ws.root))) as client:
            created = client.post("/api/knowledge/doc", json={"name": "Idea", "body": "# Idea\n"})
            path = created.json()["relPath"]
            assert (
                client.put(
                    "/api/knowledge/doc", params={"path": path}, json={"body": "# Idea v2\n"}
                ).status_code
                == 200
            )
            assert (
                client.patch(
                    "/api/knowledge/doc/meta", params={"path": path}, json={"status": "retracted"}
                ).status_code
                == 200
            )
            assert client.delete("/api/knowledge/doc", params={"path": path}).status_code == 200
        log = subprocess.run(
            ["git", "-C", str(ws.root), "log", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for event in ("knowledge.edited", "knowledge.meta_changed", "knowledge.deleted"):
            assert event in log, event
