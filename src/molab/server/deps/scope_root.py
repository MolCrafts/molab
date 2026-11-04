"""The served directory as the object routes already call ``workspace`` on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.path import Path
from molab.workspace.folder import WORKSPACE_ROOT_KIND
from molab.workspace.scope import descendants, entities, require_entity

if TYPE_CHECKING:
    from molab.workspace.folder import Folder
    from molab.workspace.fs import FileSystem
    from molab.workspace.models import ComputeTarget
    from molab.workspace.project import Project
    from molab.workspace.refs import MolabRef
    from molab.workspace.workspace import Workspace


class ScopeRoot:
    """The served node, as the workspace-shaped object routes are handed.

    ``.root`` is the opened directory. ``list_projects`` / ``get_project``
    follow rank: a served project is the only project, a served experiment
    has none. The interface is explicit — nothing is forwarded to the mounted
    folder implicitly — so a route that needs something a served node does
    not provide fails with a message naming it, not deep inside a handler.
    """

    def __init__(self, folder: Folder) -> None:
        self.folder = folder

    @property
    def root(self) -> Path:
        return Path(self.folder.resolve())

    def list_projects(self) -> list[Project]:
        from molab.workspace.project import Project

        found = entities(self.folder, Project)
        return [project for project in found if isinstance(project, Project)]

    def projects(self) -> list[Project]:
        return self.list_projects()

    def get_project(self, name: str) -> Project:
        from molab.workspace.project import Project

        found = require_entity(self.folder, Project, name)
        if not isinstance(found, Project):
            raise Project._not_found_error_cls(name)
        return found

    def project(self, name: str) -> Project:
        return self.get_project(name)

    def add_project(self, name: str) -> Project:
        from molab.workspace.errors import ProjectNotFoundError
        from molab.workspace.workspace import Workspace

        if self.folder.kind != WORKSPACE_ROOT_KIND or not isinstance(self.folder, Workspace):
            raise ProjectNotFoundError(name)
        return self.folder.add_project(name)

    def find(self, ref: MolabRef | str) -> object:
        """Resolve a ``molab:`` reference without leaving the serve boundary.

        A served workspace resolves as :meth:`Workspace.find`. Below it, a
        project, experiment, run, execution or artifact resolves only at or
        under the served node; anything else is not found. Assets are not
        resolvable from a node below the workspace.

        Raises:
            InvalidRefError: *ref* is not a canonical reference.
            RefNotFoundError: It names nothing inside the served scope.
        """
        from molab.workspace.errors import RefNotFoundError
        from molab.workspace.experiment import Experiment
        from molab.workspace.project import Project
        from molab.workspace.refs import parse_ref
        from molab.workspace.run import Run
        from molab.workspace.workspace import Workspace, resolve_below_experiment

        if isinstance(self.folder, Workspace):
            return self.folder.find(ref)
        parsed = parse_ref(ref) if isinstance(ref, str) else ref
        if parsed.asset_id is not None:
            raise RefNotFoundError(parsed, "asset", parsed.asset_id)
        if parsed.project_id is not None:
            for project in descendants(self.folder, Project):
                if isinstance(project, Project) and project.id == parsed.project_id:
                    return project
            raise RefNotFoundError(parsed, "project", parsed.project_id)
        if isinstance(self.folder, Run):
            # The experiment is above a served run: only the run and below resolve.
            if self.folder.experiment.id != parsed.experiment_id or parsed.run_id != self.folder.id:
                raise RefNotFoundError(parsed, "run", parsed.run_id or parsed.experiment_id or "")
            return resolve_below_experiment(self.folder.experiment, parsed)
        for experiment in descendants(self.folder, Experiment):
            if isinstance(experiment, Experiment) and experiment.id == parsed.experiment_id:
                return resolve_below_experiment(experiment, parsed)
        raise RefNotFoundError(parsed, "experiment", parsed.experiment_id or "")

    # ── the rest of the served-root interface, each member explicit ──────

    @property
    def fs(self) -> FileSystem:
        """The disk the served node lives on."""
        return self.folder._disk()

    @property
    def files(self) -> object:
        """User byte writes into the served node (its ``FileStore``)."""
        return self.folder.files

    @property
    def id(self) -> str:
        return str(self.folder.metadata.id)

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def kind(self) -> str:
        return self.folder.kind

    @property
    def metadata(self) -> object:
        return self.folder.metadata

    def resolve(self) -> Path:
        return Path(self.folder.resolve())

    def remove_project(self, name: str) -> None:
        """Remove a project. Only a served workspace has projects to remove."""
        from molab.workspace.errors import ProjectNotFoundError
        from molab.workspace.workspace import Workspace

        if not isinstance(self.folder, Workspace):
            raise ProjectNotFoundError(name)
        self.folder.remove_project(name)

    @property
    def assets(self) -> object:
        """Named assets at the served node's own scope (workspace, project or experiment)."""
        repository = getattr(type(self.folder), "assets", None)
        if repository is None:
            raise AttributeError(f"a served {self.folder.kind} has no asset scope of its own")
        return self.folder.assets  # ty: ignore[unresolved-attribute]

    def assets_at(self, scope: object) -> object:
        """The repository for *scope*, which must be the served node or below it."""
        from molab.workspace.workspace import Workspace

        if isinstance(self.folder, Workspace):
            return self.folder.assets_at(scope)  # ty: ignore[invalid-argument-type]
        ids = tuple(getattr(scope, "ids", ()) or ())
        if str(self.folder.metadata.id) not in ids:
            raise PermissionError("that asset scope is outside the served directory")
        host = self.folder.asset_host()
        return host.assets_at(scope)  # ty: ignore[unresolved-attribute]

    def list_targets(self) -> list[object]:
        from molab.workspace.targets import list_targets

        return list(list_targets(self))  # ty: ignore[invalid-argument-type]

    def get_target(self, name: str) -> object:
        from molab.workspace.targets import get_target

        return get_target(self, name)  # ty: ignore[invalid-argument-type]

    def has_target(self, name: str) -> bool:
        from molab.workspace.targets import has_target

        return has_target(self, name)  # ty: ignore[invalid-argument-type]

    def add_target(self, target: ComputeTarget) -> None:
        """Register a compute target. Targets belong to a workspace, not to a node."""
        self._require_workspace("register a compute target").add_target(target)

    def remove_target(self, name: str) -> None:
        self._require_workspace("remove a compute target").remove_target(name)

    def _require_workspace(self, action: str) -> Workspace:
        from molab.workspace.workspace import Workspace

        if not isinstance(self.folder, Workspace):
            raise PermissionError(
                f"cannot {action} from a served {self.folder.kind}; serve the workspace"
            )
        return self.folder

    def __getattr__(self, name: str) -> object:
        """Nothing is forwarded implicitly: a missing member is a missing feature."""
        raise AttributeError(
            f"a served {self.folder.kind} does not provide {name!r}; ScopeRoot exposes root, fs, "
            "files, id, name, kind, metadata, resolve, find, list_projects, projects, get_project, "
            "project, add_project, remove_project, assets, assets_at and the target verbs"
        )
