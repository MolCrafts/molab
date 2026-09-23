"""The knowledge projection — the single producer of ``WorkspaceContext.knowledge``.

``WorkspaceContext`` (and its :class:`~molab.workspace.workspace_context.KnowledgeRef`
row) stays workspace-owned: the *shape* of the read-model lives below, in
``molab.workspace``. What lives **here** is the one producer of the ``knowledge``
field, so the harness, the server and the CLI all read one projection instead of
walking the tree three ways (CLAUDE.md: CLI commands and server routes both call
services, never each other).

A raw :func:`~molab.workspace.workspace_context.assemble_workspace_context`
carries ``knowledge == []`` **by design** — the workspace assembler projects the
layers it owns. :func:`context_with_knowledge` is the door to the populated
context: it assembles the rest and covers ``knowledge`` with
:func:`project_knowledge`.

Enumeration is ``molab.knowledge``'s, not the workspace's: a workspace-scope
handle wraps the workspace root (``Knowledge(workspace.root, fs=workspace.fs)``,
never ``Knowledge(root, "knowledges")``, which would nest one level deeper), and
the title comes from :func:`molab.knowledge.bundle_index.extract_title` — the
function's own home. Both functions are pure reads: no write, no cache, no
global state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from molab.knowledge import Finding, Knowledge, Literature, Note, Observation, Plan, Report
from molab.knowledge.bundle_index import extract_title
from molab.workspace import ContextFocus, KnowledgeRef, WorkspaceContext

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = ["context_with_knowledge", "project_knowledge"]


def project_knowledge(workspace: Workspace) -> list[KnowledgeRef]:
    """Project the knowledge tree under *workspace* into read-model rows.

    One walk of the workspace-scope Knowledge handle, in walk order. A built-in
    Knowledge document is a file (``knowledges/<name>.md``), so a row's ``path``
    is the markdown file's workspace-relative POSIX path.

    Args:
        workspace: The workspace whose knowledge tree is projected.

    Returns:
        One :class:`~molab.workspace.KnowledgeRef` per Knowledge document.
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
) -> WorkspaceContext:
    """Assemble the **complete** workspace read-model, knowledge included.

    Every other field is the workspace's own assembly
    (:meth:`~molab.workspace.Workspace.context`); ``knowledge`` is covered —
    never appended to — by :func:`project_knowledge`, so the two producers
    cannot stack into a doubled list.

    Args:
        workspace: The workspace to project.
        focus: Caller-supplied ephemeral focus; echoed, never stored.

    Returns:
        A complete :class:`~molab.workspace.WorkspaceContext`. Callers consume
        it as given — a caller patching ``knowledge`` in with its own
        ``model_copy`` is the duplicate producer this module exists to remove.
    """
    return workspace.context(focus=focus).model_copy(
        update={"knowledge": project_knowledge(workspace)}
    )
