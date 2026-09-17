"""Public context for one physical Execution of a logical Run."""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import traceback
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from molab._typing import JSONValue, TaskOutput
from molab.profile import ProfileConfig

from .artifact_repository import ArtifactRepository
from .domain import Artifact, Asset, Execution, ExecutionMode, ExecutionStatus
from .execution_dirs import (
    ARTIFACTS,
    CHECKPOINTS,
    OUT,
    WORK,
    ExecutionDir,
    list_execution_dirs,
    resolve_execution_dir,
)
from .execution_repository import ExecutionRepository
from .file_store import FileStore
from .history import AgentRef
from .metrics_seam import MetricRecord, MetricsSink, create_metrics_writer
from .schema_version import read_versioned_json, write_versioned_json

if TYPE_CHECKING:
    from types import TracebackType

    from .run import Run


def _system_agent() -> AgentRef:
    host = platform.node() or "local"
    return AgentRef(
        id=f"process:{host}:{os.getpid()}",
        type="system",
        name=f"Python {platform.python_version()} on {host}",
    )


class _BoundEvidenceLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = line if line.endswith("\n") else line + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def tail(self, n: int = 100) -> list[str]:
        if not self.path.exists():
            return []
        return self.path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


class _ExecutionLogs:
    """Execution evidence streams; these are deliberately not Artifacts."""

    def __init__(self, execution_dir: Path) -> None:
        self._execution_dir = execution_dir

    def __call__(self, name: str = "run") -> _BoundEvidenceLog:
        if name not in {"run", "stdout", "stderr"}:
            raise ValueError("Execution log name must be run, stdout, or stderr")
        return _BoundEvidenceLog(self._execution_dir / f"{name}.log")


