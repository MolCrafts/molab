"""An approval decision must reach the *workspace* change bus, not only the
approvals ping.

The bridge exists so a browser watches one stream instead of holding a second
``EventSource`` open purely for approvals. It was dead on arrival:
``notify_approvals_changed`` republished as ``kind="approval"`` only when
handed a workspace root, and not one of its call sites passed one. Nothing
failed — the dedicated approvals stream masked it — which is exactly why the
contract is pinned here rather than left to the UI to discover.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from molexp.harness.schemas import ApprovalRequest
from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.workspace import Workspace


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="lab")
    ws.add_project("proj").add_experiment("exp").add_run(params={"i": 0})
    return ws


class _StubCurateTask:
    """The slice of ``CurateTask`` the decision route actually touches.

    A real task owns a gateway and a live asyncio driver; none of that shapes
    the notification contract under test, and standing it up would make this
    test about task machinery instead.
    """

    def __init__(self, run: Any, request: ApprovalRequest) -> None:
        self.run = run
        self.run_id = run.id
        self.task_id = "curate-stub"
        self.status = "waiting_approval"
        self.pending_requests = [request]
        self.resumed = False
        self.rejected: str | None = None

    def resume(self) -> None:
        self.resumed = True
        self.status = "running"

    def mark_rejected(self, reason: str) -> None:
        self.rejected = reason
        self.status = "failed"

    def cancel(self) -> None:
        """The registry cancels every task on server shutdown."""
        self.status = "cancelled"

    async def await_finished(self) -> None:
        """Shutdown awaits each cancelled task; this one is already done."""
        return


def _register(workspace: Workspace) -> tuple[_StubCurateTask, ApprovalRequest]:
    from molexp.server.deps.curate_runtime import get_curate_runtime

    run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
    request = ApprovalRequest(
        id="req-1",
        intent="overwrite",
        reason="needs a human",
        triggered_by_policy="test",
        created_at=datetime.now(tz=UTC),
    )
    task = _StubCurateTask(run, request)
    registry = get_curate_runtime()
    # Reaching past ``create()`` on purpose: it spawns the background driver.
    registry._by_workspace.setdefault(str(workspace.root), {})[task.task_id] = task
    return task, request


@pytest.fixture
def client(workspace: Workspace):
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: workspace
    with TestClient(app) as c:
        yield c


class TestApprovalReachesTheWorkspaceBus:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("action", "expect_resumed"), [("approve", True), ("reject", False)])
    async def test_a_decision_publishes_an_approval_change_for_this_workspace(
        self, client: TestClient, workspace: Workspace, action: str, expect_resumed: bool
    ) -> None:
        from molexp.services.workspace_notify import subscribe_workspace_changes

        task, request = _register(workspace)
        bus_root = str(workspace.resolve())

        stream = subscribe_workspace_changes(bus_root)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)  # let the subscription register

        response = await asyncio.to_thread(
            client.post,
            f"/api/approvals/curate/{task.task_id}/decisions",
            json={"requestId": request.id, "action": action},
        )
        assert response.status_code == 200, response.text

        change = await asyncio.wait_for(waiter, timeout=5)
        assert change.kind == "approval"
        assert change.root == bus_root, (
            "subscribers match the root by exact string; a mismatched spelling delivers to nobody"
        )
        assert task.resumed is expect_resumed


class TestRootDerivation:
    def test_workspace_root_of_matches_the_streams_subscription_key(
        self, workspace: Workspace
    ) -> None:
        """A task driver holds only a ``Run``; it must still name the same root."""
        from molexp.services.workspace_notify import workspace_root_of

        run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
        assert workspace_root_of(run) == str(workspace.resolve())

    def test_an_unreachable_run_yields_none_instead_of_raising(self) -> None:
        """A failed lookup must not take down a decision already on disk."""
        from molexp.services.workspace_notify import workspace_root_of

        assert workspace_root_of(object()) is None
