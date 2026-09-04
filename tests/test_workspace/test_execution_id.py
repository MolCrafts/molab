"""Execution identity — schema v2.

An Execution's id is a location-independent UUIDv7 (RFC 9562) allocated by
:meth:`~molexp.workspace.execution_repository.ExecutionRepository.create`,
never a location-derived ``exec-{run_id}`` counter. The workflow runtime's
``make_execution_id`` returns the same UUIDv7 shape so callers that
pre-allocate a slot (molq submit) get an id with no cross-host collision risk.
"""

from __future__ import annotations

import uuid

from molexp.workspace.domain import ExecutionMode
from molexp.workspace.execution_repository import ExecutionRepository
from molexp.workspace.provenance import AgentRef

_TEST_AGENT = AgentRef(id="test", type="person", name="test")


def _repo(run) -> ExecutionRepository:
    ws = run.experiment.project.workspace
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def test_execution_repository_allocates_uuid7_id(run) -> None:
    run.materialize()
    state = _repo(run).create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
    assert uuid.UUID(state.id).version == 7


def test_two_execution_repository_creates_get_distinct_ids(run) -> None:
    run.materialize()
    repo = _repo(run)
    first = repo.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT).id
    second = repo.create(mode=ExecutionMode.RERUN, created_by=_TEST_AGENT).id
    assert first != second
