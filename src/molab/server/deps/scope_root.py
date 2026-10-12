"""The served directory as the object routes already call ``workspace`` on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.path import Path
from molab.workspace.folder import WORKSPACE_ROOT_KIND
from molab.workspace.scope import entities, require_entity

if TYPE_CHECKING:
    from molab.workspace.folder import Folder
    from molab.workspace.project import Project


class ScopeRoot:
    """Quacks like a Workspace whose listings stop at the serve boundary.

    ``.root`` is the opened directory. ``list_projects`` / ``get_project``
    follow rank: a served project is the only project, a served experiment
    has none. Everything else forwards to the mounted folder.
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

    def __getattr__(self, name: str) -> object:
        return getattr(self.folder, name)
