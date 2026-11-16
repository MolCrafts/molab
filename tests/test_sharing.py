"""Sharing authorization, transactional revocation, and publication boundaries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from molab.sharing.models import (
    BeginPublication,
    PublicationBatch,
    PublishedExperiment,
    PublishedProject,
    PublishedRun,
    ScalarPoint,
)
from molab.sharing.store import SharingError, SharingStore


@pytest.fixture
def sharing(tmp_path):
    store = SharingStore(tmp_path / "control", local_state_confirmed=True)
    alice = store.provision_principal("cluster", "alice-subject", "Alice")
    bob = store.provision_principal("cluster", "bob-subject", "Bob")
    eve = store.provision_principal("cluster", "eve-subject", "Eve")
    source, token = store.provision_source(alice.id, "cluster-a", 1001)
    return store, alice, bob, eve, source, token


def publish(
    store, token, *, project_id="p-a", base_version=None, run_id="run-1", experiment_id="exp-1"
):
    draft = store.begin_publication(
        token,
        BeginPublication(
            workspace_id="workspace-a",
            project=PublishedProject(id=project_id, name="Published project"),
            base_version=base_version,
        ),
    )
    batch = PublicationBatch(
        experiments=[PublishedExperiment(id=experiment_id, name="Selected experiment")],
        runs=[
            PublishedRun(
                id=run_id,
                experiment_id=experiment_id,
                name="Selected run",
                status="succeeded",
                metrics={"energy": [ScalarPoint(value=-1.2, step=1)]},
            )
        ],
    )
    store.add_batch(token, draft["version_id"], 0, batch)
    store.commit_publication(token, draft["version_id"])
    return draft


def test_viewer_is_project_scoped_and_revoked_immediately(sharing):
    store, alice, bob, eve, _, token = sharing
    a = publish(store, token)
    b = publish(store, token, project_id="p-b")
    invite = store.invite(alice.id, a["project_id"], bob.id)
    assert store.list_projects(bob.id)["items"] == []
    with pytest.raises(SharingError, match="Invitation not found"):
        store.respond(eve.id, invite["id"], accept=True)
    store.respond(bob.id, invite["id"], accept=True)
    assert [p["id"] for p in store.list_projects(bob.id)["items"]] == [a["project_id"]]
    assert (
        store.metrics(bob.id, a["project_id"], "exp-1", "run-1")["metrics"]["energy"][0]["value"]
        == -1.2
    )
    with pytest.raises(SharingError) as forbidden:
        store.invite(bob.id, a["project_id"], eve.id)
    assert forbidden.value.status == 403
    with pytest.raises(SharingError) as hidden:
        store.get_project(bob.id, b["project_id"])
    assert hidden.value.status == 404
    pending = store.invite(alice.id, a["project_id"], bob.id)
    store.revoke_member(alice.id, a["project_id"], bob.id)
    with pytest.raises(SharingError):
        store.get_project(bob.id, a["project_id"])
    with pytest.raises(SharingError):
        store.respond(bob.id, pending["id"], accept=True)


def test_concurrent_accept_has_one_grant_and_one_success(sharing):
    store, alice, bob, _, _, token = sharing
    project = publish(store, token)
    invitation = store.invite(alice.id, project["project_id"], bob.id)

    def accept():
        try:
            store.respond(bob.id, invitation["id"], accept=True)
            return "accepted"
        except SharingError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: accept(), range(2)))
    assert sorted(map(str, outcomes)) == ["409", "accepted"]
    assert len(store.members(alice.id, project["project_id"])["members"]) == 1


def test_partial_publication_and_conflicting_versions_are_not_visible(sharing):
    store, alice, _, _, _, token = sharing
    first = publish(store, token)
    body = BeginPublication(
        workspace_id="workspace-a",
        project=PublishedProject(id="p-a", name="New name"),
        base_version=first["version_id"],
    )
    next_version = store.begin_publication(token, body)
    stale = store.begin_publication(token, body)
    batch = PublicationBatch(experiments=[PublishedExperiment(id="exp-2", name="Next experiment")])
    store.add_batch(token, next_version["version_id"], 0, batch)
    store.add_batch(token, next_version["version_id"], 0, batch)
    with pytest.raises(SharingError, match="Batch content changed"):
        store.add_batch(token, next_version["version_id"], 0, PublicationBatch())
    assert store.get_project(alice.id, first["project_id"])["version_id"] == first["version_id"]
    store.commit_publication(token, next_version["version_id"])
    with pytest.raises(SharingError, match="base version"):
        store.commit_publication(token, stale["version_id"])
    store.commit_publication(token, first["version_id"])
    assert (
        store.get_project(alice.id, first["project_id"])["version_id"] == next_version["version_id"]
    )


def test_stop_prevents_inflight_refresh_and_retry_reactivation(sharing):
    store, alice, bob, _, _, token = sharing
    first = publish(store, token)
    invite = store.invite(alice.id, first["project_id"], bob.id)
    store.respond(bob.id, invite["id"], accept=True)
    draft = store.begin_publication(
        token,
        BeginPublication(
            workspace_id="workspace-a",
            project=PublishedProject(id="p-a", name="P"),
            base_version=first["version_id"],
        ),
    )
    store.stop_publication(alice.id, first["project_id"])
    with pytest.raises(SharingError):
        store.commit_publication(token, draft["version_id"])
    store.commit_publication(token, first["version_id"])
    assert store.get_project(alice.id, first["project_id"])["active"] is False
    with pytest.raises(SharingError, match="owner confirmation"):
        store.begin_publication(
            token,
            BeginPublication(
                workspace_id="workspace-a",
                project=PublishedProject(id="p-a", name="P"),
                base_version=first["version_id"],
            ),
        )
    assert store.list_projects(bob.id)["items"] == []


def test_run_identity_includes_its_experiment(sharing):
    store, alice, _, _, _, token = sharing
    draft = store.begin_publication(
        token, BeginPublication(workspace_id="w", project=PublishedProject(id="p", name="P"))
    )
    batch = PublicationBatch(
        experiments=[PublishedExperiment(id=e, name=e) for e in ("e1", "e2")],
        runs=[
            PublishedRun(
                id="same-id", experiment_id=e, name=e, status="pending", parameters={"x": i}
            )
            for i, e in enumerate(("e1", "e2"))
        ],
    )
    store.add_batch(token, draft["version_id"], 0, batch)
    store.commit_publication(token, draft["version_id"])
    page = store.objects(alice.id, draft["project_id"], "run")
    assert page["total"] == 2
    assert [r["parameters"]["x"] for r in page["items"]] == [0, 1]


def test_source_scope_identity_lifecycle_and_owner_disable(sharing):
    store, alice, bob, _, source, token = sharing
    project = publish(store, token)
    _, bob_token = store.provision_source(bob.id, "cluster-a", 1002)
    with pytest.raises(SharingError):
        store.add_batch(bob_token, project["version_id"], 0, PublicationBatch())
    with pytest.raises(SharingError, match="bound"):
        store.provision_source(bob.id, "cluster-a", 1001)
    assert store.provision_principal("cluster", "alice-subject", "Renamed").id == alice.id
    assert store.provision_principal("other-provider", "alice-subject", "Alice").id != alice.id
    invite = store.invite(alice.id, project["project_id"], bob.id)
    store.respond(bob.id, invite["id"], accept=True)
    store.disable_source(source)
    with pytest.raises(SharingError):
        store.source_identity(token)
    store.disable_principal(alice.id)
    assert store.list_projects(bob.id)["items"] == []
    with pytest.raises(SharingError):
        store.get_project(bob.id, project["project_id"])


def test_unpublished_parent_and_secret_fields_are_rejected(sharing):
    store, _, _, _, _, token = sharing
    draft = store.begin_publication(
        token, BeginPublication(workspace_id="w", project=PublishedProject(id="p", name="P"))
    )
    store.add_batch(
        token,
        draft["version_id"],
        0,
        PublicationBatch(
            runs=[PublishedRun(id="r", experiment_id="missing", name="R", status="pending")]
        ),
    )
    with pytest.raises(SharingError, match="experiment"):
        store.commit_publication(token, draft["version_id"])
    with pytest.raises(ValidationError):
        PublishedProject(id="p", name="P", config={"secret": "credential"})
    for value in (float("nan"), float("inf"), True, "3.0"):
        with pytest.raises(ValidationError):
            ScalarPoint(value=value)


def test_state_storage_and_version_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="confirmed"):
        SharingStore(tmp_path / "state", local_state_confirmed=False)
    directory = tmp_path / "public"
    directory.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="0700"):
        SharingStore(directory, local_state_confirmed=True)
    link = tmp_path / "link"
    link.symlink_to(directory)
    with pytest.raises(ValueError, match="symlink"):
        SharingStore(link, local_state_confirmed=True)
    writable = tmp_path / "replaceable"
    writable.mkdir(mode=0o777)
    writable.chmod(0o777)
    with pytest.raises(ValueError, match="ancestors"):
        SharingStore(writable / "private", local_state_confirmed=True)


def test_failed_grant_transaction_does_not_leave_an_audit_record(sharing, monkeypatch):
    store, alice, bob, _, _, token = sharing
    project = publish(store, token)
    invitation = store.invite(alice.id, project["project_id"], bob.id)

    def fail_audit(*args: object):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "_audit", fail_audit)
    with pytest.raises(OSError):
        store.respond(bob.id, invitation["id"], accept=True)
    assert store.list_projects(bob.id)["items"] == []
    assert store.invitations(bob.id)[0]["status"] == "pending"


def test_viewer_can_leave_after_publication_is_stopped(sharing):
    store, alice, bob, _, _, token = sharing
    project = publish(store, token)
    invitation = store.invite(alice.id, project["project_id"], bob.id)
    store.respond(bob.id, invitation["id"], accept=True)
    store.stop_publication(alice.id, project["project_id"])
    store.revoke_member(bob.id, project["project_id"], bob.id)
    assert store.members(alice.id, project["project_id"])["members"] == []


def test_expired_invite_cannot_grant_access_and_can_be_reissued(sharing):
    store, alice, bob, _, _, token = sharing
    project = publish(store, token)
    invite = store.invite(alice.id, project["project_id"], bob.id)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE invitations SET expires_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(days=1)).isoformat(), invite["id"]),
        )
    with pytest.raises(SharingError) as expired:
        store.respond(bob.id, invite["id"], accept=True)
    assert expired.value.status == 410
    store.respond(bob.id, invite["id"], accept=False)
    assert store.invitations(bob.id)[0]["status"] == "declined"
    replacement = store.invite(alice.id, project["project_id"], bob.id)
    assert replacement["id"] != invite["id"]
    assert store.list_projects(bob.id)["total"] == 0


def test_pending_drafts_are_bounded_and_old_payloads_are_pruned(sharing):
    store, alice, _, _, _, token = sharing
    versions = []
    for _ in range(3):
        current = versions[-1]["version_id"] if versions else None
        versions.append(publish(store, token, base_version=current))
    with sqlite3.connect(store.path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM publication_objects WHERE version_id = ?",
                (versions[0]["version_id"],),
            ).fetchone()[0]
            == 0
        )
    store.commit_publication(token, versions[0]["version_id"])
    assert (
        store.get_project(alice.id, versions[0]["project_id"])["version_id"]
        == versions[-1]["version_id"]
    )
    body = BeginPublication(
        workspace_id="workspace-a",
        project=PublishedProject(id="p-a", name="P"),
        base_version=versions[-1]["version_id"],
    )
    for _ in range(4):
        store.begin_publication(token, body)
    with pytest.raises(SharingError) as limited:
        store.begin_publication(token, body)
    assert limited.value.status == 429
    with sqlite3.connect(store.path) as connection:
        draft_id = connection.execute(
            "SELECT id FROM publications WHERE committed_at IS NULL LIMIT 1"
        ).fetchone()[0]
    store.abort_publication(token, draft_id)
    assert store.begin_publication(token, body)["version_id"]
