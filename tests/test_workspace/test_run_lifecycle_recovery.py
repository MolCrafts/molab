"""Execution-level recovery semantics (run-recovery bugs 1-3, v2).

A Run has no scalar status; every physical Execution is sealed independently
as SUCCEEDED / FAILED / INTERRUPTED / CANCELLED and is immutable once sealed.
Recovery is a *new* Execution (RERUN, based on a terminal predecessor; a
RETRY request is stored as RERUN since arch-own-03a) — it never mutates the
failed attempt.

Bug 1 (v2) — a failed Execution is immutable: a subsequent attempt is a new
Execution and never flips the failed one back to ``succeeded``. There is no
``"aborted"`` status in v2.

Bug 2 (v2) — a new (retry) Execution is born with no error; the stale error
stays attached only to the failed Execution that produced it.

Bug 3 — the common failure path (engine swallows the task exception and
resolves the Execution to FAILED via ``mark_failed``; nothing propagates out
of the ``with`` block) must still persist failure evidence under
``executions/<exec_id>/`` (``exception.json``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus


@pytest.fixture
def run(tmp_path):
    ws = Workspace(root=tmp_path / "lab", name="lab")
    exp = ws.add_project("p").add_experiment("e")
    return exp.add_run(params={"i": 0})


def _fail_once(run) -> str:
    """Drive *run* to one FAILED Execution through the real exception path."""
    with pytest.raises(RuntimeError), run.start() as ctx:
        failed_id = ctx.id
        raise RuntimeError("boom")
    assert run.executions[-1].status is ExecutionStatus.FAILED
    return failed_id


# ── Bug 1: failed Executions are immutable; recovery is a new Execution ─────


class TestNoOpAttemptKeepsPriorStatus:
    def test_failed_execution_stays_failed_after_retry(self, run):
        failed_id = _fail_once(run)

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id):
            pass  # clean retry — a NEW Execution, must not flip the failed one

        states = {s.id: s for s in run.executions}
        assert states[failed_id].status is ExecutionStatus.FAILED
        assert run.status_summary.total == 2

    def test_failed_execution_keeps_error(self, run):
        failed_id = _fail_once(run)
        state = run._execution_repository().get(failed_id)
        assert state.error is not None
        assert state.error["type"] == "RuntimeError"
        assert state.error["message"] == "boom"

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id):
            pass

        # The retry must not clear the failed Execution's error.
        assert run._execution_repository().get(failed_id).error is not None

    def test_retry_is_new_execution_not_aborted(self, run):
        failed_id = _fail_once(run)

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id):
            pass

        executions = run.executions
        assert len(executions) == 2
        assert executions[-1].status is ExecutionStatus.SUCCEEDED  # v2 has no "aborted"

    def test_cancelled_execution_stays_cancelled(self, run):
        with run.start() as ctx:
            exec_id = ctx.id
            run.cancel(exec_id)

        assert run.executions[-1].status is ExecutionStatus.CANCELLED

    def test_new_results_are_a_positive_signal(self, run):
        """A retry that records new results is real work — it succeeds."""
        failed_id = _fail_once(run)

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id) as ctx:
            ctx.set_result("train", {"loss": 0.1})
            retry_id = ctx.id

        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED
        assert run.get_result("train", execution_id=retry_id) == {"loss": 0.1}

    def test_mark_succeeded_is_a_positive_signal(self, run):
        """A clean retry resolves to SUCCEEDED (the workflow runtime's signal)."""
        failed_id = _fail_once(run)

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id) as ctx:
            ctx.mark_succeeded()

        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

    def test_mark_failed_wins_over_mark_succeeded(self, run):
        with run.start() as ctx:
            ctx.mark_failed("task X blew up")
            ctx.mark_succeeded()  # must not override a recorded failure

        assert run.executions[-1].status is ExecutionStatus.FAILED

    def test_plain_first_attempt_still_succeeds(self, run):
        """A clean exception-free first attempt seals SUCCEEDED."""
        with run.start():
            pass
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED


# ── Bug 2: a retry Execution is born with no error ──────────────────────────


class TestSuccessClearsStaleError:
    def test_retry_execution_has_no_error_on_disk(self, run):
        failed_id = _fail_once(run)

        with run.start(mode=ExecutionMode.RERUN, based_on_execution_id=failed_id) as ctx:
            ctx.mark_succeeded()
            retry_id = ctx.id

        # Reload from disk through the parent experiment.
        reloaded = run.experiment.get_run(run.id)
        states = {s.id: s for s in reloaded.executions}
        assert states[retry_id].error is None
        assert states[retry_id].status is ExecutionStatus.SUCCEEDED


# ── Bug 3: engine-swallowed failures still write failure evidence ───────────


class TestErrorTxtOnSwallowedFailure:
    def test_mark_failed_path_writes_exception_json(self, run):
        """The engine catches task exceptions and resolves the Execution to
        FAILED via mark_failed — no exception reaches the ``with`` exit.
        Failure evidence must still land in the execution directory."""
        with run.start() as ctx:
            ctx.mark_failed("ZeroDivisionError: division by zero")
            exec_id = ctx.id

        assert run.executions[-1].status is ExecutionStatus.FAILED
        exception_json = Path(str(run.run_dir)) / "executions" / exec_id / "exception.json"
        assert exception_json.exists()
        content = exception_json.read_text()
        assert "ZeroDivisionError" in content
        assert "division by zero" in content

    def test_mark_failed_traceback_lands_in_traceback_txt(self, run):
        """The workflow runtime forwards the formatted task traceback through
        ``mark_failed(..., traceback_text=…)``; the lifecycle must persist it
        into traceback.txt instead of dropping it."""
        tb = (
            "Traceback (most recent call last):\n"
            '  File "wf.py", line 3, in explode\n'
            "    raise ZeroDivisionError('division by zero')\n"
            "ZeroDivisionError: division by zero\n"
        )
        with run.start() as ctx:
            ctx.mark_failed("ZeroDivisionError: division by zero", traceback_text=tb)
            exec_id = ctx.id

        traceback_txt = Path(str(run.run_dir)) / "executions" / exec_id / "traceback.txt"
        content = traceback_txt.read_text()
        assert "Traceback (most recent call last):" in content
        assert "raise ZeroDivisionError" in content
        assert "No Python traceback was captured" not in content
