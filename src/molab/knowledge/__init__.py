"""``molab.knowledge`` — path-identity knowledge, and the verbs that write it.

A document is a markdown file under ``knowledges/``: YAML frontmatter names
the class (``class: Finding``), the rest is the narrative. Path is identity::

    from molab.knowledge import Knowledge, Note

    wiki = Knowledge("/data/group/wiki")
    for hit in wiki.search("glass transition").hits:
        print(hit.entry.path, hit.entry.title)

    note = Note("/data/group/wiki/cooling")
    note.write("# Cooling\n")
    Note("/data/group/wiki/cooling.md")

The subclasses are ``Note``, ``Literature``, ``Report``, ``Finding``,
``Plan``, ``Roadmap``, ``Todo``, ``Milestone``, ``Observation``, and
``Delegation``. A Plan
is the campaign overview; Roadmap, Todo, and Milestone are the other three
planning documents and cite that Plan. Failure analysis is a Report; harvest
of a scientific outcome is a Finding.

A path, or a **host plus a name**: ``Note(experiment, "Tg Cooling")`` derives
``<experiment>/knowledges/tg-cooling.md`` (and the host's own disk) without
touching disk. ``.path`` is that file. The base class does not construct a
subclass, and it has no ``folder`` or ``parse`` method.

What lives here: the Knowledge handle, the document classes, ``SourceRef``, typed
edges, BM25F retrieval, named wiki sources, and the read-only Zotero importer.
Construct the document you mean: ``Note(host, name)``,
``Finding(host, name, sources=...)``. ``Finding.harvest(run, ...)`` and
``GeneratedParts(run).view(...)`` write one.
``ZoteroLibrary(path).items()`` reads a library.
``KnowledgeSourceStore(root).search(query)`` and
``SourceRef.normalize(sources, default_host=...)`` stay.
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
    Delegation,
    Finding,
    Literature,
    Milestone,
    Note,
    Observation,
    Plan,
    Report,
    Roadmap,
    Todo,
)
from .delegation import DelegationRecord
from .edges import Edge, EdgeRole
from .errors import KnowledgeNotFoundError
from .knowledge_item import SourceKind, SourceRef
from .parts import GeneratedPart, GeneratedParts
from .planning import Campaign, PlanningDocument, campaign_of, check_campaign
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
)
from .zotero import ZoteroItem

__all__ = [
    "Campaign",
    "Delegation",
    "DelegationRecord",
    "Edge",
    "EdgeRole",
    "Finding",
    "GeneratedPart",
    "GeneratedParts",
    "Knowledge",
    "KnowledgeNotFoundError",
    "KnowledgeScope",
    "KnowledgeSourceStore",
    "Literature",
    "Milestone",
    "Note",
    "Observation",
    "Plan",
    "PlanningDocument",
    "ReferenceMeta",
    "Report",
    "Roadmap",
    "SearchHit",
    "SearchResult",
    "SourceKind",
    "SourceNotFoundError",
    "SourceRef",
    "SourcedHit",
    "Todo",
    "WikiSource",
    "ZoteroItem",
    "campaign_of",
    "check_campaign",
]
