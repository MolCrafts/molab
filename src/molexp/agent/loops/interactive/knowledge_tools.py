"""Knowledge-native tools for the emergent :class:`InteractiveLoop` loop.

Three plain-Python callables — :func:`search_knowledge`, :func:`read_knowledge`,
:func:`list_knowledge_sources` — handed to pydantic-ai alongside the generic
file tools. They wrap the OKF library's verbs (BM25F-ranked
:func:`~molexp.knowledge.sources.search_sources`, path-as-identity
:meth:`Bundle.get`, reverse :meth:`Bundle.backlinks`) so the model reads
*knowledge* — typed items, sources, edges — instead of grepping raw markdown by
luck. Ranking means a question in the model's own words finds the document that
answers it, in English or Chinese.

Search spans the workspace **and** every knowledge base the operator registered
(``molexp knowledge sources add``), because a research group's methodology
usually lives in a shared wiki rather than in the workspace at hand. Hits are
tagged with their source and addressed as ``<source>:<path>``.

Same discipline as :mod:`.tools`: read-only, hard caps on every list, no
``pydantic_ai`` import (bare callables introspected by signature + docstring).
Path confinement still applies to the workspace (``_safe_path`` rejects escapes
before any I/O); a *registered* wiki is trusted by virtue of the operator having
registered it, and is reachable only by its name, never by a path the model
invents. Import direction: agent→workspace/knowledge (legal per the layer DAG).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from .tools import _MAX_FILE_BYTES, _safe_path

if TYPE_CHECKING:
    from molexp.knowledge import Bundle

__all__ = ["knowledge_tools"]

_MAX_SEARCH_ROWS = 20
"""Hits rendered per ``search_knowledge`` call."""

_MAX_EDGE_ROWS = 20
"""Out-edges / backlinks / sources rendered per ``read_knowledge`` call."""


def _bundle(root: Path) -> Bundle:
    """A plain OKF bundle over *root* — a registered wiki of unknown layout."""
    from molexp.knowledge import Bundle

    return Bundle(root)


def _workspace_bundle(root: Path) -> Bundle:
    """The workspace's own bundle — pruned to the layout it knows (run output dirs)."""
    from molexp.workspace.bundle import Bundle

    return Bundle(root)


def _resolve_ref(root: Path, ref: str) -> tuple[Bundle, str, str]:
    """Split a ``[<source>:]<path>`` ref into its bundle, source name and path.

    A bare path means the workspace and stays path-confined; a ``<source>:``
    prefix names a registered knowledge base.

    Raises:
        ValueError: If the named source is not registered — with the registered
            names listed, so the model can correct itself in one turn.
    """
    from molexp.knowledge.sources import KnowledgeSourceStore, SourceNotFoundError

    source_name, _, path = ref.partition(":") if ":" in ref else ("", "", ref)
    if not source_name:
        _safe_path(root, path)  # confinement first — before any bundle I/O
        return _workspace_bundle(root), "", path
    store = KnowledgeSourceStore(root)
    try:
        source_root = store.get(source_name).path()
    except SourceNotFoundError:
        known = ", ".join(s.name for s, _ in store.list()) or "(none registered)"
        raise ValueError(
            f"unknown knowledge source {source_name!r}; registered sources: {known}"
        ) from None
    return _bundle(source_root), source_name, path


def _meta_head(meta: Mapping[str, object]) -> list[str]:
    """Render the identity lines of a Concept's ``meta.yaml`` head."""
    rows = [f"type: {meta.get('type', 'unknown')}"]
    for field in ("kind", "status", "created_by"):
        if meta.get(field):
            rows.append(f"{field}: {meta[field]}")
    sources = meta.get("sources")
    if isinstance(sources, list) and sources:
        rows.append("sources:")
        for source in sources[:_MAX_EDGE_ROWS]:
            if isinstance(source, dict):
                rows.append(f"  - {source.get('kind', '?')}: {source.get('ref', '?')}")
        if len(sources) > _MAX_EDGE_ROWS:
            rows.append(f"  (+{len(sources) - _MAX_EDGE_ROWS} more sources)")
    return rows


