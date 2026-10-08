"""The knowledge read-model and its one producer.

:class:`KnowledgeContext` extends the workspace read-model with the document
rows. :func:`context_with_knowledge` is the only producer: the server and the
CLI both call it instead of walking the tree twice.

Enumeration is a workspace-scope handle (``Knowledge(workspace.root, fs=workspace.fs)``).
The title comes from :func:`molab.knowledge.search.extract_title`. Both
functions are pure reads: no write, no cache, no global state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from molab.knowledge import Finding, Knowledge, Literature, Note, Observation, Plan, Report
from molab.knowledge.search import extract_title
from molab.workspace import ContextFocus, WorkspaceContext

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = [
    "KnowledgeContext",
    "KnowledgeRef",
    "context_with_knowledge",
    "project_knowledge",
]


class KnowledgeRef(BaseModel, frozen=True):
    """A knowledge document's identity: workspace-relative ``.md`` path, class name, title."""

    path: str
    type: str
    title: str
    id: str | None = None


class KnowledgeContext(WorkspaceContext, frozen=True):
    """Workspace read-model plus the documents under it."""

    knowledge: list[KnowledgeRef] = Field(default_factory=list)


def project_knowledge(workspace: Workspace) -> list[KnowledgeRef]:
    """Project the knowledge tree under *workspace* into read-model rows.

    One walk of the workspace-scope Knowledge handle, in walk order. A built-in
    Knowledge document is a file (``knowledges/<name>.md``), so a row's ``path``
    is the markdown file's workspace-relative POSIX path.

    Args:
        workspace: The workspace whose knowledge tree is projected.

    Returns:
        One :class:`KnowledgeRef` per knowledge document.
    """
    rows: list[KnowledgeRef] = []
    for concept in Knowledge(workspace.root, fs=workspace.fs).walk():
        if isinstance(concept, Note | Literature | Report | Finding | Plan | Observation):
            name = concept.name
            rows.append(
                KnowledgeRef(
                    path=Path(concept.path).relative_to(workspace.root).as_posix(),
                    type=type(concept).__name__,
                    title=extract_title(concept.read()) or name,
                    id=str(name) if name is not None else None,
                )
            )
    return rows


def context_with_knowledge(
    workspace: Workspace,
    *,
    focus: ContextFocus | None = None,
) -> KnowledgeContext:
    """Assemble the complete read-model, documents included.

    Every other field is the workspace's own assembly
    (:meth:`~molab.workspace.Workspace.context`). Document rows come from
    :func:`project_knowledge` and are not patched onto the base model.

    Args:
        workspace: The workspace to project.
        focus: Caller-supplied ephemeral focus; echoed, never stored.

    Returns:
        A :class:`KnowledgeContext`. Callers consume it as given.
    """
    base = workspace.context(focus=focus)
    return KnowledgeContext(**dict(base), knowledge=project_knowledge(workspace))
