"""Tests for the molq Remote Operations aggregator."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from molq import MolqError

from molab.plugins.submit_molq import dashboard


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
            _summary(state="failed"),
            _summary(state="timed_out"),
            _summary(state="cancelled"),
            _summary(state="unknown"),
            _summary(state="succeeded"),
            _summary(
                state="succeeded",
                submitted=now - timedelta(seconds=30),
                started=now - timedelta(seconds=10),
            ),
        ]
        stats = dashboard.compute_stats(jobs)

        assert stats.running == 2
        assert stats.pending == 1
        assert stats.failed == 3
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


def _snapshot(job_id: str, state: str, *, submitted: str) -> dict:
    return {
        "ref": {
            "registry_id": "reg",
            "cluster_id": "demo-id",
            "native_id": job_id,
            "incarnation": "1",
        },
        "state": state,
        "terminal": state not in {"queued", "running"},
        "name": f"job-{job_id}",
        "submitted_at": submitted,
        "started_at": "2026-10-13T00:00:20Z" if state != "queued" else None,
        "ended_at": "2026-10-13T00:01:00Z" if state not in {"queued", "running"} else None,
        "exit_code": 0 if state == "succeeded" else None,
    }


class _Cluster:
    def __init__(self, name: str, snapshots: list[dict]) -> None:
        self.name = name
        self.snapshots = snapshots

    def list(self, *, states: list[str] | None = None, name: str | None = None) -> dict:
        del name
        snaps = self.snapshots
        if states is not None:
            snaps = [item for item in snaps if item["state"] in states]
        return {"snapshots": snaps, "coverage": {"errors": []}}


class _Registry:
    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def list(self) -> list[dict]:
        return self.records


class _Molq:
    def __init__(self, records: list[dict], snaps: dict[str, list[dict]]) -> None:
        self.clusters = _Registry(records)
        self._snaps = snaps

    def cluster(self, name: str) -> _Cluster:
        if name == "down":
            raise RuntimeError("scheduler down")
        return _Cluster(name, self._snaps.get(name, []))


def _install(monkeypatch: pytest.MonkeyPatch, mq: _Molq) -> None:
    @contextmanager
    def _session(config_path=None):
        del config_path
        yield mq

    monkeypatch.setattr(dashboard, "molq_session", _session)


def _demo(monkeypatch: pytest.MonkeyPatch, snaps: list[dict]) -> None:
    _install(
        monkeypatch,
        _Molq(
            [{"name": "demo", "id": "demo-id", "scheduler": "shell", "target_root": "/tmp/molq"}],
            {"demo": snaps},
        ),
    )


class TestListTargets:
    def test_returns_summary_per_cluster(self, monkeypatch: pytest.MonkeyPatch):
        _demo(monkeypatch, [])

        targets = dashboard.list_targets(config_path="unused")

        assert len(targets) == 1
        target = targets[0]
        assert target.name == "demo"
        assert target.scheduler == "shell"
        assert target.cluster_name == "demo-id"
        assert target.jobs_dir == "/tmp/molq"
        assert target.healthy is True

    def test_active_jobs_counts_non_terminal(self, monkeypatch: pytest.MonkeyPatch):
        _demo(
            monkeypatch,
            [
                _snapshot("a", "running", submitted="2026-10-13T00:00:02Z"),
                _snapshot("b", "queued", submitted="2026-10-13T00:00:01Z"),
                _snapshot("c", "succeeded", submitted="2026-10-13T00:00:00Z"),
            ],
        )

        targets = dashboard.list_targets(config_path="unused")

        assert targets[0].active_jobs == 2

    def test_unhealthy_cluster_does_not_drop_the_list(self, monkeypatch: pytest.MonkeyPatch):
        _install(
            monkeypatch,
            _Molq(
                [
                    {
                        "name": "demo",
                        "id": "demo-id",
                        "scheduler": "shell",
                        "target_root": "/tmp/molq",
                    },
                    {
                        "name": "down",
                        "id": "down-id",
                        "scheduler": "slurm",
                        "target_root": "/scratch",
                    },
                ],
                {"demo": []},
            ),
        )

        targets = dashboard.list_targets()

        assert [item.name for item in targets] == ["demo", "down"]
        assert targets[1].healthy is False
        assert targets[1].health_reason is not None


class TestListJobs:
    def test_returns_jobs_sorted_by_submitted_desc(self, monkeypatch: pytest.MonkeyPatch):
        _demo(
            monkeypatch,
            [
                _snapshot("old", "succeeded", submitted="2026-10-13T00:00:00Z"),
                _snapshot("new", "running", submitted="2026-10-13T00:00:05Z"),
            ],
        )

        jobs = dashboard.list_jobs("demo", config_path="unused")

        assert [job.job_id for job in jobs] == ["new", "old"]

    def test_unknown_cluster_raises(self, monkeypatch: pytest.MonkeyPatch):
        _demo(monkeypatch, [])

        with pytest.raises(KeyError):
            dashboard.list_jobs("missing")


class TestGetJob:
    def test_returns_detail_with_summary(self, monkeypatch: pytest.MonkeyPatch):
        _demo(monkeypatch, [_snapshot("abc", "running", submitted="2026-10-13T00:00:00Z")])

        detail = dashboard.get_job("demo", "abc", config_path="unused")

        assert detail.summary.job_id == "abc"
        assert detail.summary.state == "running"
        assert detail.summary.name == "job-abc"
        assert detail.command_display is None
        assert detail.transitions == ()

    def test_missing_job_raises(self, monkeypatch: pytest.MonkeyPatch):
        _demo(monkeypatch, [])

        with pytest.raises(MolqError):
            dashboard.get_job("demo", "nope")


class TestFetchPage:
    def test_returns_jobs_and_stats(self, monkeypatch: pytest.MonkeyPatch):
        _demo(
            monkeypatch,
            [
                _snapshot("a", "running", submitted="2026-10-13T00:00:02Z"),
                _snapshot("b", "succeeded", submitted="2026-10-13T00:00:01Z"),
            ],
        )

        page = dashboard.fetch_page("demo", config_path="unused")

        assert len(page.jobs) == 2
        assert page.stats.running == 1
        assert page.stats.succeeded == 1


def test_queue_failure_is_never_a_successful_empty_page(monkeypatch):
    _install(monkeypatch, _Molq([{"name": "down", "id": "down-id"}], {}))
    for target in ("down", None):
        with pytest.raises(RuntimeError, match="scheduler down"):
            dashboard.fetch_page(target)


def test_partial_scheduler_coverage_is_reported(monkeypatch):
    _demo(monkeypatch, [])
    monkeypatch.setattr(
        _Cluster,
        "list",
        lambda *_args, **_kwargs: {"snapshots": [], "coverage": {"errors": ["query failed"]}},
    )
    with pytest.raises(MolqError, match="Incomplete queue"):
        dashboard.fetch_page("demo")


def test_partial_scheduler_coverage_is_unhealthy_and_not_missing(monkeypatch):
    _demo(monkeypatch, [])
    monkeypatch.setattr(
        _Cluster,
        "list",
        lambda *_args, **_kwargs: {"snapshots": [], "coverage": {"errors": ["query failed"]}},
    )
    assert dashboard.list_targets()[0].healthy is False
    with pytest.raises(MolqError, match="Incomplete queue"):
        dashboard.get_job("demo", "missing")
