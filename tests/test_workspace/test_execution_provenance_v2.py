from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.workspace.domain import ExecutionMode, ExecutionStatus
from molexp.workspace.index_store import JsonIndexStore
from molexp.workspace.provenance import ProvenanceStore


def test_run_identity_is_not_its_definition_hash(experiment) -> None:
    first = experiment.add_run({"temperature": 300})
    second = experiment.add_run({"temperature": 300})

    assert first.id != second.id
    assert first.metadata.definition_hash == second.metadata.definition_hash


def test_run_record_contains_definition_not_execution_state(run) -> None:
    payload = json.loads((Path(run.run_dir) / "run.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["definition_hash"] == run.metadata.definition_hash
    assert {
        "status",
        "owner_pid",
        "started_at",
        "finished_at",
        "current_execution_id",
        "execution_history",
        "error",
        "executor_info",
        "context",
    }.isdisjoint(payload)


def test_run_aggregates_multiple_concurrent_executions(run) -> None:
    first = run.start()
    second = run.start(mode=ExecutionMode.RERUN)
    first.__enter__()
    second.__enter__()
    try:
        assert first.id != second.id
        assert run.status_summary.total == 2
        assert run.status_summary.active == 2
        assert run.status_summary.by_status == {"running": 2}
    finally:
        second.__exit__(None, None, None)
        first.__exit__(None, None, None)

    assert run.status_summary.by_status == {"succeeded": 2}
    with pytest.raises(AttributeError, match="no scalar status"):
        _ = run.status


def test_failed_execution_is_preserved_when_retry_succeeds(run) -> None:
    with pytest.raises(RuntimeError, match="boom"), run.start() as failed:
        failed_id = failed.id
        raise RuntimeError("boom")

    with run.start(mode=ExecutionMode.RETRY, based_on_execution_id=failed_id) as retried:
        retry_id = retried.id

    states = {state.id: state for state in run.executions}
    assert states[failed_id].status is ExecutionStatus.FAILED
    assert states[retry_id].status is ExecutionStatus.SUCCEEDED
    assert states[retry_id].based_on_execution_id == failed_id


def test_intentional_interruption_is_not_recorded_as_failure(run) -> None:
    class ApprovalPause(RuntimeError):
        pass

    with pytest.raises(ApprovalPause), run.start() as execution:
        execution_id = execution.id
        execution.mark_interrupted("waiting for approval")
        raise ApprovalPause

    state = run._execution_repository().get(execution_id)
    assert state.status is ExecutionStatus.INTERRUPTED
    assert state.error is None


def test_artifact_identity_provenance_promotion_and_index_rebuild(run) -> None:
    with run.start() as execution:
        first = execution.emit_artifact(b"same bytes", name="first.bin")
        second = execution.emit_artifact(b"same bytes", name="second.bin")
        execution_id = execution.id

    assert first.id != second.id
    assert first.content.digest == second.content.digest

    project = run.experiment.project
    asset, v1 = project.assets.promote(first, created_by=first.created_by, title="dataset")
    same_asset, v2 = project.assets.promote(
        second,
        created_by=second.created_by,
        into_asset_id=asset.id,
    )
    assert same_asset.id == asset.id
    assert [version.version for version in project.assets.versions(asset.id)] == [1, 2]
    assert v1.source_artifact_id == first.id
    assert v2.source_artifact_id == second.id

    index = JsonIndexStore(project.workspace.root, fs=project.workspace.fs)
    index.clear()
    assert project.assets.get(asset.id).id == asset.id
    assert [
        artifact.id
        for artifact in run._execution_repository().artifacts.list_for_execution(execution_id)
    ] == [
        first.id,
        second.id,
    ]

    events = ProvenanceStore(project.workspace.root, fs=project.workspace.fs).iter_events()
    assert any(
        event.event_type == "ArtifactEmitted" and event.subject.id == first.id for event in events
    )
    assert any(
        event.event_type == "ArtifactPromoted" and event.subject.id == first.id for event in events
    )
    assert any(
        event.event_type == "AssetVersionCreated" and event.subject.id == v2.id for event in events
    )


def test_sealing_is_idempotent_and_workspace_matches_physical_hierarchy(run) -> None:
    with run.start() as execution:
        execution_id = execution.id
        assert execution.workdir == Path(run.run_dir) / "executions" / execution_id / "work"

    repository = run._execution_repository()
    first = repository.seal(execution_id, ExecutionStatus.SUCCEEDED)
    second = repository.seal(execution_id, ExecutionStatus.SUCCEEDED)
    assert first == second
    sealed = [
        event
        for event in repository.provenance.events_for(execution_id)
        if event.event_type == "ExecutionSealed" and event.subject.id == execution_id
    ]
    assert len(sealed) == 1
