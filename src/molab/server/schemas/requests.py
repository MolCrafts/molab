"""Pydantic request models for Molab API.

Aligned with workspace.models — field names match domain models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Discriminator, Field, Tag, model_validator

from ._wire import ApiModel

# ── Workspace ───────────────────────────────────────────────────────────────


class WorkspaceOpenLocalRequest(ApiModel):
    """Local-workspace branch of ``POST /api/workspace/open``."""

    kind: Literal["local"] = Field(default="local", description="Discriminator")
    path: str = Field(..., description="Absolute path to the workspace")
    create_if_missing: bool = Field(False, description="Create if missing")


class WorkspaceOpenRemoteRequest(ApiModel):
    """Remote-workspace branch of ``POST /api/workspace/open``.

    The descriptor must already be registered via
    ``POST /api/workspace/targets``; auto-creation of remote roots is
    out of scope for this endpoint (returns 404 if the descriptor or
    its remote ``root_path`` is missing).
    """

    kind: Literal["remote"] = Field(..., description="Discriminator")
    name: str = Field(..., description="Registered workspace-target name")


def _workspace_open_discriminator(v: object) -> str:
    """Discriminator with back-compat default — bodies that omit ``kind``
    are treated as ``kind: "local"`` so existing clients keep working."""
    from typing import cast

    if isinstance(v, dict):
        kind = cast(dict[str, object], v).get("kind")
        return str(kind) if kind is not None else "local"
    if hasattr(v, "kind"):
        return str(v.kind)
    return "local"


WorkspaceOpenRequest = Annotated[
    Annotated[WorkspaceOpenLocalRequest, Tag("local")]
    | Annotated[WorkspaceOpenRemoteRequest, Tag("remote")],
    Discriminator(_workspace_open_discriminator),
]


# ── Project ─────────────────────────────────────────────────────────────────


class ProjectCreateRequest(ApiModel):
    name: str = Field(..., description="Human-readable project name")
    description: str = Field("", description="Project description")
    owner: str = Field("", description="Project owner")
    tags: list[str] = Field(default_factory=list, description="Project tags")


# ── Experiment ──────────────────────────────────────────────────────────────


class ExperimentCreateRequest(ApiModel):
    name: str = Field(..., description="Human-readable experiment name")
    workflow_source: dict[str, Any] | None = Field(
        None, description="Workflow IR document; bound as the document kind"
    )
    description: str = Field("", description="Experiment description")
    parameter_space: dict[str, Any] = Field(
        default_factory=dict, description="Parameter space definition"
    )
    default_target: str | None = Field(
        default=None,
        alias="defaultTarget",
        description="Compute target name new runs should default to (must exist)",
    )

    model_config = ConfigDict(populate_by_name=True)


# ── Run ─────────────────────────────────────────────────────────────────────


def _reject_parameters_alias(data: object) -> object:
    """Refuse the removed ``parameters`` request key.

    The on-disk run field is still ``parameters``. The create body is
    ``params``. Accepting the old key as an alias, or ignoring it, stores
    an empty param dict.
    """
    if isinstance(data, dict) and "parameters" in data:
        raise ValueError("unknown field 'parameters'; send 'params'")
    return data


class RunCreateRequest(ApiModel):
    params: dict[str, Any] = Field(default_factory=dict, description="Run params")
    inputs: list[str] = Field(
        default_factory=list,
        description="Asset ids this run consumes. Bound into the root task as paths.",
    )
    target: str | None = Field(
        default=None,
        description="Declared compute-target hint (must exist in workspace registry)",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _no_parameters_alias(cls, data: object) -> object:
        return _reject_parameters_alias(data)


class RunHarvestRequest(ApiModel):
    """Harvest a terminal run into sourced Knowledge under its experiment."""

    model_config = ConfigDict(extra="forbid")

    cls: Literal["Finding", "Observation", "Report"] = Field(
        default="Finding",
        description="Finding, Observation, or Report.",
    )
    narrative: str = Field(..., description="Non-empty interpretation")
    created_by: str = Field(default="ui", description="Author string")
    name: str | None = Field(default=None, description="Optional knowledge document name")
    results: dict[str, Any] | None = Field(
        default=None,
        description="Values to pin as spans on assets this run registered",
    )


class ExecutionAttemptCreateRequest(ApiModel):
    """Create one physical attempt for an existing logical Run."""

    mode: Literal["initial", "rerun", "resume", "reproduce"] = "initial"
    based_on_execution_id: str | None = None
    bypass_cache: bool = Field(
        default=False,
        description=(
            "Recompute every task, ignoring cached node results. Always true for reproduce."
        ),
    )
    target: str = Field(
        default="local",
        min_length=1,
        description=(
            "Compute target the attempt is submitted to; the built-in ``local`` target "
            "runs it on this machine. Every created attempt is submitted — an attempt "
            "nothing will run is never created."
        ),
    )
    request_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Idempotency key. When an attempt of this Run was already created with "
            "the same key, that attempt is returned and nothing new is created or "
            "dispatched, so a caller that lost the response can retry safely."
        ),
    )
    requested_by: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Software agent recorded as the attempt's creator (default: the UI).",
    )
    tasks: list[Annotated[str, Field(min_length=1)]] | None = Field(
        default=None,
        description=(
            "Rerun only these tasks (``mode`` must be ``rerun``): each executes with the "
            "inputs the predecessor attempt recorded, every other completed task is seeded "
            "from its record, and every task downstream of a selected one is skipped. "
            "Omit to rerun every task."
        ),
    )
    task_executor: Literal["thread", "process", "inline"] | None = Field(
        default=None,
        description=(
            "How the attempt's task bodies run: worker threads (default), worker "
            "processes, or inline on the engine thread. Overrides the workflow's and "
            "each task's choice."
        ),
    )
    max_workers: int | None = Field(
        default=None, ge=1, description="Worker threads / processes at most."
    )


class WorkflowDocumentRequest(ApiModel):
    """Edited workflow IR document posted by the free-layout canvas.

    ``document`` is the identity-free wire IR (``{task_configs, links, entries,
    loops, parallels, ...}``). The route validates it through
    ``WorkflowCodec.ir_to_spec`` before persisting. The compiled digest lives
    on the Execution, not in this document.
    """

    document: dict[str, Any] = Field(..., description="Workflow IR document")
    convert_to_document: bool = Field(
        default=False,
        description="Replace a code-kind binding with this document",
    )


# ── Execution ───────────────────────────────────────────────────────────────


class ExecutionCreateRequest(ApiModel):
    project_id: str = Field(..., description="Target project ID")
    experiment_id: str = Field(..., description="Target experiment ID")
    params: dict[str, Any] = Field(default_factory=dict, description="Run params")
    workflow_json: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional workflow IR (WorkflowCodec.ir_to_spec). On an unbound "
            "experiment it is bound as the document kind before the run is "
            "created. On a document experiment it must match the bound document. "
            "On a code experiment it is rejected; convert with PUT .../workflow "
            "and convertToDocument. The request never writes the in-process "
            "binding memo."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _no_parameters_alias(cls, data: object) -> object:
        return _reject_parameters_alias(data)


# ── Asset ───────────────────────────────────────────────────────────────────
