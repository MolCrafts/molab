"""Pydantic request models for Molab API.

Aligned with workspace.models — field names match domain models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, ConfigDict, Discriminator, Field, Tag

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
    workflow_source: str | None = Field(None, description="Path to workflow file")
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


class RunCreateRequest(ApiModel):
    params: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("params", "parameters"),
        description="Run params ('parameters' accepted as a deprecated alias)",
    )
    target: str | None = Field(
        default=None,
        description="Declared compute-target hint (must exist in workspace registry)",
    )

    model_config = ConfigDict(populate_by_name=True)


class RunHarvestRequest(ApiModel):
    """Harvest a terminal run into a sourced KnowledgeItem under its experiment."""

    kind: Literal[
        "Observation",
        "Decision",
        "Assumption",
        "Constraint",
        "Finding",
        "FailureAnalysis",
        "ProtocolNote",
        "ParameterRationale",
        "OpenQuestion",
        "Plan",
    ] = Field(..., description="Knowledge class name")
    narrative: str = Field(..., description="Non-empty interpretation")
    created_by: str = Field(default="ui", description="Author string")
    name: str | None = Field(default=None, description="Optional KnowledgeItem name")
    results: dict[str, Any] | None = Field(
        default=None, description="Optional headline results table"
    )


class RunAnalyzeFailureRequest(ApiModel):
    """Analyze a failed run into a sourced FailureAnalysis KnowledgeItem."""

    narrative: str | None = Field(
        default=None,
        description="Optional interpretation; when omitted a deterministic template is used",
    )
    created_by: str = Field(default="ui", description="Author string")
    force: bool = Field(
        default=False,
        description="When true, also accept cancelled runs (default: failed only)",
    )
    name: str | None = Field(default=None, description="Optional KnowledgeItem name")


class ExecutionAttemptCreateRequest(ApiModel):
    """Create one physical attempt for an existing logical Run."""

    mode: Literal["initial", "retry", "rerun", "resume", "reproduce"] = "initial"
    based_on_execution_id: str | None = None
    checkpoint_artifact_id: str | None = None
    target: str | None = None
    dispatch: bool = Field(
        default=False,
        description="Submit the queued Execution after it is created.",
    )


class ArtifactPromoteRequest(ApiModel):
    """Append an Artifact → Asset registration fact."""

    title: str | None = None
    into_asset_id: str | None = None
    created_by: str = "ui"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowDocumentRequest(ApiModel):
    """Edited workflow IR document posted by the free-layout canvas.

    ``document`` is the wire IR (``{task_configs, links, entries, loops,
    parallels, ...}``) matching ``workflow/schema/workflow.json``. The route
    validates it through ``WorkflowCodec.ir_to_spec`` before persisting.
    """

    document: dict[str, Any] = Field(..., description="Workflow IR document")


# ── Execution ───────────────────────────────────────────────────────────────


class ExecutionCreateRequest(ApiModel):
    project_id: str = Field(..., description="Target project ID")
    experiment_id: str = Field(..., description="Target experiment ID")
    params: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("params", "parameters"),
        description="Run params ('parameters' accepted as a deprecated alias)",
    )
    workflow_json: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional workflow IR (matches schema/workflow.json). When "
            "provided and the experiment has no workflow bound yet, the "
            "server binds it and persists the IR to disk. Subsequent "
            "calls reuse the on-disk binding."
        ),
    )


# ── Asset ───────────────────────────────────────────────────────────────────
