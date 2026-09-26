"""``_submit_to_scheduler`` (``cli/workspace/run.py``) — the ``--scheduler`` dispatch.

Pins the one scheduler path left broken between arch-own-02d and 02c:
``molab run --rerun --fresh --scheduler`` still mints a UUID and writes
``executions/<uuid>/fresh.json`` before handing that id to the submitter,
which after 02d accepts only a workspace-allocated QUEUED ``eNN``.

(Not named ``test_run.py``: this directory has no ``__init__.py`` and that
basename already exists elsewhere in the suite. arch-own-02c moves this test
into ``tests/test_cli/test_workspace/test_run.py::TestSubmitToScheduler``.)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from molab.cli.workspace.run import _submit_to_scheduler
from molab.profile import ProfileConfig
from molab.workflow import Workflow, WorkflowCompiler, default_binding_registry
from molab.workspace import Workspace
from molab.workspace.domain import Execution
from molab.workspace.run import Run


@dataclass
class SubmitSpy:
    """What the fake ``Submitor`` saw inside ``submit_job``."""

    submits: int = 0
    execution_id: str | None = None
    record_at_submit: Execution | None = None
    record_error: str | None = None


@dataclass
class SchedulerFixture:
    ws: Workspace
    run: Run
    script: Path
    spy: SubmitSpy


def _install_fake_submitor(monkeypatch: pytest.MonkeyPatch, run: Run) -> SubmitSpy:
    spy = SubmitSpy()

    class _FakeEventBus:
        def on(self, evt: object, handler: object) -> None:
            del evt, handler

    class _FakeJob:
        job_id = "fake-job-id"
        scheduler_job_id = "fake-sched-id"

    class FakeSubmitor:
        def __init__(self, _cluster: object, *, jobs_dir: str) -> None:
            del jobs_dir
            self._event_bus = _FakeEventBus()

        def __enter__(self) -> FakeSubmitor:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

        def submit_job(
            self,
            *,
            resources: object,
            scheduling: object,
            execution: object,
            metadata: dict[str, str],
            argv: list[str] | None = None,
            script: object | None = None,
        ) -> _FakeJob:
            del resources, scheduling, execution, argv, script
            spy.submits += 1
            spy.execution_id = metadata["execution_id"]
            try:
                spy.record_at_submit = run.execution(metadata["execution_id"])
            except KeyError as exc:
                spy.record_error = f"no record for {metadata['execution_id']!r}: {exc}"
            return _FakeJob()

    monkeypatch.setattr("molq.Submitor", FakeSubmitor)
    return spy


@pytest.fixture
def scheduler_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[SchedulerFixture]:
    """A declared ``{"seed": 1}`` run whose only attempt ``e01`` was cancelled."""
    ws = Workspace(tmp_path / "ws")
    ws.materialize()
    project = ws.add_project("p")
    exp = project.add_experiment("e")
    run = exp.add_run(params={"seed": 1})
    run.create_execution()
    run.cancel("e01")

    script = tmp_path / "s.py"
    script.write_text("x = 1\n", encoding="utf-8")

    wf = Workflow(name="one")

    @wf.task
    def only(seed: int) -> int:
        return seed

    default_binding_registry.bind(exp, WorkflowCompiler().compile(wf))
    monkeypatch.setattr(
        "molab.cli.workspace.run._load_script_workspaces", lambda *_a, **_k: ([ws], None)
    )
    monkeypatch.setattr(
        "molab.plugins.submit_molq.metadata.supported_schedulers", lambda: ("local",)
    )
    spy = _install_fake_submitor(monkeypatch, run)
    try:
        yield SchedulerFixture(ws=ws, run=run, script=script, spy=spy)
    finally:
        default_binding_registry.unbind(exp)


class TestSubmitToScheduler:
    @pytest.mark.xfail(
        strict=True,
        raises=KeyError,
        reason=(
            "arch-own-02: src/molab/cli/workspace/run.py _submit_to_scheduler --rerun --fresh — "
            "flipped by arch-own-02c: submit a pre-created QUEUED eNN with bypass_cache, "
            "no UUID, no fresh.json"
        ),
    )
    def test_rerun_fresh_submits_queued_record_with_bypass_cache(
        self, scheduler_fixture: SchedulerFixture
    ) -> None:
        fx = scheduler_fixture

        _submit_to_scheduler(
            script=fx.script,
            profile_cfg=ProfileConfig({}, name=None),
            continue_verb="rerun",
            target_path=fx.ws.root,
            explicit_ws=True,
            selected_target=None,
            selected_scheduler="local",
            cluster=None,
            resources={},
            scheduling={},
            block=False,
            fresh=True,
        )

        assert fx.spy.execution_id == "e02"
        assert fx.spy.record_error is None, fx.spy.record_error
        record = fx.spy.record_at_submit
        assert record is not None
        assert record.status.value == "queued"
        assert record.mode.value == "rerun"
        assert record.based_on_execution_id == "e01"
        assert record.bypass_cache is True
        run_dir = Path(fx.run.run_dir)
        assert list(run_dir.rglob("fresh.json")) == []
        assert sorted(p.name for p in (run_dir / "executions").iterdir()) == ["e01", "e02"]
