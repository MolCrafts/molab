"""``molexp.knowledge`` — the Open Knowledge Format library.

A *Concept* is a directory holding two files: ``meta.yaml`` (the typed head,
whose ``type`` names the Concept's class) and ``index.md`` (the narrative, whose
markdown links **are** the knowledge graph). A *Bundle* is any directory tree of
them. That is the whole format — plain directories, plain YAML, plain Markdown,
with the filesystem as the database.

**It needs no workspace.** A research group's wiki is a directory (often a git
repo); a molexp workspace is also a bundle, because its entity dirs carry the
same ``meta.yaml`` marker. Both open the same way::

    from molexp.knowledge import Bundle

    wiki = Bundle("/data/group/wiki")
    for hit in wiki.search("glass transition").hits:
        print(hit.entry.path, hit.entry.title)

Concepts are addressed by absolute path — identity *is* location — so mounting
one at any depth needs no parent chain and no path arithmetic.

What lives here: the concept-type registry (``concept_type`` /
``register_concept_type`` / ``resolve_concept_type``), ``Concept`` and the typed
subclasses shipped with it (``Note``, ``ReferenceConcept``, ``KnowledgeItem``),
the typed edge vocabulary (``EdgeRole`` / ``append_link``), the ``Bundle``
façade, its derived index, BM25F keyword retrieval that handles CJK
(:mod:`~molexp.knowledge.retrieval`), a registry of named bundles
(:mod:`~molexp.knowledge.sources`, so several group wikis can be searched at
once), and the read-only Zotero importer.

What does not: anything that knows about runs, experiments or assets. Mounting a
Concept *into* a molexp workspace is the workspace layer's job
(``molexp.workspace.knowledge_mount``), and Concept-creation events reach that
layer through the inversion seam in :mod:`molexp.knowledge.hooks` — so this
library imports stdlib, pydantic/pyyaml/pathspec, and the layer-0 primitives,
and nothing else (enforced by ``tests/test_knowledge/test_import_guard.py``).
"""

from .bundle import Backlink, Bundle
from .bundle_index import (
    BundleIndex,
    ConceptIndexEntry,
    SearchHit,
    SearchResult,
    extract_title,
)
from .concept import (
    INDEX_FILENAME,
    META_YAML_FILENAME,
    Concept,
    LinkScan,
    append_link,
    concept_from_dir,
)
from .concept_meta import ConceptMeta
from .concepts import NOTE_KIND, REFERENCE_KIND, Note, ReferenceConcept
from .edges import DEFAULT_EDGE_ROLE, Edge, EdgeRole
from .errors import ConceptNotFoundError
from .hooks import set_concept_created_hook
from .knowledge_item import (
    KNOWLEDGE_ITEM_KIND,
    KNOWLEDGE_KINDS,
    KnowledgeItem,
    KnowledgeKind,
    KnowledgeMeta,
    SourceKind,
    SourceRef,
    parse_knowledge_kind,
)
from .note_meta import NOTE_TYPE, NoteMeta
from .reference_meta import ReferenceMeta
from .sources import (
    KnowledgeScope,
    KnowledgeSourceStore,
    SourcedHit,
    SourceNotFoundError,
    WikiSource,
    open_bundle,
    resolve_source,
    search_sources,
)
from .types import concept_type, register_concept_type, resolve_concept_type
from .zotero import ZoteroItem, read_zotero_items

__all__ = [
    "DEFAULT_EDGE_ROLE",
    "INDEX_FILENAME",
    "KNOWLEDGE_ITEM_KIND",
    "KNOWLEDGE_KINDS",
    "META_YAML_FILENAME",
    "NOTE_KIND",
    "NOTE_TYPE",
    "REFERENCE_KIND",
    "Backlink",
    "Bundle",
    "BundleIndex",
    "Concept",
    "ConceptIndexEntry",
    "ConceptMeta",
    "ConceptNotFoundError",
    "Edge",
    "EdgeRole",
    "KnowledgeItem",
    "KnowledgeKind",
    "KnowledgeMeta",
    "KnowledgeScope",
    "KnowledgeSourceStore",
    "LinkScan",
    "Note",
    "NoteMeta",
    "ReferenceConcept",
    "ReferenceMeta",
    "SearchHit",
    "SearchResult",
    "SourceKind",
    "SourceNotFoundError",
    "SourceRef",
    "SourcedHit",
    "WikiSource",
    "ZoteroItem",
    "append_link",
    "concept_from_dir",
    "concept_type",
    "extract_title",
    "open_bundle",
    "parse_knowledge_kind",
    "read_zotero_items",
    "register_concept_type",
    "resolve_concept_type",
    "resolve_source",
    "search_sources",
    "set_concept_created_hook",
]
