"""Science extras mount on the host via ``compose_*(extra=)``, not via harness imports."""

from __future__ import annotations

import ast
from pathlib import Path

from molexp.harness.host import Keys, compose_plan, compose_run
from molexp.plugins.extras import default_science_extras
from molexp.plugins.metrics.host import MetricsPlugin
from molexp.plugins.submit_molq.host import MolqJobs, MolqPlugin
from molexp.workspace.metrics_seam import (
    MetricsAppend,
    MetricsSink,
    create_metrics_writer,
    get_metrics_writer_factory,
    set_metrics_writer_factory,
)

PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "src" / "molexp" / "plugins"
_HOST_FILES = (
    PLUGINS_ROOT / "metrics" / "host.py",
    PLUGINS_ROOT / "submit_molq" / "host.py",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


class TestDuckTypedNoHarnessImport:
    def test_host_adapters_do_not_import_harness(self) -> None:
        for path in _HOST_FILES:
            imported = _imported_modules(path)
            assert not any(
                name == "molexp.harness" or name.startswith("molexp.harness.") for name in imported
            ), path


class TestMolqPlugin:
    def test_compose_run_extra_publishes_jobs(self, tmp_path: Path) -> None:
        host = compose_run(run_id="r", run_dir=tmp_path, extra=(MolqPlugin(),))
        assert host.dump()[-1] == "jobs"
        assert host.ctx.has(Keys.JOBS)
        jobs = host.ctx.require(Keys.JOBS)
        assert isinstance(jobs, MolqJobs)
        cfg = host.dump_config()
        assert "jobs" in cfg["plugins"]
        assert "jobs" in cfg["services"]
        host.unload("jobs")
        assert not host.ctx.has(Keys.JOBS)
        assert "jobs" not in host.dump()
        host.unload()

    def test_submit_handler_is_lazy(self) -> None:
        jobs = MolqJobs()
        handler = jobs.submit_handler(
            scheduler="slurm",
            cluster=None,
            resources={},
            scheduling={},
        )
        from molexp.plugins.submit_molq.submit import SubmitHandler

        assert isinstance(handler, SubmitHandler)


class _SentinelSink:
    def scalar(
        self,
        key: str,
        value: int | float,
        step: int | float | None = None,
        *,
        wall_time: object = None,
        tags: object = None,
    ) -> dict[str, object]:
        del key, value, step, wall_time, tags
        return {"sentinel": True}

    def flush(self) -> None:
        return None


def _sentinel_factory(_run_dir: Path, _append: MetricsAppend) -> MetricsSink:
    return _SentinelSink()


class TestMetricsPlugin:
    def test_compose_run_extra_installs_and_restores_factory(self, tmp_path: Path) -> None:
        previous = get_metrics_writer_factory()
        set_metrics_writer_factory(_sentinel_factory)
        try:
            host = compose_run(run_id="r", run_dir=tmp_path, extra=(MetricsPlugin(),))
            assert host.dump()[-1] == "metrics"
            writer = create_metrics_writer(tmp_path, append=lambda *_a: None)
            assert not isinstance(writer, _SentinelSink)
            host.unload("metrics")
            restored = create_metrics_writer(tmp_path, append=lambda *_a: None)
            assert isinstance(restored, _SentinelSink)
            host.unload()
        finally:
            set_metrics_writer_factory(previous)

    def test_both_extras_mount_in_order(self, tmp_path: Path) -> None:
        host = compose_run(
            run_id="r",
            run_dir=tmp_path,
            extra=(MolqPlugin(), MetricsPlugin()),
        )
        assert host.dump()[-2:] == ["jobs", "metrics"]
        assert host.ctx.has(Keys.JOBS)
        host.unload()
        assert not host.ctx.has(Keys.JOBS)


class TestDefaultScienceExtras:
    def test_run_profile_dump_lists_jobs(self, tmp_path: Path) -> None:
        extras = default_science_extras()
        assert tuple(p.name for p in extras) == ("jobs", "metrics")
        host = compose_run(run_id="dump", run_dir=tmp_path, extra=extras)
        cfg = host.dump_config()
        assert cfg["plugins"][-2:] == ["jobs", "metrics"]
        assert "jobs" in cfg["services"]
        host.unload()

    def test_plan_profile_dump_lists_jobs(self, tmp_path: Path) -> None:
        from molexp.harness.gateways.stub import StubAgentGateway
        from molexp.harness.store.file_artifact_store import FileArtifactStore

        host = compose_plan(
            run_id="dump",
            run_dir=tmp_path,
            gateway=StubAgentGateway(FileArtifactStore(root=tmp_path)),
            extra=default_science_extras(),
        )
        assert "jobs" in host.dump_config()["plugins"]
        assert host.ctx.has(Keys.JOBS)
        host.unload()
