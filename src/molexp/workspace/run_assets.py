"""``RunAssets`` — RunContext's working-dir + asset-I/O facade.

Tier-3 collaborator of :class:`~molexp.workspace.run.RunContext` (see the
``workspace-slim-03-runcontext`` decomposition). Bundles the asset scope,
manifest, the typed accessors (``artifact`` / ``log`` /
``checkpoint`` / ``metrics``), the data-asset import/lookup verbs, the
execution scratch-directory helper, and error-trace persistence — every
"do I/O against this run's assets" entry point in one place.

The producer identity and active execution id are transient lifecycle
state owned by the facade, so they are injected as callables
(``producer`` / ``get_execution_id``) rather than copied.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .assets import (
    ArtifactAsset,
    Asset,
    AssetManifest,
    AssetScope,
    CheckpointAccessor,
    CheckpointAsset,
    ErrorTraceAsset,
    LogAccessor,
    LogAsset,
    Producer,
)
from .assets.base import AssetKind
from .execution_dirs import (
    ARTIFACTS,
    OUT,
    ExecutionDir,
    list_execution_dirs,
    resolve_execution_dir,
)
from .file_store import FileStore
from .metrics_seam import MetricsSink, create_metrics_writer
from .utils import compute_content_hash, generate_asset_id

if TYPE_CHECKING:
    from .run import Run


class RunAssets:
    """Working-directory + asset-access surface for one run execution."""

    def __init__(
        self,
        run: Run,
        work_dir: Path,
        scope: AssetScope,
        producer: Callable[[], Producer],
        get_execution_id: Callable[[], str | None],
    ) -> None:
        self._run = run
        self._run_dir = work_dir
        self._scope = scope
        self._producer = producer
        self._get_execution_id = get_execution_id
        self.files = FileStore(work_dir, fs=run._disk())
        self._manifest: AssetManifest | None = None
        self._log: LogAccessor | None = None
        self._checkpoint: CheckpointAccessor | None = None
        self._metrics: MetricsSink | None = None

    def _exec_rel(self) -> Path:
        execution_id = self._get_execution_id()
        if execution_id is None:
            raise RuntimeError(
                "RunAssets requires an active execution; call it inside `with run.start() as ctx:`."
            )
        return Path("executions") / execution_id

    def _execution_dir(self) -> Path:
        return self._run_dir / self._exec_rel()

    def _bind(self) -> None:
        if self._manifest is not None:
            return
        exec_dir = self._execution_dir()
        exec_dir.mkdir(parents=True, exist_ok=True)
        rel = self._exec_rel()
        self._manifest = AssetManifest(exec_dir, fs=self._run._disk())
        self._log = LogAccessor(
            self._run_dir,
            self._scope,
            self._manifest,
            self._producer,
            self._get_execution_id,
            files=self.files,
        )
        self._checkpoint = CheckpointAccessor(
            self._run_dir,
            self._scope,
            self._manifest,
            self._producer,
            files=self.files,
            execution_id_provider=self._get_execution_id,
        )
        self._metrics = create_metrics_writer(
            exec_dir,
            lambda name, line: self.files.append(rel / ARTIFACTS.name / name, line),
        )

    @property
    def log(self) -> LogAccessor:
        self._bind()
        assert self._log is not None
        return self._log

    @property
    def checkpoint(self) -> CheckpointAccessor:
        self._bind()
        assert self._checkpoint is not None
        return self._checkpoint

    @property
    def metrics(self) -> MetricsSink:
        self._bind()
        assert self._metrics is not None
        return self._metrics

    # ── The attempt's directories ───────────────────────────────────────

    def get_dir(self, name: str, *parts: str) -> Path:
        """One of this attempt's directories, created on demand.

        The single way to reach any of them — ``get_dir("work")`` for
        scratch, ``get_dir("out")`` for bulk output, ``get_dir("artifacts")``
        for promoted products. They are peers: what each promises is its
        :class:`~molexp.workspace.execution_dirs.ExecutionDir` declaration,
        not a bespoke property here.

        Requires an active execution (``with run.start() as ctx:``), and
        refuses a name nobody declared.
        """
        resolve_execution_dir(name)
        execution_id = self._get_execution_id()
        if execution_id is None:
            raise RuntimeError(
                f"RunContext.get_dir({name!r}) requires an active execution; "
                "call it inside `with run.start() as ctx:`."
            )
        return self.files.mkdir(Path("executions", execution_id, name, *parts))

    def has_dir(self, name: str) -> bool:
        """True when this attempt has actually created *name* on disk."""
        execution_id = self._get_execution_id()
        if execution_id is None:
            return False
        return (self._run_dir / "executions" / execution_id / name).is_dir()

    def list_dirs(self) -> tuple[ExecutionDir, ...]:
        """Every declared directory and what it promises."""
        return list_execution_dirs()

    def task_workdir(self, task_name: str) -> Path:
        """Where one workflow task writes: ``out/<task>/``.

        The bulk tier, not scratch — what a body writes mixes intermediates
        with the trajectory, and the two cannot be told apart from outside.
        Kept as named sugar because the workflow engine reaches it through
        the ``RunContextLike`` protocol to build ``TaskContext.workdir``.
        """
        return self.get_dir(OUT.name, task_name)

    def get_data_dir(
        self,
        asset_name: str,
        *,
        fallback: str | Path | None = None,
    ) -> Path:
        """Resolve a data directory path.

        Searches the asset hierarchy first. If no asset is found and
        *fallback* is given, creates ``workspace_root / fallback`` and
        returns it.  All return values are :class:`~pathlib.Path`.

        Args:
            asset_name: Name of the asset to look up.
            fallback: Relative path under workspace root to create when the
                asset is not found.

        Returns:
            Resolved data directory path.

        Raises:
            FileNotFoundError: If no asset found and no fallback specified.
        """
        asset = self.find_asset(asset_name)
        if asset is not None:
            return Path(asset.path)
        if fallback is not None:
            fallback = Path(fallback)
            data_dir = Path(self._run.experiment.project.workspace.root) / fallback
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir
        raise FileNotFoundError(f"Asset {asset_name!r} not found and no fallback specified.")

    # ── Catalog ─────────────────────────────────────────────────────────

    def register_product(
        self,
        src: Path | str | None = None,
        *,
        name: str | None = None,
        tags: dict[str, str] | None = None,
        mime: str | None = None,
    ) -> Path:
        """Register a file this run produced as a run artifact.

        ``register_product(name="nve.pt")`` returns
        ``<run>/artifacts/nve.pt`` (parent created) so the task can write
        there. ``register_product(src)`` copies *src* into that directory
        if needed and records it on the run manifest.
        """
        path = Path(src) if src is not None else None
        dest_name = name or (path.name if path is not None else None)
        if dest_name is None:
            raise ValueError("register_product requires src or name")
        dest = self._run_dir / self._exec_rel() / ARTIFACTS.name / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path is None:
            return dest
        if not path.is_file():
            raise FileNotFoundError(f"register_product: {path} is not a file")
        asset = self.register_artifact(path, name=dest_name, tags=tags, mime=mime)
        return self._run_dir / asset.path

    def register(
        self,
        path: Path,
        *,
        kind: AssetKind = "artifact",
        name: str | None = None,
        mime: str | None = None,
        tags: dict[str, str] | None = None,
        consumed: Sequence[Asset | str] | None = None,
        **extra: object,
    ) -> Asset:
        """Catalog an existing file. Does not copy or rewrite the payload."""
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"register: not a file: {path}")
        root = self._run_dir.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"register: path {path} is not under run_dir {root}")
        rel = resolved.relative_to(root)
        now = datetime.now()
        producer = self._producer()
        if consumed:
            ids = tuple(item if isinstance(item, str) else item.asset_id for item in consumed)
            producer = producer.model_copy(update={"inputs": ids})
        label = name or resolved.name
        asset: Asset
        if kind == "artifact":
            asset = ArtifactAsset(
                asset_id=generate_asset_id(),
                name=label,
                scope=self._scope,
                path=rel,
                created_at=now,
                updated_at=now,
                producer=producer,
                tags=tags or {},
                mime=mime,
                size=resolved.stat().st_size,
                content_hash=compute_content_hash(resolved),
            )
        elif kind == "log":
            asset = LogAsset(
                asset_id=generate_asset_id(),
                name=label,
                scope=self._scope,
                path=rel,
                created_at=now,
                updated_at=now,
                producer=producer,
                tags=tags or {},
            )
        elif kind == "checkpoint":
            ckpt_id = str(extra.get("ckpt_id") or label)
            parent = extra.get("parent_ckpt_id")
            asset = CheckpointAsset(
                asset_id=generate_asset_id(),
                name=label,
                scope=self._scope,
                path=rel,
                created_at=now,
                updated_at=now,
                producer=producer,
                tags=tags or {},
                ckpt_id=ckpt_id,
                parent_ckpt_id=str(parent) if parent is not None else None,
            )
        elif kind == "error_trace":
            asset = ErrorTraceAsset(
                asset_id=generate_asset_id(),
                name=label,
                scope=self._scope,
                path=rel,
                created_at=now,
                updated_at=now,
                producer=producer,
                tags=tags or {},
                exception_type=str(extra.get("exception_type") or "Error"),
                message=str(extra.get("message") or ""),
                execution_id=str(extra.get("execution_id") or "unbound"),
            )
        elif kind == "data":
            raise ValueError("register: kind='data' uses data_assets.import_asset")
        else:
            raise ValueError(f"register: unknown kind {kind!r}")
        self._bind()
        manifest = self._manifest
        if manifest is None:
            raise RuntimeError("asset manifest is not bound")
        manifest.register(asset)
        return asset

    def register_artifact(
        self,
        data: object,
        *,
        name: str | None = None,
        mime: str | None = None,
        tags: dict[str, str] | None = None,
        consumed: Sequence[Asset | str] | None = None,
    ) -> ArtifactAsset:
        if name is None:
            if isinstance(data, Path):
                name = Path(data).name
            else:
                raise ValueError("register_artifact: name is required when data is not a Path")
        payload: Path | bytes | dict | list | str
        if isinstance(data, (Path, bytes, dict, list, str)):
            payload = data
        elif isinstance(data, bytearray):
            payload = bytes(data)
        else:
            payload = str(data)
        dest = self.files.put(self._exec_rel() / ARTIFACTS.name / name, payload)
        asset = self.register(
            dest, kind="artifact", name=name, mime=mime, tags=tags, consumed=consumed
        )
        assert isinstance(asset, ArtifactAsset)
        return asset

    def get_asset(self, name: str, scope: str = "project"):  # noqa: ANN201
        if scope == "experiment":
            return self._run.experiment.data_assets.get(name)
        if scope == "project":
            return self._run.experiment.project.data_assets.get(name)
        if scope == "workspace":
            return self._run.experiment.project.workspace.data_assets.get(name)
        raise ValueError(f"Unknown scope: {scope!r}")

    def find_asset(self, name: str):  # noqa: ANN201
        for scope in ("experiment", "project", "workspace"):
            asset = self.get_asset(name, scope=scope)
            if asset is not None:
                return asset
        return None

    # ── Run log + error trace ───────────────────────────────────────────

    def append_run_log(self, message: str) -> None:
        """Append a single timestamped line to the ``run`` LogAsset."""
        ts = datetime.now().isoformat(timespec="seconds")
        self.log("run").append(f"{ts}  {message}")

    def save_error_details(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        """Persist an ``ErrorTraceAsset`` for an exception that propagated."""
        tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
        self.save_error_report(
            error_type=exc_type.__name__,
            message=str(exc_val),
            traceback_text="".join(tb_lines),
        )

    def save_error_report(
        self,
        *,
        error_type: str,
        message: str,
        traceback_text: str | None = None,
    ) -> None:
        """Persist ``executions/<exec_id>/error.txt`` + its ``ErrorTraceAsset``.

        Shared by both failure paths: an exception that propagated out of the
        ``with run.start():`` block (:meth:`save_error_details` supplies the
        traceback) and the far more common engine-swallowed task failure,
        where the workflow engine resolves the run to FAILED via
        ``mark_failed`` without re-raising — the runtime forwards the
        formatted task traceback through ``mark_failed(..., traceback_text=…)``
        and the lifecycle passes it here, so error.txt carries the real stack.
        The placeholder note below survives only for failure signals that
        genuinely carried no traceback (e.g. a manual ``mark_failed("msg")``).
        """
        exec_id = self._get_execution_id() or "unbound"
        rel_path = Path("executions") / exec_id / "error.txt"
        body = f"Error: {datetime.now().isoformat()}\nType: {error_type}\nMessage: {message}\n\n"
        if traceback_text:
            body += traceback_text
        else:
            body += (
                "(No Python traceback was captured: the workflow engine recorded "
                "this task failure without re-raising. Per-task detail lives in "
                f"executions/{exec_id}/workflow.json and logs/.)\n"
            )
        target = self.files.put(rel_path, body)
        self.register(
            target,
            kind="error_trace",
            name=f"error_{exec_id}",
            exception_type=error_type,
            message=message,
            execution_id=exec_id,
        )
