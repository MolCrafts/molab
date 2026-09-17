"""Built-in curation ``ToolCapability`` catalog.

The static, frozen catalog of :class:`~molab.harness.schemas.capability.ToolCapability`
entries that expose the workspace-curation functions (link 01,
``molab.workspace.curation.*``) as harness-invokable tools. Each entry names its
backing callable by a dotted ``callable_path``, declares a shallow key-level
``input_schema`` mirroring the function's signature, and declares ``side_effects``.

**read-only vs destructive contract.** Scan / query / report functions (``scan``,
``find``, ``aggregate``, and the report-only ``dedupe`` / ``consolidate`` — which
return groupings and mutate nothing) declare ``side_effects == []`` and are never
gated. The three mutators (``move_run`` / ``rehome_asset`` / ``delete_folder``)
declare a non-empty list of concrete mutation tokens, so the link-03
``side_effects`` → ``ApprovalGate`` rule gates them automatically — no per-entry
gate wiring lives here.

These are built-ins registered directly (link 05), never discovered through
molmcp. The catalog is process-static module data — literal ids, dotted paths,
and schemas — so it imports neither ``molab.workspace.curation`` nor any heavy
dependency at module load; the ``callable_path`` strings are resolved lazily by
the invocation path, keeping ``import molab.harness`` light.
"""

from __future__ import annotations

from collections.abc import Sequence

from molab.harness.schemas import ToolCapability

__all__ = ["CURATION_CAPABILITIES", "curation_capabilities"]


def _input_schema(properties: Sequence[str], required: Sequence[str]) -> dict[str, object]:
    """Build a shallow key-level ``input_schema`` (property values are empty).

    Mirrors :func:`molab.harness.mcp_capabilities.synthesize_input_schema`: the harness
    validator only key-checks (provided ⊆ ``properties``; ``required`` ⊆
    provided), so name-level entries suffice.
    """
    return {
        "type": "object",
        "properties": {name: {} for name in properties},
        "required": list(required),
    }


CURATION_CAPABILITIES: tuple[ToolCapability, ...] = (
    ToolCapability(
        id="molab.curation.scan_workspace",
        package="molab",
        name="scan_workspace",
        description=(
            "Classify a workspace tree into a frozen inventory "
            "(per-project/experiment/run breakdown + tree-wide totals). Read-only."
        ),
        input_schema=_input_schema(["workspace"], ["workspace"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.scan_workspace",
        side_effects=[],
        tags=["curation", "read-only"],
    ),
    ToolCapability(
        id="molab.curation.find_asset_by_hash",
        package="molab",
        name="find_asset_by_hash",
        description="Find a workspace asset by its content hash. Read-only.",
        input_schema=_input_schema(["workspace", "content_hash"], ["workspace", "content_hash"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.find_asset_by_hash",
        side_effects=[],
        tags=["curation", "read-only"],
    ),
    ToolCapability(
        id="molab.curation.aggregate_assets_by_kind",
        package="molab",
        name="aggregate_assets_by_kind",
        description="Count the assets in a scope keyed by their kind. Read-only.",
        input_schema=_input_schema(["scope", "recursive"], ["scope"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.aggregate_assets_by_kind",
        side_effects=[],
        tags=["curation", "read-only"],
    ),
    ToolCapability(
        id="molab.curation.dedupe_workflow_source",
        package="molab",
        name="dedupe_workflow_source",
        description=(
            "Group run ids by the content hash of their captured workflow source. "
            "Report-only — mutates nothing."
        ),
        input_schema=_input_schema(["runs"], ["runs"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.dedupe_workflow_source",
        side_effects=[],
        tags=["curation", "read-only"],
    ),
    ToolCapability(
        id="molab.curation.consolidate_workflow_source",
        package="molab",
        name="consolidate_workflow_source",
        description=(
            "Map each duplicate run id to the canonical id of its source group. "
            "Report-only — mutates nothing."
        ),
        input_schema=_input_schema(["runs"], ["runs"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.consolidate_workflow_source",
        side_effects=[],
        tags=["curation", "read-only"],
    ),
    ToolCapability(
        id="molab.curation.move_run",
        package="molab",
        name="move_run",
        description="Relocate a run to another experiment (moves its run directory).",
        input_schema=_input_schema(["run", "target_experiment"], ["run", "target_experiment"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.move_run",
        side_effects=["move:run_directory"],
        tags=["curation", "destructive"],
    ),
    ToolCapability(
        id="molab.curation.rehome_asset",
        package="molab",
        name="rehome_asset",
        description="Re-import a data asset's payload into another scope (copy or move).",
        input_schema=_input_schema(
            ["asset", "source", "target", "action"], ["asset", "source", "target"]
        ),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.rehome_asset",
        side_effects=["write:asset_payload", "register:asset_catalog"],
        tags=["curation", "destructive"],
    ),
    ToolCapability(
        id="molab.curation.delete_folder",
        package="molab",
        name="delete_folder",
        description="Delete a folder and drop it from its parent's listing.",
        input_schema=_input_schema(["folder"], ["folder"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.curation.delete_folder",
        side_effects=["delete:folder"],
        tags=["curation", "destructive"],
    ),
    ToolCapability(
        id="molab.curation.git_push",
        package="molab",
        name="history_push",
        description="Push the workspace history to a git remote.",
        input_schema=_input_schema(["workspace", "remote"], ["workspace", "remote"]),
        output_schema={"type": "object"},
        callable_path="molab.workspace.history.push_workspace",
        side_effects=["push:remote"],
        tags=["curation", "history", "destructive"],
    ),
)


def curation_capabilities() -> list[ToolCapability]:
    """Return the built-in curation capability catalog.

    Returns a fresh ``list`` each call (the frozen ``ToolCapability`` entries are
    shared). The app-tier merge (link 05) registers these onto the concrete
    ``InMemoryCapabilityRegistry``.
    """
    return list(CURATION_CAPABILITIES)
