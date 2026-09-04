"""Reorganize a workspace tree.

Thin compositions over the workspace move / import / delete primitives:

* ``move_run`` relocates a Run to another Experiment (``Run.move_to``).
* ``move_experiment`` relocates an Experiment (and its runs) to another
  Project — including across workspace roots.
* ``rehome_asset`` re-imports a ``DataAsset``'s payload into another scope
  (``DataAssetLibrary.import_asset``), preserving its content hash.
* ``delete_folder`` removes a folder and prunes it from its parent's listing.
* ``strip_legacy_ops`` deletes leftover ``ops/`` sidecars (persist-one:
  status lives in ``executions/<id>/execution.json``).

``reslug`` (entity rename) is intentionally absent: renaming an entity's id must
rewrite its authoritative metadata file and re-home every asset cataloged under
the old scope (and a Run's id is embedded in its execution ids), which is a
focused follow-up rather than a ``move_to`` compose.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from molexp.workspace.assets.data import DataAsset, DataAssetLibrary, ImportAction
    from molexp.workspace.experiment import Experiment
    from molexp.workspace.folder import Folder
    from molexp.workspace.project import Project
    from molexp.workspace.run import Run
    from molexp.workspace.workspace import Workspace

__all__ = [
    "delete_folder",
    "move_experiment",
    "move_run",
    "rehome_asset",
    "strip_legacy_ops",
]


class _ImportTarget(Protocol):
    """A workspace scope that can import a ``DataAsset`` (Workspace / Project /
    Experiment)."""

    @property
    def data_assets(self) -> DataAssetLibrary: ...


def move_run(run: Run, target_experiment: Experiment) -> None:
    """Relocate *run* to *target_experiment*.

    Composes ``Run.move_to``, which is container- and children-index-aware.
    Local-filesystem only — ``move_to`` raises ``NotImplementedError`` on a
    remote-backed folder.

    Args:
        run: The run to move.
        target_experiment: The experiment to move it under.
    """
    run.move_to(target_experiment)


def move_experiment(experiment: Experiment, target_project: Project) -> None:
    """Relocate *experiment* (and every run under it) to *target_project*.

    Composes ``Experiment.move_to``. The experiment keeps its UUID id and
    display name; only the parent project (and, when the project lives in
    another workspace, the workspace root) changes. Local-filesystem only.

    Args:
        experiment: The experiment to move.
        target_project: The project to move it under. May belong to a
            different :class:`~molexp.workspace.Workspace` than *experiment*.
    """
    experiment.move_to(target_project)


def strip_legacy_ops(scope: Workspace | Project | Experiment | Run) -> int:
    """Remove leftover ``ops/`` sidecars under *scope*.

    persist-one folded operational state into
    ``executions/<id>/execution.json``. A pre-cutover ``ops/run.json`` is
    not a layout container (``validate`` reports ``layout.stray``) and is
    never the status authority. Returns the number of ``ops/`` directories
    deleted.
    """
    from molexp.workspace.experiment import Experiment
    from molexp.workspace.project import Project
    from molexp.workspace.run import Run
    from molexp.workspace.workspace import Workspace

    runs: list[Run]
    if isinstance(scope, Run):
        runs = [scope]
    elif isinstance(scope, Experiment):
        runs = list(scope.list_runs())
    elif isinstance(scope, Project):
        runs = [run for exp in scope.list_experiments() for run in exp.list_runs()]
    elif isinstance(scope, Workspace):
        runs = [
            run
            for project in scope.list_projects()
            for exp in project.list_experiments()
            for run in exp.list_runs()
        ]
    else:
        raise TypeError(
            f"strip_legacy_ops expects Workspace/Project/Experiment/Run, got {type(scope)!r}"
        )

    removed = 0
    for run in runs:
        ops = Path(str(run.run_dir)) / "ops"
        if ops.is_dir():
            shutil.rmtree(ops)
            removed += 1
    return removed


def _scope_dir(entity: object) -> Path:
    """Resolve a workspace entity's on-disk scope directory.

    Probes the entity's directory property in most-specific order so a Run's
    ``run_dir`` wins over a Workspace's ``root``.
    """
    for attr in ("run_dir", "experiment_dir", "project_dir", "root"):
        value = getattr(entity, attr, None)
        if value is not None:
            return Path(str(value))
    raise TypeError(f"{type(entity).__name__} has no resolvable scope directory")


def rehome_asset(
    asset: DataAsset,
    *,
    source: object,
    target: _ImportTarget,
    action: ImportAction = "copy",
) -> DataAsset:
    """Re-import *asset*'s payload into *target*'s scope.

    Composes ``DataAssetLibrary.import_asset`` on the target. For ``action`` of
    ``"copy"`` or ``"move"`` the content hash is recomputed on the destination
    payload, so identical bytes yield an identical ``content_hash``.

    Args:
        asset: The data asset whose payload to re-home.
        source: The workspace entity the asset currently lives under (used only
            to resolve the source payload path).
        target: The destination scope (Workspace / Project / Experiment).
        action: Transfer mode passed through to ``import_asset``.

    Returns:
        The newly imported :class:`DataAsset` under *target*'s scope.
    """
    payload = asset.payload(_scope_dir(source))
    return target.data_assets.import_asset(asset.name, payload, action=action)


def delete_folder(folder: Folder) -> None:
    """Delete *folder* and drop it from its parent's listing.

    Routes through ``parent.remove_folder`` (which also prunes the derived
    children index) when the folder is mounted; falls back to ``Folder.delete``
    for an unmounted folder. Entity folders (Project / Experiment / Run) are
    keyed on disk by their UUID7 id, not their display name, so the removal
    key is the entity id when present.

    Args:
        folder: The folder to delete.
    """
    parent = folder.parent
    if parent is not None:
        key = getattr(folder, "id", None)
        if key is None:
            key = folder.name
        parent.remove_folder(key, cls=type(folder))
    else:
        folder.delete()
