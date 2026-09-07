"""Plan bundle — ``compose_plan`` + plan workflow.

:class:`Plan` is an object that composes plugins. It is not a Mode kernel
and does not subclass an Agent.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mollog import get_logger

from molexp.harness.errors import ApprovalPendingError, StageExecutionError
from molexp.harness.host.compose import compose_plan
from molexp.harness.host.keys import Keys
from molexp.harness.host.plugins.tools import ToolBelt
from molexp.harness.plan import FROZEN_PLAN_KIND
from molexp.harness.plan.disk_board import DiskTaskBoard
from molexp.harness.plan_tools import BOARD_TOOLS, as_loop_tool
from molexp.harness.schemas import ModeResult
from molexp.harness.stages.plan_reachability_probe import PlanReachabilityProbe
from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.workspace.domain import ExecutionMode, ExecutionStatus

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from molexp.harness.executors import Executor
    from molexp.harness.gateways.gateway import AgentGateway
    from molexp.harness.host.host import Host
    from molexp.harness.host.plugin import Plugin
    from molexp.harness.modes.plan_workflow import PlanDraft
    from molexp.harness.registry.capability_registry import CapabilityRegistry
    from molexp.harness.schemas import PlanArtifactRef, WorkflowSource
    from molexp.harness.stages.approval_gate import Approver
    from molexp.workspace.experiment import Experiment
    from molexp.workspace.run import Run

    LoopEventObserver = Callable[[object], Awaitable[None]]

_LOG = get_logger(__name__)

__all__ = ["Plan"]

_PLAN_NAME = "plan"
_TITLE_SEPARATORS = ("，", "。", "；", ",", ";", ".", "?", "？", "!", "：", ":")  # noqa: RUF001


def _as_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return {}


def _short_plan_title(text: str, *, max_len: int = 72) -> str:
    first = (text.splitlines()[0] if text else "").strip() or "experiment"
    for sep in _TITLE_SEPARATORS:
        if sep in first:
            head = first.split(sep, 1)[0].strip()
            if len(head) >= 2 and head != first:
                first = head
                break
    if len(first) <= max_len:
        return first
    return first[: max_len - 1].rstrip() + "…"


class Plan:
    """Plan bundle: mount the plan host and run the plan workflow.

    :meth:`open` binds a content-addressed workspace Run (same draft ⇒
    same Run). :meth:`execute` runs the pipeline inside the Run lifecycle;
    :meth:`save` lands the generated workflow IR on the owning experiment.
    """

    name = _PLAN_NAME

    def __init__(
        self,
        *,
        draft: PlanDraft | None = None,
        probe: PlanReachabilityProbe | None = None,
        approve: Approver | None = None,
        realize: bool = True,
        executor: Executor | None = None,
        realize_attempts: int = 3,
        on_loop_event: LoopEventObserver | None = None,
        board_max_iters: int = 8,
        plugins: tuple[Plugin, ...] = (),
    ) -> None:
        self.draft = draft
        self.probe = probe or PlanReachabilityProbe()
        self.approve = approve
        self.realize = realize
        self.executor = executor
        self.realize_attempts = realize_attempts
        self.on_loop_event = on_loop_event
        self.board_max_iters = board_max_iters
        self.plugins = plugins
        self._run: Run | None = None
        self._user_input: str | None = None
        self._last_execution_id: str | None = None

    @classmethod
    def open(
        cls,
        experiment: Experiment,
        user_input: str,
        *,
        supersedes: str | None = None,
        draft: PlanDraft | None = None,
        probe: PlanReachabilityProbe | None = None,
        approve: Approver | None = None,
        realize: bool = True,
        executor: Executor | None = None,
        realize_attempts: int = 3,
        on_loop_event: LoopEventObserver | None = None,
        board_max_iters: int = 8,
        plugins: tuple[Plugin, ...] = (),
    ) -> Plan:
        """Bind a content-addressed plan Run — same draft ⇒ same Run.

        The run id is derived from ``mode`` / ``draft`` (and ``supersedes``
        when a later plan replaces an earlier one). ``add_run`` is idempotent
        on that id, so re-opening the same draft replays store-first on the
        same Run instead of minting a new one.
        """
        from molexp._typing import JSONValue
        from molexp.workspace.utils import derive_run_id

        params: dict[str, JSONValue] = {"mode": "plan", "draft": user_input}
        if supersedes:
            params["supersedes"] = supersedes
        plan = cls(
            draft=draft,
            probe=probe,
            approve=approve,
            realize=realize,
            executor=executor,
            realize_attempts=realize_attempts,
            on_loop_event=on_loop_event,
            board_max_iters=board_max_iters,
            plugins=plugins,
        )
        plan._run = experiment.add_run(params, id=derive_run_id(params))
        plan._user_input = user_input
        return plan

    @property
    def bound_run(self) -> Run:
        """The workspace Run this plan is bound to via :meth:`open`."""
        if self._run is None:
            raise StageExecutionError("Plan is not bound; call Plan.open(...)")
        return self._run

    @property
    def last_execution_id(self) -> str | None:
        """Execution allocated by the most recent :meth:`execute`/``run`` call."""
        return self._last_execution_id

    @staticmethod
    def _spec(user_input: str) -> dict[str, Any]:
        """Seed the opaque plan ``spec`` from the operator draft."""
        try:
            parsed = json.loads(user_input)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        text = user_input.strip() or "experiment"
        return {
            "title": _short_plan_title(text),
            "objective": text,
            "raw_request": text,
        }

    async def execute(
        self,
        *,
        gateway: AgentGateway,
        capability_registry: CapabilityRegistry | None = None,
        run: Run | None = None,
        user_input: str | None = None,
    ) -> ModeResult:
        """Run this plan inside the workspace Run lifecycle.

        Marks the run succeeded on completion. Failures propagate and the
        RunContext settles the run failed. Uses the bound run from
        :meth:`open` when ``run`` / ``user_input`` are omitted.
        """
        host = run if run is not None else self._run
        text = user_input if user_input is not None else self._user_input
        if host is None or text is None:
            raise StageExecutionError("Plan is not bound; call Plan.open(...)")
        prior = host.executions
        mode = self._next_execution_mode(prior)
        predecessor = prior[-1].id if prior else None
        with host.start(mode=mode, based_on_execution_id=predecessor) as run_ctx:
            self._bind_approver_execution(run_ctx)
            self._seed_review_decision(host, run_ctx)
            try:
                result = await self.run(
                    run=host,
                    user_input=text,
                    gateway=gateway,
                    capability_registry=capability_registry,
                    execution_context=run_ctx,
                )
            except ApprovalPendingError as exc:
                run_ctx.mark_interrupted(str(exc))
                raise
            run_ctx.mark_succeeded()
        return result

    async def run(
        self,
        *,
        run: Any,  # noqa: ANN401 — workspace Run
        user_input: str,
        gateway: AgentGateway,
        capability_registry: CapabilityRegistry | None = None,
        execution_context: Any | None = None,  # noqa: ANN401 — workspace ExecutionContext
    ) -> ModeResult:
        """Run this bundle on *run* and return a :class:`ModeResult`."""
        if execution_context is None:
            prior = run.executions
            mode = self._next_execution_mode(prior)
            predecessor = prior[-1].id if prior else None
            with run.start(mode=mode, based_on_execution_id=predecessor) as owned_context:
                self._bind_approver_execution(owned_context)
                self._seed_review_decision(run, owned_context)
                try:
                    return await self.run(
                        run=run,
                        user_input=user_input,
                        gateway=gateway,
                        capability_registry=capability_registry,
                        execution_context=owned_context,
                    )
                except ApprovalPendingError as exc:
                    owned_context.mark_interrupted(str(exc))
                    raise
        self._last_execution_id = execution_context.id
        host = compose_plan(
            run_id=run.id,
            run_dir=run.run_dir,
            gateway=gateway,
            capability_registry=capability_registry,
            execution_context=execution_context,
            extra=self.plugins,
        )
        try:
            result = await self._run_on_host(
                host,
                run=run,
                user_input=user_input,
                execution_context=execution_context,
            )
            return result
        finally:
            host.unload()

    @staticmethod
    def _next_execution_mode(prior: list[Any]) -> ExecutionMode:
        if not prior:
            return ExecutionMode.INITIAL
        if prior[-1].status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }:
            return ExecutionMode.RETRY
        return ExecutionMode.RERUN

    def _bind_approver_execution(self, context: Any) -> None:  # noqa: ANN401
        bind = getattr(self.approve, "bind_execution", None)
        if callable(bind):
            bind(context)

    @staticmethod
    def _seed_review_decision(run: Any, context: Any) -> None:  # noqa: ANN401
        """Materialize an appended operator decision as input to a new attempt."""
        if not context.based_on_execution_id:
            return
        from molexp.harness.store.run_approval_store import RunApprovalStore

        approvals = RunApprovalStore(
            run.run_dir,
            run_id=run.id,
            execution_id=context.based_on_execution_id,
        )
        review = approvals.latest_review_decision()
        if review is None:
            return
        context.emit_artifact(
            review.model_dump(mode="json"),
            name="harness/review_decision/operator-review.json",
            media_type="application/json",
            semantic_type="review_decision",
            metadata={"source": "provenance", "decision_action": review.action},
        )

    async def _run_on_host(
        self,
        host: Host,
        *,
        run: Any,  # noqa: ANN401
        user_input: str,
        execution_context: Any,  # noqa: ANN401 — workspace ExecutionContext
    ) -> ModeResult:
        from molexp.harness.host.plugins.workflow import WorkflowHandle
        from molexp.harness.modes.plan_workflow import PlanBag, compile_plan_workflow
        from molexp.harness.plan import board_path
        from molexp.workflow import WorkflowRuntime
        from molexp.workflow.types import WorkflowResult

        ctx = host.as_run_context()
        store = ctx.artifact_store
        if not isinstance(store, FileArtifactStore):
            raise StageExecutionError("plan host did not publish a FileArtifactStore")
        if ctx.agent_gateway is None:
            raise StageExecutionError("plan host did not publish ctx.llm")
        spec = self._spec(user_input)
        board_file = board_path(execution_context.get_dir("work"))
        disk_board = DiskTaskBoard(board_file, artifact_store=store)
        belt = host.ctx.require(Keys.TOOLS)
        if not isinstance(belt, ToolBelt):
            raise StageExecutionError("plan host did not publish a ToolBelt")
        for tool in BOARD_TOOLS:
            belt.register(
                as_loop_tool(tool, ctx=ctx, board=disk_board, approve=self.approve),
                host.ctx,
            )
        bag = PlanBag(
            ctx=ctx,
            user_input=user_input,
            spec=spec,
            board_file=board_file,
            tools=belt.snapshot(),
            name=self.name,
            probe=self.probe,
            draft=self.draft,
            on_event=self.on_loop_event,
            board_max_iters=self.board_max_iters,
            do_realize=self.realize,
            approve=self.approve,
            executor=self.executor,
            realize_attempts=self.realize_attempts,
            run_id=run.id,
        )
        compiled = compile_plan_workflow(bag)
        scratch = execution_context.get_dir("work", ".plan_scratch")
        scratch.mkdir(parents=True, exist_ok=True)
        wf_handle = host.ctx.get(Keys.WORKFLOW)
        if isinstance(wf_handle, WorkflowHandle):
            raw = await wf_handle.execute(
                compiled,
                persist=True,
                run_dir=run.run_dir,
                scratch_root=scratch,
                run_context=execution_context,
                execution_id=execution_context.id,
                bypass_cache=True,
            )
        else:
            raw = await WorkflowRuntime().execute(
                compiled,
                persist=True,
                run_dir=run.run_dir,
                scratch_root=scratch,
                run_context=execution_context,
                execution_id=execution_context.id,
                bypass_cache=True,
            )
        if not isinstance(raw, WorkflowResult):
            raise StageExecutionError("plan workflow execute did not return a WorkflowResult")
        wf_result = raw
        if bag.approval_pending is not None:
            raise bag.approval_pending
        if wf_result.status != "succeeded":
            raise StageExecutionError(
                f"plan workflow failed: {getattr(wf_result, 'error', None) or wf_result.status}"
            )
        persist_out = _as_mapping(wf_result.outputs.get("persist_plan"))
        if not persist_out.get("ok"):
            raise StageExecutionError(
                "plan bundle: final board is malformed; refusing to open the "
                f"review gate — {persist_out.get('error', persist_out)}"
            )
        render_out = _as_mapping(wf_result.outputs.get("render_report"))
        if not render_out.get("ok"):
            raise StageExecutionError("plan report renderer did not produce a plan_report")

        def _ref(kind: str) -> PlanArtifactRef:
            latest = store.latest_by_kind(kind)
            if latest is None:
                raise StageExecutionError(f"missing artifact {kind}")
            return latest

        knowledge_ref = store.latest_by_kind("knowledge_context")
        plan_ref = _ref("experiment_plan")
        report_ref = _ref("plan_report")
        audit_ref = store.latest_by_kind("review_pack")
        frozen_ref = store.latest_by_kind(FROZEN_PLAN_KIND)
        realize_out = _as_mapping(wf_result.outputs.get("realize"))
        exec_ref = store.latest_by_kind("execution_result") if realize_out.get("ok") else None
        stage_artifacts: list[Any] = [
            *([knowledge_ref] if knowledge_ref is not None else []),
            plan_ref,
            report_ref,
            *([audit_ref] if audit_ref is not None else []),
            *([frozen_ref] if frozen_ref is not None else []),
            *([exec_ref] if exec_ref is not None else []),
        ]
        final = exec_ref or report_ref
        return ModeResult(
            mode_name=self.name,
            run_id=run.id,
            execution_id=execution_context.id,
            stage_artifacts=tuple(a for a in stage_artifacts if a is not None),
            final_artifact=final,
        )

    def save(self, *, run: Run | None = None, execution_id: str | None = None) -> bool:
        """Persist the generated workflow IR onto the run's owning experiment.

        Compiles the run's ``workflow_source`` artifact and writes it on the
        experiment (stamping ``plan_run_id``). Returns ``True`` when an IR
        document was written. Uses the bound run from :meth:`open` when
        ``run`` is omitted.
        """
        host = run if run is not None else self._run
        if host is None:
            raise StageExecutionError("Plan.save requires a bound run; call Plan.open(...)")
        selected_execution_id = execution_id or self._last_execution_id
        ir = self._ir(run=host, execution_id=selected_execution_id)
        if ir is None:
            return False
        experiment = host.experiment
        experiment.metadata = experiment.metadata.model_copy(
            update={
                "workflow_source": json.dumps(ir, sort_keys=True),
                "plan_run_id": host.id,
            }
        )
        experiment.save()
        return True

    def _ir(self, *, run: Run, execution_id: str | None) -> dict[str, Any] | None:
        """Compile this plan run's ``workflow_source`` artifact to display IR."""
        from molexp.harness.schemas import WorkflowSource
        from molexp.harness.store.paths import harness_artifact_root

        if execution_id is not None:
            store = FileArtifactStore.open_execution(run, execution_id)
        else:
            store = FileArtifactStore(root=harness_artifact_root(run.run_dir))
        ref = store.latest_by_kind("workflow_source")
        if ref is None:
            return None
        ws = WorkflowSource.model_validate_json(store.get(ref.id))
        return _compile_package_to_ir(ws) if ws.files else _compile_source_to_ir(ws.source)