def knowledge_tools(workspace_root: Path) -> tuple[Callable[..., str], ...]:
    """Build the knowledge tool callables confined to ``workspace_root``.

    Args:
        workspace_root: The workspace — searched as a bundle itself, and the
            source of the workspace-scoped knowledge-source config tier.

    Returns:
        ``(search_knowledge, list_knowledge_sources, read_knowledge)`` in a
        stable order.
    """
    root = Path(workspace_root)

    def search_knowledge(query: str, concept_type: str | None = None) -> str:
        """Search the group's knowledge bases by meaning, not by exact wording.

        Use this BEFORE planning or answering questions about methodology,
        protocols, parameter choices, or prior experiments. It searches the
        workspace's own notes AND every knowledge base registered on this host
        (a lab wiki, a protocol repo), ranking by keyword relevance — so ask a
        real question ("how do we choose the cooling rate for Tg?") rather than
        guessing a filename. Works in English and Chinese.

        Returns ranked refs; read a promising one in full with
        ``read_knowledge``.

        Args:
            query: What you want to know, in words.
            concept_type: Optional exact Concept type filter, e.g.
                ``"knowledge.item"`` or ``"note.note"``.
        """
        from molexp.knowledge.sources import search_sources

        hits = search_sources(
            query,
            workspace_root=root,
            concept_type=concept_type,
            limit=_MAX_SEARCH_ROWS,
            # The workspace is searched through its own (layout-pruned) bundle;
            # registered wikis are opened plain by ``search_sources`` itself.
            workspace_searcher=lambda: _workspace_bundle(root).search(
                query, concept_type=concept_type, limit=_MAX_SEARCH_ROWS
            ),
        )
        if not hits:
            return f"no knowledge matches for {query!r}"
        rows = []
        for sourced in hits:
            entry = sourced.hit.entry
            row = f"{sourced.ref} · {entry.type} · {entry.title or entry.path}"
            if sourced.source:
                row += f" · source={sourced.source}"
            if sourced.hit.snippet:
                row += f" · {sourced.hit.snippet}"
            rows.append(row)
        if len(hits) >= _MAX_SEARCH_ROWS:
            rows.append(f"(showing the top {_MAX_SEARCH_ROWS} — refine the query for more)")
        return "\n".join(rows)

    def list_knowledge_sources() -> str:
        """List the knowledge bases searchable from here.

        Use when ``search_knowledge`` finds nothing and you want to know whether
        anything is registered at all, or to scope a search to one wiki.
        """
        from molexp.knowledge.sources import KnowledgeSourceStore

        entries = KnowledgeSourceStore(root).list()
        rows = [f"(workspace) {root}"]
        rows += [
            f"{source.name} · {source.path()}"
            + (f" · {source.description}" if source.description else "")
            for source, _scope in entries
        ]
        if not entries:
            rows.append("(no external knowledge bases registered on this host)")
        return "\n".join(rows)

    def read_knowledge(path: str) -> str:
        """Read one knowledge document in full: metadata, body, and edges.

        Use after ``search_knowledge`` surfaces a promising ref. Returns the
        Concept's typed head (kind / status / sources for a knowledge item), its
        narrative body, what it cites (out-edges), and what cites it
        (backlinks).

        Args:
            path: The ref exactly as ``search_knowledge`` returned it — either
                ``"<source>:<path>"`` for a registered knowledge base or a bare
                workspace-relative path (e.g.
                ``"projects/p/experiments/e/finding-abc"``).
        """
        from molexp.knowledge.errors import ConceptNotFoundError

        bundle, _source, rel = _resolve_ref(root, path)
        try:
            concept = bundle.get(rel)
        except (ConceptNotFoundError, FileNotFoundError) as exc:
            raise ValueError(
                f"no knowledge Concept at {path!r} — use search_knowledge to find valid refs"
            ) from exc

        rows = [f"# {path}", *_meta_head(concept.read_meta())]

        body = concept.read_index() or ""
        raw = body.encode("utf-8")
        if len(raw) > _MAX_FILE_BYTES:
            body = raw[:_MAX_FILE_BYTES].decode("utf-8", errors="ignore") + "\n... (body truncated)"
        rows += ["", "## body", body.strip() or "(empty body)"]

        edges = concept.typed_out_edges()[:_MAX_EDGE_ROWS]
        rows += ["", "## cites (out-edges)"]
        rows += [f"- [{edge.role}] {edge.target}" for edge in edges] or ["(none)"]

        backlinks = bundle.backlinks(concept)[:_MAX_EDGE_ROWS]
        rows += ["", "## cited by (backlinks)"]
        rows += [f"- [{link.role}] {bundle.rel_path(link.source)}" for link in backlinks] or [
            "(none)"
        ]
        return "\n".join(rows)

    return (search_knowledge, list_knowledge_sources, read_knowledge)
