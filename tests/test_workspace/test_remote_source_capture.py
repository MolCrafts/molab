"""Source capture for a workspace reached through a remote filesystem.

The workspace is a real tree served by molq's local Shell destination and
opened through ``RemoteFS``. It is reached through a symlinked path, the way
macOS reaches ``/home/...`` (``/System/Volumes/Data/home/...`` once resolved
locally): resolving a remote path on this machine names another directory, so
the capture must use the workspace filesystem's own path rules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.fs_remote import RemoteFS
from molab.workspace.run import Run


def _remote_run(molq_destination, tmp_path: Path, *, entrypoint: str | None = None) -> Run:
    """A code experiment with ``workflow.py`` importing ``helper.py``, opened remotely."""
    client, _registry, cluster, root = molq_destination
    local = Workspace(root / "ws", name="lab")
    local.materialize()
    experiment = local.add_project("p").add_experiment("e")
    directory = Path(str(experiment.resolve()))
    (directory / "workflow.py").write_text("import helper\nwf = None\n", encoding="utf-8")
    (directory / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    experiment.bind_workflow("code", entrypoint=entrypoint or f"{directory}/workflow.py:wf")
    local.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "tree"],
    ):
        subprocess.run(
            ["git", "-C", str(root / "ws"), *args], check=True, capture_output=True, timeout=30
        )

    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    remote = Workspace(str(alias / "ws"), fs=RemoteFS(client, cluster, str(alias)))
    [run] = remote.get_project("p").get_experiment("e").list_runs()
    return run


class TestRemoteSourceCapture:
    def test_the_attempt_captures_its_source_through_the_workspace_filesystem(
        self, molq_destination, tmp_path: Path
    ) -> None:
        run = _remote_run(molq_destination, tmp_path)

        record = run._create_execution()

        assert record.source is not None
        assert [item.name for item in record.source.files] == ["workflow.py", "helper.py"]
        assert record.source.locator.startswith(str(tmp_path / "alias")), record.source.locator
        root = molq_destination[3]
        attempt = next(root.rglob(f"executions/{record.id}"))
        assert (attempt / "source" / "helper.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    def test_the_git_state_of_a_remote_tree_is_unknown(
        self, molq_destination, tmp_path: Path
    ) -> None:
        run = _remote_run(molq_destination, tmp_path)

        record = run._create_execution()

        # The tree is a git repository on this machine too; a remote path is
        # never handed to the local git.
        assert record.source is not None
        assert record.source.vcs_commit is None
        assert record.source.vcs_dirty is None

    def test_a_missing_script_fails_before_any_record_exists(
        self, molq_destination, tmp_path: Path
    ) -> None:
        run = _remote_run(molq_destination, tmp_path)
        script = next(molq_destination[3].rglob("experiments/e/workflow.py"))
        script.unlink()

        with pytest.raises(FileNotFoundError):
            run._create_execution()
        assert run.executions == []

    def test_a_script_outside_the_workspace_is_refused_before_any_record_exists(
        self, molq_destination, tmp_path: Path
    ) -> None:
        from molab.workspace.source_snapshot import SourceCaptureError

        outside = tmp_path / "elsewhere.py"
        outside.write_text("wf = None\n", encoding="utf-8")
        run = _remote_run(molq_destination, tmp_path, entrypoint=f"{outside}:wf")

        with pytest.raises(SourceCaptureError, match="outside the workspace"):
            run._create_execution()
        assert run.executions == []


class TestRemoteValidatorImportCheck:
    def test_a_module_the_script_imports_is_shipped_source(
        self, molq_destination, tmp_path: Path
    ) -> None:
        from molab.workspace.entity_record import read_record
        from molab.workspace.validate import experiment_source_names

        run = _remote_run(molq_destination, tmp_path)
        experiment = run.experiment
        fs = experiment.workspace.fs
        directory = str(experiment.resolve())
        canonical = read_record(fs, directory).canonical

        names = experiment_source_names(fs, directory, canonical)

        assert names == frozenset({"workflow.py", "helper.py"})
