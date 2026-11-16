"""``staging.release_staged_run``: a remote run's namespace goes once its result is home.

Each remote run is staged into its own namespace under the target's scratch
root (``targets.target_run_dir``). Reconcile brings a succeeded attempt home
whole, so the namespace is then only a copy: it is deleted, unless another
attempt of the run is still active, the path is not a run namespace under the
scratch root, or the target is the workspace itself.
"""

from __future__ import annotations

from pathlib import Path

from molab.fs import LocalFS
from molab.plugins.submit_molq.staging import release_staged_run
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.history import AgentRef
from molab.workspace.models import ComputeTarget
from molab.workspace.run import Run
from molab.workspace.targets import target_run_dir

_AGENT = AgentRef(id="test", type="person", name="test")


def _setup(tmp_path: Path) -> tuple[Run, ComputeTarget, Path]:
    ws = Workspace(tmp_path / "ws")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e", params={}).add_run(params={"seed": 1})
    target = ComputeTarget(
        name="hpc", registry_id="reg", cluster_id="hpc", scratch_root=str(tmp_path / "remote")
    )
    staged = Path(target_run_dir(target, ws, run))
    (staged / "executions" / "e01" / "out").mkdir(parents=True)
    (staged / "executions" / "e01" / "out" / "traj.npz").write_bytes(b"x")
    return run, target, staged


def _attempt(run: Run, status: ExecutionStatus, *, executor: dict | None = None) -> str:
    repo = run._execution_repository()
    mode = ExecutionMode.RERUN if run.executions else ExecutionMode.INITIAL
    state = repo.create(mode=mode, created_by=_AGENT)
    if executor:
        repo.update_operational(state.id, executor=executor)
    if status is not ExecutionStatus.QUEUED:
        repo.start(state.id)
        repo.seal(state.id, status)
    return state.id


def _namespace(staged: Path, run: Run) -> Path:
    for parent in staged.parents:
        if parent.name == run.id:
            return parent
    raise AssertionError("no namespace")


def test_a_succeeded_run_namespace_is_deleted(tmp_path: Path) -> None:
    run, target, staged = _setup(tmp_path)
    neighbour = _namespace(staged, run).parent / "other-run"
    neighbour.mkdir()
    eid = _attempt(run, ExecutionStatus.SUCCEEDED)

    assert release_staged_run(LocalFS(), run, target, eid) is True
    assert not _namespace(staged, run).exists()
    assert neighbour.exists()


def test_another_active_attempt_keeps_the_namespace(tmp_path: Path) -> None:
    run, target, staged = _setup(tmp_path)
    eid = _attempt(run, ExecutionStatus.SUCCEEDED)
    _attempt(run, ExecutionStatus.QUEUED)

    assert release_staged_run(LocalFS(), run, target, eid) is False
    assert staged.exists()


def test_a_path_outside_the_scratch_root_is_refused(tmp_path: Path) -> None:
    run, target, _staged = _setup(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "projects" / "p" / "experiments" / "e" / "runs" / "seed=1"
    (elsewhere / "executions" / "e01").mkdir(parents=True)
    eid = _attempt(run, ExecutionStatus.SUCCEEDED, executor={"remote_run_dir": str(elsewhere)})

    assert release_staged_run(LocalFS(), run, target, eid) is False
    assert elsewhere.exists()


def test_a_local_target_is_never_touched(tmp_path: Path) -> None:
    run, _target, _staged = _setup(tmp_path)
    local = ComputeTarget(name="local", scratch_root=str(run.experiment.project.workspace.root))
    eid = _attempt(run, ExecutionStatus.SUCCEEDED)

    assert release_staged_run(LocalFS(), run, local, eid) is False
    assert Path(str(run.run_dir)).exists()


class _LocalTransport(LocalFS):
    """A target filesystem on the local disk, with the staging ``download``."""

    def download(
        self, remote: str, local: str, *, recursive: bool = False, exclude: tuple[str, ...] = ()
    ) -> None:
        import shutil
        from fnmatch import fnmatch

        del recursive
        shutil.copytree(
            remote,
            local,
            dirs_exist_ok=True,
            ignore=lambda _d, names: [n for n in names if any(fnmatch(n, p) for p in exclude)],
        )


def _remote_attempt(run: Run, target: ComputeTarget, status: ExecutionStatus) -> str:
    executor = {
        "backend": "molq",
        "target": target.name,
        "registry_id": target.registry_id,
        "cluster_id": target.cluster_id,
        "scratch_root": target.scratch_root,
    }
    return _attempt(run, status, executor=executor)


class TestBringHomeStagedRun:
    def test_a_failed_attempts_output_comes_home_and_the_namespace_goes(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.staging import bring_home_staged_run

        run, target, staged = _setup(tmp_path)
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: _LocalTransport())
        eid = _remote_attempt(run, target, ExecutionStatus.FAILED)

        assert bring_home_staged_run(run) is True
        assert (Path(run.execution_dir(eid)) / "out" / "traj.npz").read_bytes() == b"x"
        assert not _namespace(staged, run).exists()

    def test_a_pruned_tier_is_not_brought_back(self, monkeypatch, tmp_path: Path) -> None:
        from molab.plugins.submit_molq.staging import bring_home_staged_run

        run, target, staged = _setup(tmp_path)
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: _LocalTransport())
        eid = _remote_attempt(run, target, ExecutionStatus.FAILED)
        run._execution_repository().mark_pruned(eid, ("out",))

        assert bring_home_staged_run(run) is True
        assert not (Path(run.execution_dir(eid)) / "out").exists()
        assert not _namespace(staged, run).exists()

    def test_a_local_run_is_left_alone(self, tmp_path: Path) -> None:
        from molab.plugins.submit_molq.staging import bring_home_staged_run

        run, _target, staged = _setup(tmp_path)
        _attempt(run, ExecutionStatus.FAILED)

        assert bring_home_staged_run(run) is False
        assert staged.exists()

    def test_an_active_attempt_keeps_everything_remote(self, monkeypatch, tmp_path: Path) -> None:
        from molab.plugins.submit_molq.staging import bring_home_staged_run

        run, target, staged = _setup(tmp_path)
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: _LocalTransport())
        eid = _remote_attempt(run, target, ExecutionStatus.FAILED)
        _remote_attempt(run, target, ExecutionStatus.QUEUED)

        assert bring_home_staged_run(run) is False
        assert staged.exists()
        assert not (Path(run.execution_dir(eid)) / "out").exists()


def test_emptied_parents_go_up_to_the_scratch_root(tmp_path: Path) -> None:
    run, target, _staged = _setup(tmp_path)
    eid = _attempt(run, ExecutionStatus.SUCCEEDED)
    root = Path(target.scratch_root)
    (root / "other-workspace").mkdir()

    assert release_staged_run(LocalFS(), run, target, eid) is True
    assert root.exists()
    assert sorted(p.name for p in root.iterdir()) == ["other-workspace"]


def test_a_parent_with_another_run_stays(tmp_path: Path) -> None:
    run, target, staged = _setup(tmp_path)
    sibling = _namespace(staged, run).parent / "another-run"
    sibling.mkdir()
    eid = _attempt(run, ExecutionStatus.SUCCEEDED)

    assert release_staged_run(LocalFS(), run, target, eid) is True
    assert sibling.exists()
