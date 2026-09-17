"""Session harvest + export — agent-record-export-05.

``harvest_session`` turns an on-disk :class:`~molab.harness.agent.folders.AgentSession`
into sourced :class:`~molab.workspace.knowledge.Knowledge` via
:func:`~molab.workspace.knowledge_write.write_knowledge`.

``export_session_zip`` archives the session folder via
:func:`~molab.workspace.archive.archive_folder_zip` — the single zip writer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.ids import slugify
from molab.workspace.archive import archive_folder_zip
from molab.workspace.knowledge import Knowledge, SourceRef
from molab.workspace.knowledge_write import write_knowledge

if TYPE_CHECKING:
    from molab.harness.agent.folders import AgentSession
    from molab.workspace.folder import Folder

__all__ = ["export_session_zip", "harvest_session"]


def harvest_session(
    session: AgentSession,
    *,
    cls: type[Knowledge],
    narrative: str,
    created_by: str,
    host: Folder | None = None,
    name: str | None = None,
) -> Knowledge:
    """Harvest a finished agent session into a typed KnowledgeItem.

    Args:
        session: On-disk agent session folder (has messages / meta).
        cls: Knowledge subclass (the category).
        narrative: Non-empty interpretation of the session.
        created_by: Author string.
        host: Parent Folder; defaults to the session's parent.
        name: Optional Concept name; default ``session-harvest-{slug}-{id}``.

    Returns:
        The written Knowledge.

    Raises:
        ValueError: Empty narrative.
    """
    if not narrative.strip():
        raise ValueError(
            "harvest_session requires a non-empty narrative — knowledge is interpretation"
        )
    parent = host if host is not None else session.parent
    if parent is None:
        raise ValueError("harvest_session needs a host Folder (session has no parent)")

    item_name = name or f"session-{slugify(cls.__name__)}-{session.name}"
    body_lines = [
        f"# [{cls.__name__}] agent session {session.name}",
        "",
        narrative.strip(),
        "",
        "## Session",
        "",
        f"- status: {session.status}",
        f"- goal: {session.goal_summary or '(none)'}",
    ]
    # Optional lossless model history size (feedstock for export).
    try:
        n_msgs = len(session.read_messages())
        body_lines.append(f"- model_messages: {n_msgs}")
    except Exception:
        pass
    body = "\n".join(body_lines).rstrip() + "\n"

    return write_knowledge(
        parent,
        name=item_name,
        cls=cls,
        sources=[
            SourceRef(kind="agent_action", ref=session.name),
        ],
        created_by=created_by,
        body=body,
        cite=[(session, "derived_from")],
        title=f"Session {session.name}",
    )


def export_session_zip(session: AgentSession) -> bytes:
    """Zip the session directory via the workspace archive core.

    Returns:
        Zip bytes of the session folder (meta, entries, messages, …).
    """
    return archive_folder_zip(session)
