"""``molab.knowledge`` — path-identity knowledge, usable with no workspace.

A document is a markdown file under ``knowledges/``: YAML frontmatter names
the class (``class: Finding``), the rest is the narrative. Path is identity::

    from molab.knowledge import Knowledge, Note

    wiki = Knowledge("/data/group/wiki")
    for hit in wiki.search("glass transition").hits:
        print(hit.entry.path, hit.entry.title)

    note = Note("/data/group/wiki/cooling")
    note.write("# Cooling\n")
    Knowledge.open("/data/group/wiki/cooling")

The six subclasses are ``Note``, ``Literature``, ``Report``, ``Finding``,
``Plan``, ``Observation``. Failure analysis is a Report; harvest of a scientific
outcome is a Finding.

A path, or a **host plus a name**: ``Note(experiment, "Tg Cooling")`` derives
``<experiment>/knowledges/tg-cooling.md`` (and the host's own disk) without
touching disk; ``folder(experiment, "Tg Cooling", Note)`` is that same
derivation on its own, returning the ``.md`` path for a ``FILE_DOCUMENT`` class
and the bare ``<slug>/`` directory otherwise.

What lives here: the concept-type registry, the Knowledge handle, the six
classes, ``SourceRef``, typed edges, the single ``folder(host, name, of)``
location derivation, BM25F retrieval, named wiki sources, and the read-only
Zotero importer.

What does not: anything that knows about runs, experiments or assets. Mounting a
document *into* a molab workspace is the workspace layer's job
(``write_knowledge``), and creation events reach that layer through the
inversion seam in :mod:`molab.knowledge.hooks`.
"""

from .bundle_index import (
    SearchHit,
    SearchResult,
)
from .concept import Knowledge
from .concepts import Finding, Literature, Note, Observation, Plan, Report
from .edges import Edge, EdgeRole
from .errors import KnowledgeNotFoundError
from .knowledge_item import SourceKind, SourceRef
from .location import folder
from .reference_meta import ReferenceMeta
from .sources import (
    KnowledgeScope,
    KnowledgeSourceStore,
    SourcedHit,
    SourceNotFoundError,
    WikiSource,
    resolve_source,
    search_sources,
)
from .zotero import ZoteroItem, read_zotero_items

__all__ = [
    "Edge",
    "EdgeRole",
    "Finding",
    "Knowledge",
    "KnowledgeNotFoundError",
    "KnowledgeScope",
    "KnowledgeSourceStore",
    "Literature",
    "Note",
    "Observation",
    "Plan",
    "ReferenceMeta",
    "Report",
    "SearchHit",
    "SearchResult",
    "SourceKind",
    "SourceNotFoundError",
    "SourceRef",
    "SourcedHit",
    "WikiSource",
    "ZoteroItem",
    "folder",
    "read_zotero_items",
    "resolve_source",
    "search_sources",
]