# Compile helpers for :meth:`Plan.save`. Not a public persist API.

_SAFE_BUILTINS: dict[str, Any] = {
    "__import__": __import__,
    "len": len,
    "range": range,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "sum": sum,
    "min": min,
    "max": max,
}


def _attach_task_sources(ir: dict[str, Any], source: str) -> None:
    """Annotate each ``task_config`` with its own source code (in place)."""
    task_configs = ir.get("task_configs")
    if not isinstance(task_configs, list):
        return
    wanted = {
        tc["task_id"]
        for tc in task_configs
        if isinstance(tc, dict) and isinstance(tc.get("task_id"), str)
    }
    if not wanted:
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    lines = source.splitlines()
    by_name: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted or node.end_lineno is None:
            continue
        start = min([d.lineno for d in node.decorator_list] + [node.lineno])
        segment = "\n".join(lines[start - 1 : node.end_lineno])
        by_name[node.name] = textwrap.dedent(segment).strip("\n")
    for tc in task_configs:
        if not isinstance(tc, dict):
            continue
        task_id = tc.get("task_id")
        if isinstance(task_id, str) and task_id in by_name:
            tc["source"] = by_name[task_id]


def _annotation_to_ui_type(ann: ast.expr | None) -> tuple[str, list | None]:
    """Map a parameter annotation to a UI field type (+ enum options)."""
    if isinstance(ann, ast.Name):
        return {"float": "number", "int": "integer", "str": "text", "bool": "boolean"}.get(
            ann.id, "text"
        ), None
    if isinstance(ann, ast.Subscript):
        base = ann.value
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
        if base_name == "Literal":
            elts = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            options = [e.value for e in elts if isinstance(e, ast.Constant)]
            return "enum", options
    return "text", None


