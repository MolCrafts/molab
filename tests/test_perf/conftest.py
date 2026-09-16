"""Fixtures for the perf suite: a synthetic workspace written **directly**.

The layout is produced by writing the authoritative files with the real
pydantic models (``RunMetadata`` / ``RunOpsState`` / ``ArtifactAsset`` / …)
but *without* going through ``add_run`` — whose per-call children-index
rewrite is O(N²) and would take minutes at 10 000 runs. Everything written
here must parse back through ``Workspace(root)`` → ``list_projects`` →
``list_experiments`` → ``list_runs`` → ``run.read_ops()`` and through
``scan_assets``; :func:`test_fixture_parses_back` locks that.

Scale: ``MOLEXP_PERF_SCALE=small`` (5x4x10 = 200 runs, the default) or
``full`` (50x20x10 = 10 000 runs).

Two counters are available to the budget tests:

* ``counting_fs`` — a :class:`tests.support.counting_fs.CountingFileSystem`
  injected into ``Workspace(root, fs=…)``; counts every call that goes through
  the ``FileSystem`` seam (``open`` / ``exists`` / ``is_dir`` / ``stat`` …).
* ``audit`` — an OS-level collector fed by :func:`sys.addaudithook`
  (``open`` / ``os.listdir`` / ``os.scandir``). It sees *every* file open in
  the process — including code paths that bypass the fs seam (raw ``pathlib``
  in the asset scanner, the knowledge ``Bundle``, sqlite) — so "``assets.json``
  opened once" can be asserted regardless of routing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

try:
    from molexp.fs import LocalFileSystem
except ImportError:  # pre-extraction tree (baseline capture only)
    from molexp.workspace.fs_local import LocalFileSystem  # type: ignore[no-redef]
from molexp.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem

# ── scale ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scale:
    projects: int
    experiments: int
    runs: int

    @property
    def n_runs(self) -> int:
        return self.projects * self.experiments * self.runs

    @property
    def n_experiments(self) -> int:
        return self.projects * self.experiments


SCALES = {"small": Scale(5, 4, 10), "full": Scale(50, 20, 10)}


def current_scale() -> Scale:
    name = os.environ.get("MOLEXP_PERF_SCALE", "small")
    if name not in SCALES:
        raise ValueError(f"MOLEXP_PERF_SCALE must be one of {sorted(SCALES)}, got {name!r}")
    return SCALES[name]


# ── synthetic writer ────────────────────────────────────────────────────────

_STATUS_CYCLE = ("succeeded", "succeeded", "failed", "running", "pending", "cancelled")


def _versioned(payload: dict) -> str:
    from molexp.workspace.schema_version import MOLEXP_SCHEMA_VERSION

    return json.dumps({"schema_version": MOLEXP_SCHEMA_VERSION, **payload}, default=str)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _meta_yaml(directory: Path, kind: str, slug: str) -> None:
    _write(directory / "meta.yaml", yaml.safe_dump({"type": kind, "id": slug}, sort_keys=False))


def _index_row(slug: str, kind: str, created: datetime) -> dict:
    from molexp.workspace.models import FolderMetadata

    return FolderMetadata(
        id=slug, name=slug, kind=kind, created_at=created, updated_at=created
    ).model_dump(mode="json")


def _run_id(p: int, e: int, r: int) -> str:
    return hashlib.sha1(f"{p}/{e}/{r}".encode()).hexdigest()[:8]


@dataclass
class SynthLayout:
    """What the writer produced — ids the tests navigate by."""

    root: Path
    scale: Scale
    project_ids: list[str] = field(default_factory=list)
    experiment_ids: dict[str, list[str]] = field(default_factory=dict)  # project → experiments
    run_ids: dict[tuple[str, str], list[str]] = field(default_factory=dict)  # (p, e) → runs
    asset_ids: list[str] = field(default_factory=list)
    note_paths: list[Path] = field(default_factory=list)

    @property
    def first(self) -> tuple[str, str, str]:
        p = self.project_ids[0]
        e = self.experiment_ids[p][0]
        return p, e, self.run_ids[(p, e)][0]

    @property
    def n_runs(self) -> int:
        return sum(len(v) for v in self.run_ids.values())


def build_synth_workspace(
    root: Path,
    *,
    projects: int,
    experiments: int,
    runs: int,
    executions: int = 2,
    notes: bool = True,
    events: bool = True,
) -> SynthLayout:
    """Write a complete molexp workspace tree under *root* (see module docs)."""
    try:
        from molexp.knowledge.concepts import Note
        from molexp.knowledge.note_meta import NoteMeta
    except ImportError:  # pre-extraction tree (baseline capture only)
        from molexp.workspace.concepts import Note  # type: ignore[no-redef]
        from molexp.workspace.note_meta import NoteMeta  # type: ignore[no-redef]
    from molexp.workspace.assets.artifact import ArtifactAsset
    from molexp.workspace.assets.base import AssetScope, Producer
    from molexp.workspace.assets.manifest import SCHEMA_VERSION, _dump
    from molexp.workspace.folder import (
        WORKSPACE_EXPERIMENT_KIND,
        WORKSPACE_PROJECT_KIND,
        WORKSPACE_ROOT_KIND,
        WORKSPACE_RUN_KIND,
    )
    from molexp.workspace.metrics import MetricsWriter
    from molexp.workspace.models import (
        ExecutionMetadata,
        ExecutionRecord,
        ExperimentMetadata,
        ProjectMetadata,
        RunMetadata,
        WorkspaceMetadata,
    )
    from molexp.workspace.run_ops import RunOpsState

    scale = Scale(projects, experiments, runs)
    layout = SynthLayout(root=root, scale=scale)
    fs = LocalFileSystem()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    root.mkdir(parents=True, exist_ok=True)

    _write(
        root / "workspace.json",
        _versioned(
            WorkspaceMetadata(id="synth", name="synth", created_at=t0).model_dump(mode="json")
        ),
    )
    _meta_yaml(root, WORKSPACE_ROOT_KIND, "synth")
    _write(root / "assets.json", json.dumps({"schema_version": SCHEMA_VERSION, "assets": {}}))

    project_index: dict[str, dict] = {}
    previous_asset: str | None = None
    counter = 0
    event_rows: list[tuple[str, str, list[str]]] = []

    for p in range(projects):
        pid = f"proj-{p:02d}"
        pdir = root / "projects" / pid
        pmeta = ProjectMetadata(id=pid, name=pid, created_at=t0 + timedelta(minutes=p))
        _write(pdir / "project.json", _versioned(pmeta.model_dump(mode="json")))
        _meta_yaml(pdir, WORKSPACE_PROJECT_KIND, pid)
        _write(pdir / "assets.json", json.dumps({"schema_version": SCHEMA_VERSION, "assets": {}}))
        project_index[pid] = _index_row(pid, WORKSPACE_PROJECT_KIND, pmeta.created_at)
        layout.project_ids.append(pid)
        layout.experiment_ids[pid] = []
        experiment_index: dict[str, dict] = {}

        for e in range(experiments):
            eid = f"exp-{e:02d}"
            edir = pdir / "experiments" / eid
            emeta = ExperimentMetadata(
                id=eid,
                name=eid,
                created_at=t0 + timedelta(minutes=p, seconds=e),
                workflow_source="train.py",
                parameter_space={"lr": [1e-3, 1e-4]},
                git_commit="deadbeef",
            )
            _write(edir / "experiment.json", _versioned(emeta.model_dump(mode="json")))
            _meta_yaml(edir, WORKSPACE_EXPERIMENT_KIND, eid)
            _write(
                edir / "assets.json", json.dumps({"schema_version": SCHEMA_VERSION, "assets": {}})
            )
            experiment_index[eid] = _index_row(eid, WORKSPACE_EXPERIMENT_KIND, emeta.created_at)
            layout.experiment_ids[pid].append(eid)
            layout.run_ids[(pid, eid)] = []
            run_index: dict[str, dict] = {}

            for r in range(runs):
                rid = _run_id(p, e, r)
                rdir = edir / "runs" / f"run-{rid}"
                created = t0 + timedelta(minutes=p, seconds=e, milliseconds=r)
                status = _STATUS_CYCLE[counter % len(_STATUS_CYCLE)]
                counter += 1
                params = {"lr": 1e-3 if r % 2 else 1e-4, "seed": r}
                rmeta = RunMetadata(
                    id=rid,
                    parameters=params,
                    created_at=created,
                    config={"epochs": 10},
                    config_hash=hashlib.sha256(
                        json.dumps(params, sort_keys=True).encode()
                    ).hexdigest()[:16],
                    executor_info={"backend": "local", "hostname": "synth"},
                    profile="default",
                )
                _write(rdir / "run.json", _versioned(rmeta.model_dump(mode="json")))
                _meta_yaml(rdir, WORKSPACE_RUN_KIND, rid)
                run_index[rid] = _index_row(rid, WORKSPACE_RUN_KIND, created)
                layout.run_ids[(pid, eid)].append(rid)

                # executions: exec-<rid>, exec-<rid>-2, …
                exec_ids = [f"exec-{rid}"] + [f"exec-{rid}-{n}" for n in range(2, executions + 1)]
                records = []
                for k, xid in enumerate(exec_ids):
                    started = created + timedelta(seconds=10 * k)
                    last = k == len(exec_ids) - 1
                    xstatus = status if last else "failed"
                    finished = (
                        None
                        if (last and status in ("running", "pending"))
                        else started + timedelta(seconds=5)
                    )
                    records.append(
                        ExecutionRecord(
                            execution_id=xid,
                            started_at=started,
                            finished_at=finished,
                            status=xstatus,
                        )
                    )
                    xdir = rdir / "executions" / xid
                    _write(
                        xdir / "execution.json",
                        _versioned(
                            ExecutionMetadata(
                                execution_id=xid,
                                run_id=rid,
                                started_at=started,
                                finished_at=finished,
                                status=xstatus,
                                executor_info={"backend": "local"},
                            ).model_dump(mode="json")
                        ),
                    )
                    _write(xdir / "stdout.log", f"[{xid}] step 1\nstep 2\n")
                    _write(xdir / "stderr.log", "")
                ops = RunOpsState(
                    status=status,
                    owner_pid=os.getpid() if status == "running" else None,
                    owner_host="synth" if status == "running" else None,
                    started_at=None if status == "pending" else created,
                    finished_at=records[-1].finished_at,
                    heartbeat_at=datetime.now(UTC) if status == "running" else None,
                    current_execution_id=None if status == "pending" else exec_ids[-1],
                    executions=tuple(records),
                )
                _write(rdir / "_ops" / "run.json", json.dumps(ops.model_dump(mode="json")))

                # assets: two artifacts, the second consuming the first, and the
                # first consuming the previous run's second (a cross-run chain)
                scope = AssetScope(kind="run", ids=(pid, eid, rid))
                manifest: dict[str, dict] = {}
                a_ids = []
                for j, name in enumerate(("metrics.json", "summary.txt")):
                    aid = f"a{rid}{j}"
                    a_ids.append(aid)
                    target = rdir / "artifacts" / name
                    _write(target, json.dumps({"loss": 0.1 * r}) if j == 0 else f"run {rid}\n")
                    inputs: tuple[str, ...] = ()
                    if j == 1:
                        inputs = (a_ids[0],)
                    elif previous_asset is not None:
                        inputs = (previous_asset,)
                    asset = ArtifactAsset(
                        asset_id=aid,
                        name=name,
                        scope=scope,
                        path=Path("artifacts") / name,
                        created_at=created + timedelta(seconds=30 + j),
                        updated_at=created + timedelta(seconds=30 + j),
                        producer=Producer(
                            run_id=rid, execution_id=exec_ids[-1], task_id="train", inputs=inputs
                        ),
                        tags={"stage": "train"},
                        mime="application/json" if j == 0 else "text/plain",
                        size=target.stat().st_size,
                        content_hash="sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
                    )
                    manifest[aid] = _dump(asset)
                    layout.asset_ids.append(aid)
                previous_asset = a_ids[1]
                _write(
                    rdir / "assets.json",
                    json.dumps({"schema_version": SCHEMA_VERSION, "assets": manifest}),
                )

                writer = MetricsWriter(rdir)
                for step in range(100):
                    writer.scalar("loss", 1.0 / (step + 1), step)

                if events:
                    event_rows.append(("run.created", rid, [rid]))
                    if status != "pending":
                        event_rows.append(("run.started", rid, [rid]))
                    if status == "succeeded":
                        event_rows.append(("run.completed", rid, [rid]))
                    elif status == "failed":
                        event_rows.append(("run.failed", rid, [rid]))

                if notes and r == 0:
                    layout.note_paths.append(
                        _write_note(
                            rdir,
                            f"run-note-{rid}",
                            fs,
                            Note,
                            NoteMeta,
                            body=f"# Run {rid}\n\nObserved loss plateau.\n",
                        )
                    )

            _write(edir / "run.json", json.dumps(run_index))
            if notes and e == 0:
                layout.note_paths.append(
                    _write_note(
                        edir,
                        f"exp-note-{pid}-{eid}",
                        fs,
                        Note,
                        NoteMeta,
                        body="# Experiment notes\n\nSweep over lr.\n",
                    )
                )
        _write(pdir / "experiment.json", json.dumps(experiment_index))
        if notes and p == 0:
            layout.note_paths.append(
                _write_note(
                    pdir,
                    f"project-note-{pid}",
                    fs,
                    Note,
                    NoteMeta,
                    body="# Project\n\nGoals and 方法.\n",
                )
            )
    _write(root / "project.json", json.dumps(project_index))
    if notes:
        layout.note_paths.append(
            _write_note(root, "lab-wiki", fs, Note, NoteMeta, body="# Lab wiki\n\nConventions.\n")
        )

    if events and event_rows:
        from molexp.workspace.events import WorkspaceEventLog

        log = WorkspaceEventLog(root)
        for etype, rid, refs in event_rows:
            log.append(etype, "run-lifecycle", payload={"run_id": rid}, refs=refs)  # type: ignore[arg-type]
    return layout


def _write_note(
    host: Path, name: str, fs: LocalFileSystem, note_cls, meta_cls, *, body: str
) -> Path:
    """Write an OKF Note (``meta.yaml`` + ``index.md``) directly under *host*."""
    directory = host / name
    payload = meta_cls(
        tags=["synthetic", "perf"], timestamp=datetime(2026, 1, 1, tzinfo=UTC)
    ).model_dump(mode="json")
    payload["type"] = "note.note"
    payload["id"] = name
    _write(directory / "meta.yaml", yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    _write(directory / "index.md", body)
    return directory


# ── OS-level audit collector ────────────────────────────────────────────────


class AuditCollector:
    """Counts ``open`` (read-only) / ``os.listdir`` / ``os.scandir`` audit events.

    One hook is installed per process (they cannot be removed); collection is
    gated by :attr:`active` so the cost when idle is one attribute check.
    """

    def __init__(self) -> None:
        self.active = False
        self.opens: Counter[str] = Counter()  # basename → count
        self.open_paths: list[str] = []
        self.listings: list[str] = []  # dir paths listed via os.listdir / os.scandir
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.opens.clear()
            self.open_paths.clear()
            self.listings.clear()

    def hook(self, event: str, args: tuple) -> None:
        if not self.active:
            return
        if event == "open":
            path, mode, flags = args
            if isinstance(path, int) or path is None:
                return
            if mode is None:
                if flags & (os.O_WRONLY | os.O_RDWR):
                    return
            elif "r" not in str(mode) or "+" in str(mode):
                return
            spath = os.fspath(path) if not isinstance(path, str) else path
            with self._lock:
                self.opens[Path(str(spath)).name] += 1
                self.open_paths.append(str(spath))
        elif event in ("os.listdir", "os.scandir"):
            path = args[0] if args else None
            if path is None or isinstance(path, int):
                return
            with self._lock:
                self.listings.append(str(os.fspath(path)))

    def opens_of(self, basename: str) -> int:
        return self.opens[basename]

    def opens_under(self, fragment: str) -> int:
        return sum(1 for p in self.open_paths if fragment in p)

    def listings_under(self, fragment: str) -> int:
        return sum(1 for p in self.listings if fragment in p)

    @contextmanager
    def collect(self) -> Iterator[AuditCollector]:
        self.reset()
        self.active = True
        try:
            yield self
        finally:
            self.active = False


_AUDIT = AuditCollector()
sys.addaudithook(_AUDIT.hook)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def scale() -> Scale:
    return current_scale()


@pytest.fixture(scope="session")
def synth(tmp_path_factory: pytest.TempPathFactory, scale: Scale) -> SynthLayout:
    """The session-wide synthetic workspace (built once)."""
    root = tmp_path_factory.mktemp("synth-ws")
    return build_synth_workspace(
        root, projects=scale.projects, experiments=scale.experiments, runs=scale.runs
    )


@pytest.fixture
def counting_fs() -> CountingFileSystem:
    return CountingFileSystem(LocalFileSystem())


@pytest.fixture
def counting_workspace(synth: SynthLayout, counting_fs: CountingFileSystem) -> Workspace:
    """A **cold** Workspace over the synthetic root, routed through ``counting_fs``."""
    ws = Workspace(root=synth.root, fs=counting_fs)
    counting_fs.reset()
    return ws


@pytest.fixture
def plain_workspace(synth: SynthLayout) -> Workspace:
    return Workspace(root=synth.root)


@pytest.fixture
def audit() -> AuditCollector:
    _AUDIT.reset()
    return _AUDIT


@pytest.fixture(autouse=True)
def _isolate_molcrafts_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "_molcrafts_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MOLCRAFTS_HOME", str(fake_home))


def make_client(workspace: Workspace):
    from fastapi.testclient import TestClient

    from molexp.server.app import create_app
    from molexp.server.dependencies import get_workspace

    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: workspace
    return TestClient(app)


@pytest.fixture
def client(counting_workspace: Workspace):
    """FastAPI client whose ``get_workspace`` is the cold counting workspace."""
    return make_client(counting_workspace)


@pytest.fixture
def fs_reset(counting_fs: CountingFileSystem) -> Callable[[], None]:
    return counting_fs.reset
