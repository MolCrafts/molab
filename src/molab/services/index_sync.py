"""``molab index sync`` — rebuild every derived block of every ``index.md``.

Two layers write into a Folder's ``index.md`` frontmatter, and neither may
name the other: workspace derives the reserved ``index:`` keys from the tree
(D89), and knowledge asks for the ``index.knowledges`` section through the
opaque ``Folder.set_index_section``. The full rebuild therefore composes them
here, in the service layer above both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = ["IndexSyncResult", "sync"]


class IndexSyncResult(BaseModel):
    """What one full rebuild touched."""

    model_config = ConfigDict(frozen=True)

    records: int
    """Records whose reserved ``index:`` keys were rebuilt (visited)."""
    sections: int
    """Hosts whose ``index.knowledges`` section was rewritten."""


def sync(ws: Workspace) -> IndexSyncResult:
    """Rebuild the reserved keys of every record, then every knowledge section."""
    from molab.knowledge.index_section import rebuild_sections
    from molab.workspace.index_projection import sync_index

    records = sync_index(ws)
    sections = rebuild_sections(ws)
    return IndexSyncResult(records=records, sections=sections)
