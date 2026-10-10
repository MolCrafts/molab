"""``molab.knowledge`` — path-identity knowledge, and the verbs that write it.

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
derivation on its own, returning the ``.md`` path.

What lives here: the Knowledge handle, the six classes, ``SourceRef``, typed
edges, the single ``folder(host, name, of)`` location derivation, BM25F
retrieval, named wiki sources, the read-only Zotero importer, and
``parse_class``. A document is written on the class:
``Note.mount(host, name)``, ``Finding.create(host, name, ...)``,
``Finding.harvest(run, ...)``, ``SourceRef.normalize(sources, default_host=...)``.
A new document's ``knowledge.created`` history is recorded by
:func:`molab.knowledge.write.write_knowledge`.

**Dependency direction.** ``molab.knowledge`` depends on ``molab.workspace`` —
a document's host is a workspace ``Folder``, and ``harvest`` takes a ``Run`` —
and that dependency is one-way. Every ``molab.workspace`` import lives
**inside a function body** or in an ``if TYPE_CHECKING:`` block (which never
executes), because ``molab/__init__.py`` eagerly loads ``molab.workspace``: a
module-level back-import would make this package import a cycle. A host that
cannot supply a git history or an id simply observes nothing.
"""

from .concept import Knowledge
from .concepts import (
    Finding,
    Literature,
    Note,
    Observation,
    Plan,
    Report,
    parse_class,
)
from .edges import Edge, EdgeRole
from .errors import KnowledgeNotFoundError
from .knowledge_item import SourceKind, SourceRef
from .location import folder
from .reference_meta import ReferenceMeta
from .search import (
    SearchHit,
    SearchResult,
)
from .sources import (
    KnowledgeScope,
    KnowledgeSourceStore,
    SourcedHit,
    SourceNotFoundError,
    WikiSource,
    resolve_source,
    search_sources,
)
from .zotero import ZoteroItem, read_zotero

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
    "parse_class",
    "read_zotero",
    "resolve_source",
    "search_sources",
]
