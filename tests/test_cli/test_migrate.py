"""``molab migrate`` — an old workspace becomes a readable one.

The migration is judged by what the new tree looks like to a person and to
the reader: legible paths, one file per attempt, nothing that merely copies
something already on disk, and bulk payload shared with the source rather
than duplicated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.cli import migrate_cmd
from molab.cli.migrate_cmd import migrate_workspace
from molab.workspace import Workspace
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION
from molab.workspace.validate import validate_workspace

PROJECT_ID = "01a06e0a-0000-7000-8000-000000000001"
EXPERIMENT_ID = "01a06e0a-0000-7000-8000-000000000002"
RUN_ID = "01a06e0a-0000-7000-8000-000000000003"
EXEC_ID = "01a06e0a-0000-7000-8000-000000000004"
ARTIFACT_ID = "01a06e0a-0000-7000-8000-000000000005"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def legacy(tmp_path: Path) -> Path:
    """A workspace in the old shape: UUID paths, split sidecars, side stores."""
    root = tmp_path / "lab"
    _write(root / "workspace.json", {"schema_version": 2, "id": "lab", "type": "workspace.root"})
    _write(root / "projects.json", {PROJECT_ID: {"id": PROJECT_ID, "name": "peo-tg"}})

    project = root / "projects" / PROJECT_ID
    _write(project / "project.json", {"schema_version": 2, "id": PROJECT_ID, "name": "peo-tg"})
    _write(project / "experiments.json", {EXPERIMENT_ID: {"id": EXPERIMENT_ID}})

    experiment = project / "experiments" / EXPERIMENT_ID
    _write(
        experiment / "experiment.json",
        {
            "schema_version": 2,
            "id": EXPERIMENT_ID,
            "name": "ff-regression",
            "revision": 1,
            "revision_id": EXPERIMENT_ID,
            "definition_hash": "sha256:" + "a" * 64,
        },
    )
    _write(experiment / "runs.json", {RUN_ID: {"id": RUN_ID}})
    (experiment / "workflow.py").write_text("# the experiment's script\n", encoding="utf-8")

    run = experiment / "runs" / f"run-{RUN_ID}"
    _write(
        run / "run.json",
        {
            "schema_version": 2,
            "id": RUN_ID,
            "type": "workspace.run",
            "parameters": {"dp": 5, "seed": 42},
            "definition_hash": "sha256:" + "b" * 64,
            "experiment_revision_id": EXPERIMENT_ID,
            "created_at": "2026-09-04T22:09:31.441949",
        },
    )
    (run / "run.json.lock").write_text("", encoding="utf-8")

    attempt = run / "executions" / EXEC_ID
    _write(
        attempt / "execution.json",
        {
            "schema_version": 2,
            "id": EXEC_ID,
            "run_id": RUN_ID,
            "project_id": PROJECT_ID,
            "mode": "initial",
            "status": "failed",
            "created_at": "2026-09-04T22:09:31.925482Z",
            "finished_at": "2026-09-04T22:10:21.113655Z",
            "created_by": {"id": "molab", "type": "system", "name": "Molab"},
        },
    )
    _write(attempt / "environment.json", {"schema_version": 2, "environment": {"host": "n226"}})
    _write(attempt / "exception.json", {"type": "ImportError", "message": "boom"})
    (attempt / "runtime.log").write_text("started\n", encoding="utf-8")
    (attempt / "traceback.txt").write_text("Traceback: boom\n", encoding="utf-8")
    (attempt / "execution.json.lock").write_text("", encoding="utf-8")
    _write(attempt / "workflow.json", {"schema_version": 2, "workflow": {}})

    payload = b'{"t": 1}\n'
    digest = "76be54eb8c67ef2df41769481432fd811e1c453a44ceb9e68a8cd27458acaeae"
    _write(
        attempt / "artifacts" / ARTIFACT_ID / "artifact.json",
        {
            "schema_version": 2,
            "id": ARTIFACT_ID,
            "execution_id": EXEC_ID,
            "run_id": RUN_ID,
            "project_id": PROJECT_ID,
            "name": "metrics.jsonl",
            "content": {"digest": f"sha256:{digest}", "size": len(payload), "kind": "file"},
            "created_at": "2026-09-04T22:10:20.775525Z",
            "created_by": {"id": "molab", "type": "system", "name": "Molab"},
            "source_path": "work/metrics.jsonl",
        },
    )
    cas = root / "content" / "sha256" / digest[:2] / digest
    cas.mkdir(parents=True)
    (cas / "payload").write_bytes(payload)

    jobs = attempt / "jobs" / "5ad54d5f-7aaa-462d-900f-13c17fd1430e"
    jobs.mkdir(parents=True)
    _write(jobs / "manifest.json", {"scheduler": "slurm"})
    (jobs / "run_slurm.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (jobs / "stdout.log").write_text("out\n", encoding="utf-8")
    (jobs / "stderr.log").write_text("err\n", encoding="utf-8")

    (attempt / "work").mkdir()
    (attempt / "work" / "big.data").write_bytes(b"x" * 1024)

    _write(root / "index" / "entities" / "artifact" / f"{ARTIFACT_ID}.json", {"record": {}})
    _write(root / "provenance" / "events" / "2026" / "09" / "e.json", {"event_type": "x"})
    return root


class TestMigratedLayout:
    def test_every_path_segment_is_readable(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        run_dir = target / "projects/peo-tg/experiments/ff-regression/runs/dp=5_seed=42"
        assert run_dir.is_dir()
        assert (run_dir / "executions" / "e01" / "execution.json").is_file()

    def test_identity_survives_the_rename(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        ws = Workspace(target)
        project = ws.list_projects()[0]
        experiment = project.list_experiments()[0]
        run = experiment.list_runs()[0]
        assert (project.id, experiment.id, run.id) == (PROJECT_ID, EXPERIMENT_ID, RUN_ID)

    def test_the_result_conforms_to_the_layout_law(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)
        report = validate_workspace(target)
        assert report.ok, [f"{v.rule} {v.path}" for v in report.violations]


class TestFragmentsAreFolded:
    def test_one_attempt_is_one_file(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        ws = Workspace(target)
        run = ws.list_projects()[0].list_experiments()[0].list_runs()[0]
        attempt = run.executions[0]
        assert (attempt.id, attempt.seq, attempt.status.value) == ("e01", 1, "failed")
        assert attempt.environment == {"host": "n226"}
        assert attempt.error == {"type": "ImportError", "message": "boom"}
        assert [a.name for a in attempt.artifacts] == ["metrics.jsonl"]

        attempt_dir = Path(run.run_dir) / "executions" / "e01"
        assert not (attempt_dir / "environment.json").exists()
        assert not (attempt_dir / "exception.json").exists()
        assert not (attempt_dir / "traceback.txt").exists()
        # ``artifacts/`` is the promoted tier and holds bytes. What must be
        # gone is the per-artifact side-store that used to live inside it —
        # those records are now the one inline list on execution.json.
        assert not list(attempt_dir.rglob("artifact.json"))
        assert (attempt_dir / "artifacts" / "metrics.jsonl").is_file()

    def test_folded_record_is_current_schema(self, legacy: Path, tmp_path: Path) -> None:
        """arch-own-02a §6 (D66): the fold writes through the repository's versioned write."""
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)
        record = json.loads(
            (
                target
                / "projects/peo-tg/experiments/ff-regression/runs/dp=5_seed=42"
                / "executions/e01/execution.json"
            ).read_text(encoding="utf-8")
        )
        assert record["schema_version"] == 4
        assert record["schema_version"] == MOLAB_SCHEMA_VERSION

    def test_evidence_becomes_one_log(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)
        log = (
            target
            / "projects/peo-tg/experiments/ff-regression/runs/dp=5_seed=42/executions/e01/run.log"
        ).read_text()
        assert "started" in log
        assert "Traceback: boom" in log

    def test_scheduler_jobs_are_flat_files(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)
        jobs = (
            target
            / "projects/peo-tg/experiments/ff-regression/runs/dp=5_seed=42/executions/e01/jobs"
        )
        assert sorted(p.name for p in jobs.iterdir()) == [
            "5ad54d5f-7aaa-462d-900f-13c17fd1430e.err",
            "5ad54d5f-7aaa-462d-900f-13c17fd1430e.json",
            "5ad54d5f-7aaa-462d-900f-13c17fd1430e.out",
            "5ad54d5f-7aaa-462d-900f-13c17fd1430e.sh",
        ]
        assert not any(p.is_dir() for p in jobs.iterdir())