def _extract_input_schema(ir: dict[str, Any], source: str) -> None:
    """Derive the workflow's editable inputs from the tasks' typed parameters."""
    task_configs = ir.get("task_configs")
    if not isinstance(task_configs, list):
        return
    wanted = {
        tc["task_id"]
        for tc in task_configs
        if isinstance(tc, dict) and isinstance(tc.get("task_id"), str)
    }
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    fields: dict[str, dict] = {}

    def _record(arg: ast.arg, default: ast.expr | None) -> None:
        name = arg.arg
        if default is None or name in ("ctx", "self") or name in fields:
            return
        ftype, options = _annotation_to_ui_type(arg.annotation)
        try:
            default_value = ast.literal_eval(default)
        except (ValueError, SyntaxError):
            default_value = None
        field: dict = {"name": name, "type": ftype, "default": default_value}
        if options is not None:
            field["options"] = options
        fields[name] = field

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in wanted:
            continue
        pos = node.args.args
        for arg, default in zip(
            pos[len(pos) - len(node.args.defaults) :], node.args.defaults, strict=False
        ):
            _record(arg, default)
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
            _record(arg, default)

    if fields:
        prior = ir.get("input_schema")
        existing = {
            f["name"]: f
            for f in (prior if isinstance(prior, list) else [])
            if isinstance(f, dict) and "name" in f
        }
        for name, field in fields.items():
            existing.setdefault(name, field)
        ir["input_schema"] = list(existing.values())