class _CheckpointWriter:
    """A checkpoint is an explicitly emitted Artifact with checkpoint semantics."""

    def __init__(self, context: ExecutionContext) -> None:
        self._context = context

    def __call__(
        self,
        name: str | None = None,
        *,
        data: dict[str, JSONValue] | None = None,
        tags: dict[str, str] | None = None,
    ) -> Artifact:
        label = name or f"checkpoint-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
        path = self._context.get_dir(CHECKPOINTS.name) / f"{label}.json"
        path.write_text(
            json.dumps(
                {
                    "name": label,
                    "created_at": datetime.now(UTC).isoformat(),
                    "data": data or {},
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return self._context.emit_artifact(
            path,
            name=path.name,
            media_type="application/json",
            semantic_type="checkpoint",
            metadata=cast("dict[str, JSONValue]", {"tags": tags or {}}),
        )


class ExecutionContext:
    """Context manager for exactly one new or preallocated Execution.

    Run is immutable scientific intent. Operational state, evidence, results,
    heartbeat, workflow state, and emitted outputs all live below this
    Execution's physical directory.
    """

    def __init__(
        self,
        run: Run,
        *,
        profile_config: ProfileConfig | None = None,
        execution_id: str | None = None,
        mode: ExecutionMode = ExecutionMode.INITIAL,
        based_on_execution_id: str | None = None,
        checkpoint_artifact_id: str | None = None,
        created_by: AgentRef | None = None,
    ) -> None:
        self.run = run
        self.run_dir = Path(run.run_dir)
        self._profile_config = profile_config or ProfileConfig({}, name=None)
        self._explicit_execution_id = execution_id
        self._execution_id: str | None = None
        self._mode = mode
        self._based_on_execution_id = based_on_execution_id
        self._checkpoint_artifact_id = checkpoint_artifact_id
        self._created_by = created_by or _system_agent()
        self._state: Execution | None = None
        self._active_task_id: str | None = None
        self._failure: dict[str, JSONValue] | None = None
        self._terminal_override: ExecutionStatus | None = None
        self._workflow_succeeded = False
        self._entered = False
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._metrics: MetricsSink | None = None
        workspace = run.experiment.project.workspace
        self._artifacts = ArtifactRepository(workspace.root, fs=workspace.fs)
        self._executions = ExecutionRepository(
            workspace.root,
            run.run_dir,
            run_id=run.id,
            project_id=run.experiment.project.id,
            fs=workspace.fs,
            artifacts=self._artifacts,
        )

    @property
    def id(self) -> str:
        if self._execution_id is None:
            raise RuntimeError("ExecutionContext has not been entered")
        return self._execution_id

    @property
    def execution_dir(self) -> Path:
        return self.run_dir / "executions" / self.id

    @property
    def based_on_execution_id(self) -> str | None:
        """Selected predecessor for retry/resume/reproduction provenance."""
        return self._state.based_on_execution_id if self._state is not None else None

    def get_dir(self, name: str, *parts: str) -> Path:
        """One of this attempt's directories, created on demand.

        Peers: ``get_dir("work")`` and ``get_dir("artifacts")`` differ in
        what they promise, never in how you reach them. An undeclared name
        raises rather than creating a directory nothing validates.
        """
        resolve_execution_dir(name)
        path = self.execution_dir.joinpath(name, *parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def has_dir(self, name: str) -> bool:
        """True when this attempt has actually created *name* on disk."""
        return (self.execution_dir / name).is_dir()

    def list_dirs(self) -> tuple[ExecutionDir, ...]:
        """Every declared directory and what it promises."""
        return list_execution_dirs()

    @property
    def files(self) -> FileStore:
        return FileStore(self.get_dir(WORK.name), fs=self.run._disk())

    @property
    def params(self) -> dict[str, JSONValue]:
        return self.run.parameters

    @property
    def config(self) -> ProfileConfig:
        return self._profile_config

    @property
    def log(self) -> _ExecutionLogs:
        return _ExecutionLogs(self.execution_dir)

    @property
    def checkpoint(self) -> _CheckpointWriter:
        return _CheckpointWriter(self)

    @property
    def metrics(self) -> MetricsSink:
        if self._metrics is None:
            # Into the versioned tier: a metrics WAL is small and is the
            # record of what the run measured. Appended through a store
            # rooted at the attempt so the tier is part of the path.
            store = FileStore(self.execution_dir, fs=self.run._disk())
            self._metrics = create_metrics_writer(
                self.execution_dir,
                lambda name, line: store.append(Path(ARTIFACTS.name) / name, line),
            )
        return self._metrics

    def task_workdir(self, task_name: str) -> Path:
        """Where one workflow task writes: ``out/<task>/``.

        The bulk tier, not scratch. What a task body writes is genuinely
        mixed — the inputs it generated, its intermediates, and the
        trajectory — and those cannot be separated from outside the body.
        They land in the tier that is *kept*; anything worth citing is then
        promoted into ``artifacts/`` by ``register_artifact``.

        ``work/`` is left to the framework's own scratch (plan boards,
        harness staging), which is genuinely disposable.
        """
        return self.get_dir(OUT.name, task_name)

    def set_active_task(self, task_id: str | None) -> None:
        self._active_task_id = task_id

    def __enter__(self) -> ExecutionContext:
        if self._entered:
            raise RuntimeError("ExecutionContext cannot be entered twice")
        state: Execution
        if self._explicit_execution_id is not None:
            try:
                state = self._executions.get(self._explicit_execution_id)
            except KeyError:
                state = self._create(self._explicit_execution_id)
            else:
                if state.status is not ExecutionStatus.QUEUED:
                    raise ValueError(
                        f"preallocated Execution {state.id!r} is {state.status.value}, not queued"
                    )
        else:
            state = self._create(None)
        self._state = self._executions.start(state.id)
        self._execution_id = state.id
        self._prepare_execution_files()
        self.log("run").append(
            f"{datetime.now(UTC).isoformat()} execution started mode={state.mode.value}"
        )
        self._entered = True
        self._start_heartbeat()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        self._stop_heartbeat()
        self._remove_heartbeat()
        if exc_type is not None and self._terminal_override is None:
            self._write_exception(exc_type, exc_val, exc_tb)
        status = self._terminal_override or (
            ExecutionStatus.FAILED
            if exc_type is not None or self._failure is not None
            else ExecutionStatus.SUCCEEDED
        )
        if self._metrics is not None:
            self._metrics.flush()
            metrics_path = self.get_dir(ARTIFACTS.name) / "metrics.mlp.jsonl"
            if metrics_path.is_file():
                self.emit_artifact(
                    metrics_path,
                    media_type="application/x-ndjson",
                    semantic_type="molplot.metrics",
                )
        self.log("run").append(
            f"{datetime.now(UTC).isoformat()} execution finished status={status.value}"
        )
        self._executions.seal(self.id, status, error=self._failure)
        self._entered = False
        return False

    async def __aenter__(self) -> ExecutionContext:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)

    def emit_artifact(
        self,
        data: object,
        *,
        name: str | None = None,
        media_type: str | None = None,
        mime: str | None = None,
        semantic_type: str | None = None,
        declaration_id: str | None = None,
        metadata: dict[str, JSONValue] | None = None,
        tags: dict[str, str] | None = None,
        consumed: Sequence[Artifact | Asset | str] | None = None,
    ) -> Artifact:
        """Explicitly snapshot an observed output; declarations never call this."""
        if not self._entered:
            raise RuntimeError("emit_artifact must be called inside an ExecutionContext")
        source: Path
        if isinstance(data, Path):
            source = data
        elif isinstance(data, str) and Path(data).exists():
            source = Path(data)
        else:
            if name is None:
                raise ValueError("emit_artifact requires name for in-memory data")
            source = self.get_dir(WORK.name) / name
            source.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, (bytes, bytearray)):
                source.write_bytes(bytes(data))
            elif isinstance(data, (dict, list)):
                source.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            else:
                source.write_text(str(data), encoding="utf-8")
        inputs = tuple(self._entity_id(item) for item in (consumed or ()))
        combined_metadata: dict[str, JSONValue] = dict(metadata or {})
        if tags:
            combined_metadata["tags"] = cast("JSONValue", dict(tags))
        if self._active_task_id:
            combined_metadata["task_id"] = self._active_task_id
        if inputs:
            self._executions.add_observed_inputs(self.id, inputs)
        artifact = self._artifacts.emit(
            source,
            execution_dir=self.execution_dir,
            execution_id=self.id,
            run_id=self.run.id,
            project_id=self.run.experiment.project.id,
            created_by=self._created_by,
            name=name,
            media_type=media_type or mime,
            semantic_type=semantic_type,
            declaration_id=declaration_id,
            input_entity_ids=inputs,
            metadata=combined_metadata,
        )
        self._executions.add_artifact(self.id, artifact)
        return artifact

    def register_metric(
        self,
        key: str,
        value: float,
        *,
        step: int | None = None,
        tags: dict[str, str] | None = None,
    ) -> MetricRecord:
        return self.metrics.scalar(key, value, step, tags=cast("dict[str, JSONValue] | None", tags))

    def set_result(self, key: str, value: TaskOutput) -> None:
        results = self._read_results()
        results[key] = value
        write_versioned_json(self.execution_dir / "results.json", {"results": results})

    def get_result(self, key: str) -> TaskOutput:
        return self._read_results().get(key)

    def set_workflow(self, workflow: BaseModel | dict[str, JSONValue]) -> None:
        value = workflow.model_dump(mode="json") if isinstance(workflow, BaseModel) else workflow
        write_versioned_json(self.execution_dir / "workflow.json", {"workflow": value})

    def mark_failed(self, error: str | None = None, traceback_text: str | None = None) -> None:
        if self._failure is not None:
            return
        self._failure = {
            "type": "WorkflowError",
            "message": error or "workflow failed",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if traceback_text:
            (self.execution_dir / "traceback.txt").write_text(traceback_text, encoding="utf-8")
        (self.execution_dir / "exception.json").write_text(
            json.dumps(self._failure, indent=2, sort_keys=True), encoding="utf-8"
        )

    def mark_succeeded(self) -> None:
        if self._failure is None:
            self._workflow_succeeded = True

    def mark_interrupted(self, reason: str | None = None) -> None:
        """Settle this attempt as an intentional, resumable interruption.

        Approval gates and external preemption are history, but not failures.
        The reason is runtime evidence only; it does not mutate the Run.
        """
        self._terminal_override = ExecutionStatus.INTERRUPTED
        if reason:
            self.log("run").append(f"interrupted: {reason}")

    def _create(self, execution_id: str | None) -> Execution:
        environment: dict[str, JSONValue] = {
            "python": sys.version,
            "platform": platform.platform(),
            "host": platform.node(),
            "pid": os.getpid(),
            "profile": self._profile_config.name,
            "config": self._profile_config.to_dict(),
            "config_hash": (
                self._profile_config.content_hash()
                if len(self._profile_config) > 0 or self._profile_config.name
                else None
            ),
        }
        return self._executions.create(
            mode=self._mode,
            created_by=self._created_by,
            execution_id=execution_id,
            based_on_execution_id=self._based_on_execution_id,
            checkpoint_artifact_id=self._checkpoint_artifact_id,
            executor={"kind": "local", "host": platform.node(), "pid": os.getpid()},
            environment=environment,
        )

    def _prepare_execution_files(self) -> None:
        """Make the attempt's two directories. Its state is already one file."""
        self.execution_dir.mkdir(parents=True, exist_ok=True)
        self.get_dir(OUT.name)

    def _write_exception(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._failure is None:
            self._failure = {
                "type": exc_type.__name__,
                "message": str(exc_val),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        # The failure is carried on the Execution itself (sealed into
        # ``execution.json``); only the traceback text is too big for a field,
        # and it belongs in the attempt's one log.
        self.log("run").append("".join(traceback.format_exception(exc_type, exc_val, exc_tb)))

    def _read_results(self) -> dict[str, TaskOutput]:
        path = self.execution_dir / "results.json"
        if not path.exists():
            return {}
        raw = read_versioned_json(path)
        results = raw.get("results")
        return results if isinstance(results, dict) else {}

    @staticmethod
    def _entity_id(value: Artifact | Asset | str) -> str:
        if isinstance(value, str):
            return value
        return value.id

    def _heartbeat_path(self) -> Path:
        return self.execution_dir / "alive"

    def _start_heartbeat(self) -> None:
        self._heartbeat_path().touch()
        stop = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop,),
            name=f"molab-execution-heartbeat-{self.id}",
            daemon=True,
        )
        self._heartbeat_stop = stop
        self._heartbeat_thread = thread
        thread.start()

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        while not stop.wait(30):
            self._heartbeat_path().touch(exist_ok=True)

    def _remove_heartbeat(self) -> None:
        self._heartbeat_path().unlink(missing_ok=True)


RunContext = ExecutionContext

__all__ = ["ExecutionContext", "RunContext"]
