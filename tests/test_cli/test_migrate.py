"""``molab migrate`` — an old workspace becomes a readable one.

The migration is judged by what the new tree looks like to a person and to
the reader: legible paths, one file per attempt, nothing that merely copies
something already on disk, and bulk payload shared with the source rather
than duplicated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from molab.cli import migrate_cmd
from molab.cli.migrate_cmd import migrate_app, migrate_workflow_kind, migrate_workspace
from molab.workspace import Experiment, Workspace
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
        assert artifact.path == "artifacts/metrics.jsonl"
        assert (run.execution_dir("e01") / artifact.path).read_bytes() == b'{"t": 1}\n'


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


DOC_A: dict[str, object] = {
    "workflow_id": "workflow_00000000",
    "name": "constant_add",
    "task_configs": [
        {
            "task_id": "a",
            "task_type": "core.constant",
            "config": {"value": 2},
            "status": "pending",
        },
        {
            "task_id": "b",
            "task_type": "core.constant",
            "config": {"value": 3},
            "status": "pending",
        },
        {
            "task_id": "c",
            "task_type": "core.add",
            "config": {},
            "status": "pending",
        },
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}

GRAPH_IR: dict[str, object] = {
    "name": "g",
    "tasks": [{"task_id": "t", "task_type": "core.constant"}],
    "edges": [],
}

_ENTRYPOINT = "wf.py:build"


def _write_ir(exp: Experiment, document: dict[str, object]) -> None:
    path = Path(exp.experiment_dir) / "workflow.ir.json"
    path.write_text(json.dumps(document), encoding="utf-8")


def _kind_lab(tmp_path: Path) -> Path:
    """Six legacy experiments: two code, one document, three unbound."""
    root = tmp_path / "lab"
    workspace = Workspace(root, name="lab")
    project = workspace.add_project("proj")

    entry = project.add_experiment("entry")
    entry.metadata = entry.metadata.model_copy(update={"workflow_entrypoint": _ENTRYPOINT})
    entry.save()
    _write_ir(entry, GRAPH_IR)

    plan = project.add_experiment("plan")
    plan.metadata = plan.metadata.model_copy(update={"plan_run_id": "p1"})
    plan.save()

    document = project.add_experiment("document")
    _write_ir(document, DOC_A)

    memo = project.add_experiment("memo")
    _write_ir(memo, GRAPH_IR)

    handwritten = project.add_experiment("handwritten")
    meta_path = Path(handwritten.experiment_dir) / "experiment.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["workflow_source"] = "train.py"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    project.add_experiment("empty")
    return root


def _revisions(root: Path) -> dict[str, tuple[int, str]]:
    project = Workspace(root, name="lab").get_project("proj")
    return {
        exp.name: (exp.metadata.revision, exp.metadata.revision_id)
        for exp in project.list_experiments()
    }


def _ir_and_experiment_bytes(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for name in ("experiment.json", "workflow.ir.json"):
        for path in sorted(root.rglob(name)):
            found[str(path.relative_to(root))] = path.read_bytes()
    return found


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestMigrateWorkflowKind:
    def test_first_pass_binds_without_changing_revision(self, tmp_path: Path) -> None:
        root = _kind_lab(tmp_path)
        before = _revisions(root)

        report = migrate_workflow_kind(root)

        assert report.code == 2
        assert report.document == 1
        assert report.unbound == 3
        assert report.skipped == 0
        assert _revisions(root) == before

        project = Workspace(root, name="lab").get_project("proj")
        kinds = {exp.name: exp.workflow_kind for exp in project.list_experiments()}
        assert kinds == {
            "entry": "code",
            "plan": None,
            "document": "document",
            "memo": "code",
            "handwritten": None,
            "empty": None,
        }
        assert project.get_experiment("document").workflow_document == DOC_A
        assert project.get_experiment("entry").entrypoint == _ENTRYPOINT
        plan = project.get_experiment("plan")
        assert plan.workflow_kind is None
        assert any("legacy plan run" in note for note in report.notes)

    def test_second_pass_skips_bound_experiments(self, tmp_path: Path) -> None:
        root = _kind_lab(tmp_path)
        migrate_workflow_kind(root)
        before = _ir_and_experiment_bytes(root)

        report = migrate_workflow_kind(root)

        assert report.skipped == 3
        assert report.code == 0
        assert report.document == 0
        assert report.unbound == 3
        assert _ir_and_experiment_bytes(root) == before

    def test_dry_run_counts_and_writes_nothing(self, tmp_path: Path) -> None:
        root = _kind_lab(tmp_path)
        before = _tree_bytes(root)

        report = migrate_workflow_kind(root, dry_run=True)

        assert report.code == 2
        assert report.document == 1
        assert report.unbound == 3
        assert report.skipped == 0
        assert report.dry_run is True
        assert _tree_bytes(root) == before
        project = Workspace(root, name="lab").get_project("proj")
        assert all(exp.workflow_kind is None for exp in project.list_experiments())

    def test_cli_dry_run_reports_counts(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        root = _kind_lab(tmp_path)
        result = CliRunner().invoke(migrate_app, ["workflow-kind", str(root), "--dry-run"])

        assert result.exit_code == 0
        assert "code: 2" in result.stdout
        assert "dry run" in result.stdout
        assert "dropped workflow_source" not in result.stdout

    def test_cli_missing_path_exits_2(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        result = CliRunner().invoke(migrate_app, ["workflow-kind", str(tmp_path / "missing")])

        assert result.exit_code == 2


class TestMigrateAssets:
    def test_missing_workspace_json_is_bad_parameter(self, tmp_path: Path) -> None:
        import typer

        from molab.cli.migrate_cmd import migrate_assets

        with pytest.raises(typer.BadParameter):
            migrate_assets(tmp_path)

    def test_rewrites_one_record_and_drops_the_root_manifest(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_assets
        from tests.support.legacy_assets import DIGEST, HELLO, LEGACY_ID, write_legacy_data_asset

        root = tmp_path / "lab"
        Workspace(root, name="lab").materialize()
        write_legacy_data_asset(
            root,
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
        )
        (root / "assets.json").write_text(
            json.dumps({"schema_version": 1, "assets": {}}), encoding="utf-8"
        )

        report = migrate_assets(root)

        assert len(report.rewritten) == 1
        assert report.manifests_removed == ("assets.json",)

    def test_cli_dry_run_prints_counts_and_writes_nothing(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from tests.support.legacy_assets import DIGEST, HELLO, LEGACY_ID, write_legacy_data_asset

        root = tmp_path / "lab"
        Workspace(root, name="lab").materialize()
        write_legacy_data_asset(
            root,
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
        )
        (root / "assets.json").write_text(
            json.dumps({"schema_version": 1, "assets": {}}), encoding="utf-8"
        )
        before = _tree_bytes(root)

        result = CliRunner().invoke(migrate_app, ["assets", str(root), "--dry-run"])

        assert result.exit_code == 0
        assert "DRY-RUN" in result.stdout
        assert "1" in result.stdout
        assert _tree_bytes(root) == before

    def test_cli_unresolved_exits_1(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from tests.support.legacy_assets import write_legacy_domain_asset

        root = tmp_path / "lab"
        project = Workspace(root, name="lab").add_project("p")
        asset_id = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6d"
        write_legacy_domain_asset(
            Path(project.project_dir),
            asset_id=asset_id,
            project_id=project.id,
            title="model",
            artifact_id="0190ffff-0000-7000-8000-000000000000",
            content={"digest": "sha256:" + "ab" * 32, "size": 1, "kind": "file"},
        )

        result = CliRunner().invoke(migrate_app, ["assets", str(root)])

        assert result.exit_code == 1
        assert asset_id in result.stdout
        assert "no longer exists" in result.stdout


def _knowledge_workspace(tmp_path: Path) -> tuple[Path, object, object, object]:
    """A workspace with one project, experiment and ``seed=1`` run."""
    root = tmp_path / "lab"
    workspace = Workspace(root, name="lab")
    workspace.materialize()
    project = workspace.add_project("p")
    experiment = project.add_experiment("e")
    run = experiment.add_run(params={"seed": 1})
    return root, experiment, run, workspace


def _snapshot(root: Path) -> tuple[dict[str, str], set[str]]:
    import hashlib

    hashes: dict[str, str] = {}
    paths: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        for name in dirnames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            paths.add(f"{rel}/")
        for name in filenames:
            file = Path(dirpath) / name
            rel = file.relative_to(root).as_posix()
            paths.add(rel)
            hashes[rel] = hashlib.sha256(file.read_bytes()).hexdigest()
    return hashes, paths


class TestMigrateKnowledge:
    def test_root_level_reference_and_directory_forms(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_knowledge
        from molab.workspace.refs import MolabRef

        root, experiment, run, workspace = _knowledge_workspace(tmp_path)
        run_ref = str(MolabRef(experiment_id=experiment.id, run_id=run.id))
        experiment_ref = str(MolabRef(experiment_id=experiment.id))
        (root / "cooling-rate.md").write_text(
            "---\nclass: Note\n---\n\n"
            "From [@derived_from run](projects/p/experiments/e/runs/seed=1).\n",
            encoding="utf-8",
        )
        (root / "index.md").write_text("# Lab\n", encoding="utf-8")
        refs = root / "references"
        refs.mkdir()
        (refs / "meta.json").write_text('{"type": "bundle.references"}\n', encoding="utf-8")
        (refs / "k1.md").write_text("---\nclass: Literature\n---\n\n# K1\n", encoding="utf-8")
        k2 = refs / "k2"
        k2.mkdir()
        (k2 / "literature.json").write_text('{"title": "T", "doi": "10.1/x"}\n', encoding="utf-8")
        (k2 / "index.md").write_text("The paper.\n", encoding="utf-8")
        obs = Path(experiment.resolve()) / "knowledges" / "obs-1"
        obs.mkdir(parents=True)
        (obs / "observation.json").write_text(
            json.dumps(
                {
                    "created_by": "alice",
                    "sources": [
                        {"kind": "run", "ref": run.id},
                        {"kind": "experiment", "ref": experiment.id},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (obs / "index.md").write_text(
            "[cooling](../../../../../../cooling-rate.md)\n", encoding="utf-8"
        )
        index_before = (root / "index.md").read_bytes()

        report = migrate_knowledge(root)

        note = (root / "knowledges" / "cooling-rate.md").read_text(encoding="utf-8")
        assert run_ref in note
        assert workspace.find(run_ref).id == run.id
        assert not (root / "cooling-rate.md").exists()
        assert (root / "index.md").read_bytes() == index_before
        assert ("index.md", "no knowledge class") in report.skipped
        literature = (root / "knowledges" / "k1.md").read_text(encoding="utf-8")
        assert "class: Literature" in literature
        folded = (root / "knowledges" / "k2.md").read_text(encoding="utf-8")
        assert "class: Literature" in folded
        assert "title: T" in folded
        assert "doi: 10.1/x" in folded
        assert "The paper." in folded
        assert not refs.exists()
        obs_text = (Path(experiment.resolve()) / "knowledges" / "obs-1.md").read_text(
            encoding="utf-8"
        )
        assert "class: Observation" in obs_text
        assert "created_by: alice" in obs_text
        assert "sources:" not in obs_text
        assert "../../../../../knowledges/cooling-rate.md" in obs_text
        assert f"- [@derived_from {run.id}]({run_ref})" in obs_text
        assert f"- [@derived_from {experiment.id}]({experiment_ref})" in obs_text
        assert not obs.exists()

    def test_attachment_stays_and_collision_keeps_both(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_knowledge

        root, experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        (root / "knowledges").mkdir()
        (root / "knowledges" / "cooling-rate.md").write_text(
            "---\nclass: Note\n---\n\n# kept\n", encoding="utf-8"
        )
        (root / "cooling-rate.md").write_text(
            "---\nclass: Note\n---\n\n# legacy\n", encoding="utf-8"
        )
        obs = Path(experiment.resolve()) / "knowledges" / "obs-1"
        obs.mkdir(parents=True)
        (obs / "observation.json").write_text('{"created_by": "alice"}\n', encoding="utf-8")
        (obs / "index.md").write_text("![f](fig.png)\n", encoding="utf-8")
        (obs / "fig.png").write_bytes(b"PNG")

        report = migrate_knowledge(root)

        assert (
            (root / "knowledges" / "cooling-rate.md")
            .read_text(encoding="utf-8")
            .endswith("# kept\n")
        )
        assert "# legacy" in (root / "knowledges" / "cooling-rate-2.md").read_text(encoding="utf-8")
        assert report.collisions == [("knowledges/cooling-rate.md", "knowledges/cooling-rate-2.md")]
        landed = (Path(experiment.resolve()) / "knowledges" / "obs-1.md").read_text(
            encoding="utf-8"
        )
        assert "![f](obs-1/fig.png)" in landed
        assert (obs / "fig.png").read_bytes() == b"PNG"
        assert any(item.endswith("obs-1") for item in report.leftovers)

    def test_canonical_artifact_and_ambiguous_sources(self, tmp_path: Path) -> None:
        from molab.cli.migrate_cmd import migrate_knowledge
        from molab.workspace.refs import MolabRef

        root, experiment, run, workspace = _knowledge_workspace(tmp_path)
        with run.start() as ctx:
            artifact = ctx.emit_artifact({"ok": True}, name="trace.json")
        run_ref = str(MolabRef(experiment_id=experiment.id, run_id=run.id))
        experiment_ref = str(MolabRef(experiment_id=experiment.id))
        artifact_ref = str(
            MolabRef(experiment_id=experiment.id, run_id=run.id, artifact_id=artifact.id)
        )
        canonical = Path(experiment.resolve()) / "knowledges" / "finding-R.md"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(
            "---\n"
            "class: Finding\n"
            "sources:\n"
            f"- kind: run\n  ref: {run.id}\n"
            f"- kind: experiment\n  ref: {experiment.id}\n"
            "---\n\n"
            "[@derived_from seed=1](../runs/seed=1)\n",
            encoding="utf-8",
        )
        traced = root / "knowledges" / "traced.md"
        traced.parent.mkdir(parents=True, exist_ok=True)
        traced.write_text(
            "---\n"
            "class: Note\n"
            "sources:\n"
            f"- kind: artifact\n  ref: {artifact.id}\n"
            "- kind: artifact\n  ref: missing-artifact\n"
            "---\n\n"
            "# t\n",
            encoding="utf-8",
        )
        other = workspace.add_project("q").add_experiment("f")
        experiment.add_run(id="r1")
        other.add_run(id="r1")
        ambiguous = root / "ambiguous.md"
        ambiguous.write_text(
            "---\nclass: Note\nsources:\n- kind: run\n  ref: r1\n---\n\n# a\n",
            encoding="utf-8",
        )
        qualified = root / "qualified.md"
        qualified.write_text(
            "---\n"
            "class: Note\n"
            "sources:\n"
            f"- kind: experiment\n  ref: {experiment.id}\n"
            "- kind: run\n  ref: r1\n"
            "---\n\n"
            "# q\n",
            encoding="utf-8",
        )

        report = migrate_knowledge(root)

        text = canonical.read_text(encoding="utf-8")
        assert "sources:" not in text
        assert text.count(run_ref) == 1
        assert experiment_ref in text
        traced_text = traced.read_text(encoding="utf-8")
        assert artifact_ref in traced_text
        assert "missing-artifact" in traced_text
        assert any(label == "artifact:missing-artifact" for _doc, label in report.unresolved)
        ref_a = str(MolabRef(experiment_id=experiment.id, run_id="r1"))
        ref_b = str(MolabRef(experiment_id=other.id, run_id="r1"))
        ambiguous_text = (root / "knowledges" / "ambiguous.md").read_text(encoding="utf-8")
        assert ("knowledges/ambiguous.md", "run:r1", (ref_a, ref_b)) in report.ambiguous
        assert "ref: r1" in ambiguous_text
        qualified_text = (root / "knowledges" / "qualified.md").read_text(encoding="utf-8")
        assert ref_a in qualified_text
        assert not any(
            label == "run:r1" and doc.endswith("qualified.md")
            for doc, label, _candidates in report.ambiguous
        )

    def test_dry_run_matches_the_real_run_and_the_second_run_is_a_no_op(
        self, tmp_path: Path
    ) -> None:
        from molab.cli.migrate_cmd import migrate_knowledge

        root, experiment, run, _workspace = _knowledge_workspace(tmp_path)
        (root / "cooling-rate.md").write_text(
            "---\nclass: Note\n---\n\n"
            "From [@derived_from run](projects/p/experiments/e/runs/seed=1).\n",
            encoding="utf-8",
        )
        obs = Path(experiment.resolve()) / "knowledges" / "obs-1"
        obs.mkdir(parents=True)
        (obs / "observation.json").write_text(
            json.dumps(
                {
                    "created_by": "alice",
                    "sources": [
                        {"kind": "run", "ref": run.id},
                        {"kind": "experiment", "ref": experiment.id},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (obs / "index.md").write_text(
            "[cooling](../../../../../../cooling-rate.md)\n", encoding="utf-8"
        )
        before_hashes, before_paths = _snapshot(root)

        dry = migrate_knowledge(root, dry_run=True)

        assert _snapshot(root) == (before_hashes, before_paths)
        assert dry.commit is None
        real = migrate_knowledge(root)
        assert dry.moved == real.moved
        assert dry.links_rewritten == real.links_rewritten
        assert dry.sources_folded == real.sources_folded
        after = _snapshot(root)
        again = migrate_knowledge(root)
        assert again.changed is False
        assert again.commit is None
        assert _snapshot(root) == after

    def test_only_knowledge_verbs_write(self, tmp_path: Path) -> None:
        import inspect

        from molab.cli import migrate_cmd
        from molab.cli.migrate_cmd import migrate_knowledge
        from molab.knowledge.concept import Concept, remove_legacy_files

        root, _experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        (root / "cooling-rate.md").write_text("---\nclass: Note\n---\n\n# A\n", encoding="utf-8")
        refs = root / "references"
        refs.mkdir()
        (refs / "k1.md").write_text("---\nclass: Literature\n---\n\n# K\n", encoding="utf-8")
        moves: list[str] = []
        writes: list[str] = []
        real_move = Concept.move_to
        real_write = Concept.write

        def _move(self: Concept, *args: object, **kwargs: object) -> None:
            moves.append(str(self.path))
            real_move(self, *args, **kwargs)  # type: ignore[arg-type]

        def _write(self: Concept, *args: object, **kwargs: object) -> None:
            writes.append(str(self.path))
            real_write(self, *args, **kwargs)  # type: ignore[arg-type]

        Concept.move_to = _move  # type: ignore[method-assign]
        Concept.write = _write  # type: ignore[method-assign]
        try:
            migrate_knowledge(root)
        finally:
            Concept.move_to = real_move  # type: ignore[method-assign]
            Concept.write = real_write  # type: ignore[method-assign]

        assert len(moves) == 2
        assert writes
        assert all(path.endswith(".md") for path in writes)
        banned = (
            ".rename(",
            ".remove(",
            "write_text",
            "atomic_write_text",
            "unlink",
            "rmdir",
            "shutil",
        )
        blobs = [inspect.getsource(migrate_cmd.migrate_knowledge)]
        for name, obj in vars(migrate_cmd).items():
            if name.startswith("_knowledge_") and inspect.isfunction(obj):
                blobs.append(inspect.getsource(obj))
        blob = "\n".join(blobs)
        for token in banned:
            assert token not in blob
        assert "molab:" not in Path("src/molab/cli/migrate_cmd.py").read_text(encoding="utf-8")
        assert remove_legacy_files  # the verb the command is allowed to call

    def test_one_commit_leaves_unrelated_files_untracked(self, tmp_path: Path) -> None:
        import subprocess

        from molab.cli.migrate_cmd import migrate_knowledge
        from molab.workspace.history import GitHistory

        root, _experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        GitHistory(root).init()
        (root / "scratch.txt").write_text("leave me\n", encoding="utf-8")
        (root / "cooling-rate.md").write_text("---\nclass: Note\n---\n\n# A\n", encoding="utf-8")

        def _count() -> int:
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return 0
            return int(result.stdout.strip())

        before = _count()
        report = migrate_knowledge(root)
        message = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert _count() == before + 1
        assert "Molab-Event: knowledge.migrated" in message
        assert report.commit == head
        assert "scratch.txt" not in tracked.split()

    def test_a_non_root_path_is_refused(self, tmp_path: Path) -> None:
        import typer

        from molab.cli.migrate_cmd import migrate_knowledge

        root, experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        before = _snapshot(root)

        with pytest.raises(typer.BadParameter):
            migrate_knowledge(outside)
        with pytest.raises(typer.BadParameter):
            migrate_knowledge(Path(experiment.resolve()))

        assert _snapshot(root) == before


class TestMigrateKnowledgeCmd:
    def test_dry_run_prints_the_plan(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from molab.cli import app

        root, _experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        (root / "cooling-rate.md").write_text("---\nclass: Note\n---\n\n# A\n", encoding="utf-8")
        before = _snapshot(root)

        result = CliRunner().invoke(app, ["migrate", "knowledge", str(root), "--dry-run"])

        assert result.exit_code == 0
        assert "DRY-RUN" in result.stdout
        assert "cooling-rate.md -> knowledges/cooling-rate.md" in result.stdout
        assert _snapshot(root) == before

    def test_a_real_run_prints_counts(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from molab.cli import app

        root, _experiment, _run, _workspace = _knowledge_workspace(tmp_path)
        (root / "cooling-rate.md").write_text("---\nclass: Note\n---\n\n# A\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["migrate", "knowledge", str(root)])

        assert result.exit_code == 0
        assert "links rewritten:" in result.stdout
        assert "sources folded:" in result.stdout

    def test_a_non_workspace_exits_nonzero(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from molab.cli import app

        result = CliRunner().invoke(app, ["migrate", "knowledge", str(tmp_path / "missing")])

        assert result.exit_code != 0