def _compile_source_to_ir(source: str) -> dict[str, Any] | None:
    """Compile a ``build_workflow()`` program to a UI-renderable IR document."""
    import molexp.workflow as workflow

    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    try:
        exec(compile(source, "<plan_workflow_source>", "exec"), namespace)
        builder = namespace["build_workflow"]()
        compiled = workflow.WorkflowCompiler().compile(builder)
        ir = dict(workflow.default_codec.spec_to_ir(compiled, strict=False))
        _attach_task_sources(ir, source)
        _extract_input_schema(ir, source)
        return ir
    except Exception as exc:
        _LOG.warning(f"plan workflow source did not compile for display: {exc!r}")
        return None


_PACKAGE_IR_SCRIPT = textwrap.dedent(
    """
    import importlib, json, sys

    sys.path.insert(0, sys.argv[1])
    module = importlib.import_module(sys.argv[2])
    from molexp.workflow import WorkflowCompiler, default_codec
    compiled = WorkflowCompiler().compile(module.build_workflow())

    json.dump(dict(default_codec.spec_to_ir(compiled, strict=False)), sys.stdout)
    """
)


def _compile_package_to_ir(ws: WorkflowSource) -> dict[str, Any] | None:
    """Multi-file mode: build the display IR from ``ws.files`` in a subprocess."""
    try:
        with tempfile.TemporaryDirectory(prefix="molexp-plan-ir-") as tmp:
            for f in ws.files:
                target = Path(tmp) / f.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f.source, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-c", _PACKAGE_IR_SCRIPT, tmp, ws.module_name],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        if proc.returncode != 0:
            _LOG.warning(
                f"plan workflow package did not compile for display: {proc.stderr.strip()[-500:]}"
            )
            return None
        ir = dict(json.loads(proc.stdout))
    except Exception as exc:
        _LOG.warning(f"plan workflow package did not compile for display: {exc!r}")
        return None
    for f in ws.files:
        _attach_task_sources(ir, f.source)
        _extract_input_schema(ir, f.source)
    return ir