class TestSideStoresAreDropped:
    def test_nothing_that_only_copied_the_tree_survives(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        assert not (target / "index").exists()
        assert not (target / "provenance").exists()
        assert not (target / "content").exists()
        assert not list(target.rglob("projects.json"))
        assert not list(target.rglob("experiments.json"))
        assert not list(target.rglob("runs.json"))
        assert not list(target.rglob("*.lock"))

    def test_the_artifact_bytes_land_where_a_person_looks(
        self, legacy: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)
        ws = Workspace(target)
        run = ws.list_projects()[0].list_experiments()[0].list_runs()[0]
        artifact = run.executions[0].artifacts[0]
        assert artifact.path.endswith("executions/e01/artifacts/metrics.jsonl")
        assert (target / artifact.path).read_bytes() == b'{"t": 1}\n'


class TestBulkPayload:
    def test_work_is_hard_linked_not_copied(self, legacy: Path, tmp_path: Path) -> None:
        """An old ``work/`` becomes ``out/``, and its bytes are never copied.

        The old directory held everything the attempt wrote — antechamber
        droppings and the trajectory alike — and the two cannot be told apart
        after the fact. It lands in the tier that is *kept*, never in the one
        declared safe to delete whole.
        """
        target = tmp_path / "lab-v3"
        report = migrate_workspace(legacy, target)

        source = legacy / "projects" / PROJECT_ID / "experiments" / EXPERIMENT_ID
        source_file = source / "runs" / f"run-{RUN_ID}" / "executions" / EXEC_ID / "work/big.data"
        moved = (
            target
            / "projects/peo-tg/experiments/ff-regression/runs/dp=5_seed=42/executions/e01/out/big.data"
        )
        assert moved.is_file()
        assert moved.stat().st_ino == source_file.stat().st_ino
        assert report.copied_files == 0

    def test_the_source_workspace_is_untouched(self, legacy: Path, tmp_path: Path) -> None:
        before = sorted(str(p.relative_to(legacy)) for p in legacy.rglob("*"))
        migrate_workspace(legacy, tmp_path / "lab-v3")
        after = sorted(str(p.relative_to(legacy)) for p in legacy.rglob("*"))
        assert before == after


class TestHonesty:
    def test_an_attempt_with_no_state_file_is_not_called_a_success(
        self, legacy: Path, tmp_path: Path
    ) -> None:
        """An old attempt that only left scheduler output never recorded how it
        ended. The migration must say so, not invent a result."""
        stub = (
            legacy
            / "projects"
            / PROJECT_ID
            / "experiments"
            / EXPERIMENT_ID
            / "runs"
            / f"run-{RUN_ID}"
            / "executions"
            / "exec-legacy"
            / "jobs"
            / "j1"
        )
        stub.mkdir(parents=True)
        (stub / "stdout.log").write_text("submitted\n", encoding="utf-8")

        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        ws = Workspace(target)
        run = ws.list_projects()[0].list_experiments()[0].list_runs()[0]
        statuses = {x.status.value for x in run.executions}
        assert "succeeded" not in statuses
        assert "interrupted" in statuses


class TestSafety:
    def test_a_non_empty_target_is_refused(self, legacy: Path, tmp_path: Path) -> None:
        target = tmp_path / "lab-v3"
        target.mkdir()
        (target / "keep.txt").write_text("mine", encoding="utf-8")
        with pytest.raises(Exception, match="not empty"):
            migrate_workspace(legacy, target)


class TestLegacyKnowledgeIndexKeep:
    """``knowledges.json`` is the **old children-index filename**, deliberately kept.

    It reads like a workspace knowledge leftover, but its meaning is "an old
    index that only copied the tree — recognise it and drop it". The migration
    tool must keep recognising it, so this lock stops a later sweep (11's
    cleanup scan) from deleting the entry as knowledge debris.
    """

    def test_the_drop_name_is_registered(self) -> None:
        assert "knowledges.json" in migrate_cmd._DROP_NAMES

    def test_a_legacy_children_index_does_not_survive(self, legacy: Path, tmp_path: Path) -> None:
        index = legacy / "projects" / PROJECT_ID / "experiments" / EXPERIMENT_ID / "knowledges.json"
        _write(index, {"some-id": {"id": "some-id", "title": "cooling-rate"}})

        target = tmp_path / "lab-v3"
        migrate_workspace(legacy, target)

        assert not list(target.rglob("knowledges.json"))


class TestMigrateBrand:
    def test_renames_workspace_machine_dir_and_gitignore(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_brand

        ws = tmp_path / "lab"
        (ws / ".molexp" / "locks").mkdir(parents=True)
        (ws / ".molexp" / "locks" / "x.lock").write_text("", encoding="utf-8")
        (ws / ".gitignore").write_text("# head\n.molexp/\n*.pyc\n", encoding="utf-8")

        report = migrate_brand(ws, migrate_home=False)
        assert report.workspace_dir_renamed is True
        assert report.gitignore_updated is True
        assert not (ws / ".molexp").exists()
        assert (ws / ".molab" / "locks" / "x.lock").is_file()
        assert ".molab/" in (ws / ".gitignore").read_text(encoding="utf-8")
        assert ".molexp/" not in (ws / ".gitignore").read_text(encoding="utf-8")

    def test_renames_home_config_dir(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_brand

        ws = tmp_path / "lab"
        ws.mkdir()
        fake_home = tmp_path / "home"
        (fake_home / ".molexp" / "config.json").parent.mkdir(parents=True)
        (fake_home / ".molexp" / "config.json").write_text("{}", encoding="utf-8")

        report = migrate_brand(ws, home=fake_home, migrate_home=True)
        assert report.home_renamed is True
        assert not (fake_home / ".molexp").exists()
        assert (fake_home / ".molab" / "config.json").is_file()

    def test_refuses_when_both_machine_dirs_exist(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_brand

        ws = tmp_path / "lab"
        (ws / ".molexp").mkdir(parents=True)
        (ws / ".molab").mkdir(parents=True)
        with pytest.raises(Exception, match="both"):
            migrate_brand(ws, migrate_home=False)
