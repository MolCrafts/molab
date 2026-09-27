"""Workspace tree inventory.

``scan_workspace`` classifies the ``Workspace -> Project -> Experiment -> Run``
tree into a frozen snapshot: a per-project / per-experiment / per-run breakdown
plus tree-wide totals. It composes the typed ``list_*`` walkers with each run's
derived lifecycle status and the total asset count (imported data assets plus
run-emitted artifacts) — it does not re-implement any traversal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ..assets import scan
from ._assets import count_emitted_artifacts

if TYPE_CHECKING:
    from molab.workspace.workspace import Workspace

__all__ = [
    "ExperimentInventory",
    "ProjectInventory",
    "RunInventory",
    "WorkspaceInventory",
    "scan_workspace",
]


class RunInventory(BaseModel):
    """A run's identity and lifecycle status."""

    model_config = ConfigDict(frozen=True)

    id: str
    status: str


class ExperimentInventory(BaseModel):
    """An experiment and the runs it contains."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    runs: tuple[RunInventory, ...]


class ProjectInventory(BaseModel):
    """A project and the experiments it contains."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    experiments: tuple[ExperimentInventory, ...]


class WorkspaceInventory(BaseModel):
    """A frozen snapshot of a workspace's structure with tree-wide totals."""

    model_config = ConfigDict(frozen=True)

    name: str
    projects: tuple[ProjectInventory, ...]
    project_count: int
    experiment_count: int
    run_count: int
    asset_count: int


def scan_workspace(workspace: Workspace) -> WorkspaceInventory:
    """Classify a workspace tree into a frozen :class:`WorkspaceInventory`.

    Composes ``workspace.list_projects`` / ``Project.list_experiments`` /
    ``Experiment.list_runs`` and each run's derived lifecycle status for the
    structural breakdown, and the total asset count (imported data assets via
    ``scan.scan_assets`` plus run-emitted artifacts) for ``asset_count``. The
    scan reads the authoritative on-disk manifests and provenance index; it is
    read-only.

    Args:
        workspace: The workspace to inventory.

    Returns:
        A frozen inventory carrying the per-project/experiment/run tree and the
        tree-wide ``project_count`` / ``experiment_count`` / ``run_count`` /
        ``asset_count`` totals.
    """
    projects: list[ProjectInventory] = []
    experiment_count = 0
    run_count = 0
    for project in workspace.list_projects():
        experiments: list[ExperimentInventory] = []
        for experiment in project.list_experiments():
            runs = tuple(
                RunInventory(id=run.id, status=run.status_label) for run in experiment.list_runs()
            )
            run_count += len(runs)
            experiment_count += 1
            experiments.append(
                ExperimentInventory(id=experiment.id, name=experiment.metadata.name, runs=runs)
            )
        projects.append(
            ProjectInventory(
                id=project.id,
                name=project.metadata.name,
                experiments=tuple(experiments),
            )
        )
    asset_count = len(scan.scan_assets(workspace.root)) + count_emitted_artifacts(workspace)
    return WorkspaceInventory(
        name=workspace.metadata.name,
        projects=tuple(projects),
        project_count=len(projects),
        experiment_count=experiment_count,
        run_count=run_count,
        asset_count=asset_count,
    )
