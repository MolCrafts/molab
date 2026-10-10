"""Tests for the molq Remote Operations aggregator."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from molq.models import Command, JobSpec
from molq.status import JobState

from molab.plugins.submit_molq import dashboard

# ── compute_stats ──────────────────────────────────────────────────────────


def _summary(
    *,
    state: str,
    submitted: datetime | None = None,
    started: datetime | None = None,
) -> dashboard.JobSummary:
    return dashboard.JobSummary(
        target="t",
        job_id="j",
        scheduler_job_id=None,
        cluster_name=None,
        scheduler=None,
        name=None,
        state=state,
        submitted_at=submitted,
        started_at=started,
        finished_at=None,
        exit_code=None,
        duration_seconds=None,
        cwd=None,
    )


class TestComputeStats:
    def test_buckets_each_state_correctly(self):
        now = datetime.now(UTC)
        jobs = [
            _summary(state="running"),
            _summary(state="running"),
            _summary(state="queued"),
            _summary(state="submitted"),
            _summary(state="created"),
            _summary(state="failed"),
            _summary(state="timed_out"),
            _summary(state="cancelled"),
            _summary(state="lost"),
            _summary(state="succeeded"),
            _summary(
                state="succeeded",
                submitted=now - timedelta(seconds=30),
                started=now - timedelta(seconds=10),
            ),
        ]
        stats = dashboard.compute_stats(jobs)

        assert stats.running == 2
        assert stats.pending == 3
        assert stats.failed == 4
        assert stats.succeeded == 2
        assert stats.avg_wait_seconds == pytest.approx(20.0, abs=0.01)

    def test_empty_returns_zeros_and_no_avg(self):
        stats = dashboard.compute_stats([])

        assert stats.running == 0
        assert stats.pending == 0
        assert stats.failed == 0
        assert stats.succeeded == 0
        assert stats.avg_wait_seconds is None

    def test_excludes_waits_outside_24h_window(self):
        old = datetime.now(UTC) - timedelta(days=2)
        jobs = [
            _summary(
                state="succeeded",
                submitted=old,
                started=old + timedelta(seconds=600),
            ),
        ]
        stats = dashboard.compute_stats(jobs)

        assert stats.avg_wait_seconds is None


# ── list_targets / list_jobs / get_job ─────────────────────────────────────


@pytest.fixture
def molq_config(tmp_path, monkeypatch):
    """Isolate the molq store + config under tmp_path for the duration of the test.

    ``Submitor.from_profile`` auto-bootstraps a ``JobStore`` at
    ``molcfg.project_config_dir('molq') / 'jobs.db'``. Setting
    ``MOLCRAFTS_HOME`` redirects molcfg's base under ``tmp_path`` so
    the store, config, and any other molcfg-managed paths land in
    test scratch.
    """
    from tests.test_plugins.test_submit_molq.conftest import write_molq_demo_config

    config_path = write_molq_demo_config(tmp_path, monkeypatch)
    dashboard._reset_submitor_cache()
    yield config_path
    dashboard._reset_submitor_cache()


def _seed_record(submitor, *, job_id: str, state: JobState) -> None:
    """Build a synthetic JobSpec and insert it directly into the store."""
    spec = JobSpec(
        job_id=job_id,
        cluster_name=submitor.cluster_name,
        scheduler="local",
        command=Command.from_submit_args(argv=["echo", "hi"]),
        cwd=str(submitor._jobs_dir) if submitor._jobs_dir else ".",
        metadata={"job_name": f"job-{job_id}"},
    )
    submitor._store.insert_job(spec)
    now = time.time()
    submitor._store.update_job(
        job_id,
        state=state,
        scheduler_job_id=f"sched-{job_id}",
        submitted_at=now - 30,
        started_at=(now - 20) if state != JobState.QUEUED else None,
        finished_at=now if state.is_terminal else None,
        exit_code=0 if state == JobState.SUCCEEDED else None,
    )


class TestListTargets:
    def test_returns_summary_per_profile(self, molq_config):
        targets = dashboard.list_targets(config_path=molq_config)

        assert len(targets) == 1
        target = targets[0]
        assert target.name == "demo"
        assert target.scheduler == "local"
        assert target.cluster_name == "demo-local"
        assert target.healthy is True

    def test_active_jobs_counts_non_terminal(self, molq_config):
        # The cache is keyed by (name, config_path_str).
        submitor = dashboard._submitor_for("demo", str(molq_config))
        _seed_record(submitor, job_id="a", state=JobState.RUNNING)
        _seed_record(submitor, job_id="b", state=JobState.QUEUED)
        _seed_record(submitor, job_id="c", state=JobState.SUCCEEDED)

        targets = dashboard.list_targets(config_path=molq_config)

        assert targets[0].active_jobs == 2


class TestListJobs:
    def test_returns_jobs_sorted_by_submitted_desc(self, molq_config):
        submitor = dashboard._submitor_for("demo", str(molq_config))
        _seed_record(submitor, job_id="old", state=JobState.SUCCEEDED)
        time.sleep(0.01)
        _seed_record(submitor, job_id="new", state=JobState.RUNNING)

        jobs = dashboard.list_jobs("demo", config_path=molq_config)

        assert [j.job_id for j in jobs] == ["new", "old"]


class TestGetJob:
    def test_returns_detail_with_summary(self, molq_config):
        submitor = dashboard._submitor_for("demo", str(molq_config))
        _seed_record(submitor, job_id="abc", state=JobState.RUNNING)

        detail = dashboard.get_job("demo", "abc", config_path=molq_config)

        assert detail.summary.job_id == "abc"
        assert detail.summary.state == "running"
        assert detail.command_display == "echo hi"


# ── fetch_page ─────────────────────────────────────────────────────────────


class TestFetchPage:
    def test_returns_jobs_and_stats(self, molq_config):
        submitor = dashboard._submitor_for("demo", str(molq_config))
        _seed_record(submitor, job_id="a", state=JobState.RUNNING)
        _seed_record(submitor, job_id="b", state=JobState.SUCCEEDED)

        page = dashboard.fetch_page("demo", config_path=molq_config)

        assert len(page.jobs) == 2
        assert page.stats.running == 1
        assert page.stats.succeeded == 1
