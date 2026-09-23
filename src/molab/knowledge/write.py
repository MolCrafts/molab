"""The verbs that write Knowledge *into* a molab workspace tree.

``molab.knowledge`` owns the knowledge storage layout, so it owns the verbs
that write into it: a sourced document (:func:`write_knowledge`), a bare note
mount (:func:`mount_note`) and the source normalization
(:func:`normalize_sources`). The destination is derived by
:func:`molab.knowledge.location.folder` — the one derivation — and the bytes
land through :meth:`~molab.knowledge.concept.Concept.write`, the one
persistence path. No new format, no second edge writer.

**The workspace ``Folder`` family is the host, and it is imported lazily.**
``molab/__init__.py`` eagerly loads ``molab.workspace``, so a module-level
``from molab.workspace… import …`` would make ``import molab.knowledge`` a
cycle. Every such import therefore sits in a function body (or an
``if TYPE_CHECKING:`` block, which never executes at runtime) — enforced by
``tests/test_knowledge/test_import_guard.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from molab.fs import PathArg

from .concept import Knowledge, append_link
from .concepts import Finding, Note, Observation, Plan, Report
from .embed import resolve_embed_target
from .knowledge_item import SourceKind, SourceRef
from .location import folder

if TYPE_CHECKING:
    from molab.workspace.folder import Folder

    from .concept import Concept
    from .edges import EdgeRole

__all__ = ["mount_note", "normalize_sources", "write_knowledge"]

_LOG = logging.getLogger(__name__)


def _workspace_root(host: Folder) -> Path:
    """The nearest ancestor of *host* holding a ``workspace.json`` (itself if none)."""
    cur = Path(str(host.resolve()))
    while True:
        if (cur / "workspace.json").is_file():
            return cur
        if cur.parent == cur:
            return Path(str(host.resolve()))
        cur = cur.parent


def write_knowledge(
    host: Folder,
    *,
    name: str,
    of: type[Knowledge],
    sources: list[SourceRef],
    created_by: str,
    text: str,
    cite: Sequence[tuple[Folder | Concept | PathArg, EdgeRole]] = (),
    title: str = "",
) -> Knowledge:
    """Write sourced Knowledge under *host* (idempotent on *name*).

    Args:
        host: Parent (a Project or Experiment).
        name: Document name; slugified to the landed filename.
        of: Knowledge subclass — this **is** the category (``Plan``, ``Finding``).
        sources: Non-empty source list for sourced classes.
        created_by: Author (person or ``agent:…`` / ``PlanOrchestrator/…``).
        text: Narrative for the document.
        cite: Optional ``(target, EdgeRole)`` pairs.
        title: Display title accepted by callers; identity is *name*.

    Returns:
        The written Knowledge document.

    Raises:
        TypeError: If *host* is neither a path nor a ``Folder``-family object.
        ValueError: If *of* is a sourced class and *sources* is empty.
    """
    _ = title
    dest = folder(host, name, of)
    fs = host._disk()
    if of is Finding or of is Report or of is Plan or of is Observation:
        item = of(dest, sources=list(sources), fs=fs)
    else:
        item = of(dest, fs=fs)
    item.write(text, {"created_by": created_by, "name": name})
    _apply_cites(item, cite, host=host)
    return item


def _apply_cites(
    item: Knowledge,
    cite: Sequence[tuple[Folder | Concept | PathArg, EdgeRole]],
    *,
    host: Folder,
) -> None:
    """Write each cite as a typed edge — best-effort, one try per target.

    The document is already durable when an edge fails, so a single failed
    citation is logged and skipped rather than turning a successful write into
    an error.
    """
    if not cite:
        return
    root = _workspace_root(host)
    for source, role in cite:
        try:
            _cite(item, source, role=role, root=root)
        except Exception:
            _LOG.warning(
                "write_knowledge: cite failed for %s role=%s",
                getattr(source, "name", source),
                role,
                exc_info=True,
            )


def _cite(
    item: Knowledge,
    source: Folder | Concept | PathArg,
    *,
    role: EdgeRole,
    root: Path,
) -> None:
    """Append one typed edge for *source*, in the branch its family demands.

    Three branches, and none of them silently drops an edge:

    - a ``Folder`` / ``Asset`` goes through
      :func:`~molab.knowledge.embed.resolve_embed_target` (the only resolver for
      those two families) and links the directory it normalizes to;
    - a Knowledge document goes through :meth:`~molab.knowledge.concept.Concept.ref`;
    - anything else is taken as a bare path and linked verbatim — never handed
      to ``resolve_embed_target``, which would ``TypeError`` on it and lose the
      edge.
    """
    from molab.workspace.assets.base import Asset
    from molab.workspace.folder import Folder

    if isinstance(source, (Folder, Asset)):
        append_link(item, resolve_embed_target(source, root=root), role=role)
        return
    if isinstance(source, Knowledge) and type(source) is not Knowledge:
        item.ref(source, role=role)
        return
    append_link(item, source, role=role)


def mount_note(host: Folder, name: str, *, body: str = "") -> Note:
    """Idempotently mount a :class:`Note` under the workspace Folder *host*.

    A mount **materializes the document even with an empty body** — a bare
    marker is what makes the note visible to a bundle walk — and a repeat call
    never truncates an existing body, including a repeat that passes
    ``body=""``.

    Args:
        host: The Folder to mount under (an ``Experiment``, a ``Run``, the root).
        name: Human name; slugified to the landed filename.
        body: Initial narrative, written only on the call that creates the note.

    Returns:
        The mounted note (the existing one on a repeat call).

    Raises:
        TypeError: If *host* is neither a path nor a ``Folder``-family object.
    """
    dest = folder(host, name, Note)
    note = Note(dest, fs=host._disk())
    if body or not note.exists():
        note.write(body)
    return note


def normalize_sources(
    sources: list[SourceRef | Folder | str] | None,
    *,
    default_host: Folder,
) -> list[SourceRef]:
    """Normalize a caller's free-form source list into typed :class:`SourceRef`\\ s.

    Accepts ``SourceRef``\\ s as-is, maps a ``Folder`` by its class name
    (``Run`` -> ``run``, ``Experiment`` -> ``experiment``, anything else ->
    ``file``), and classifies a free string by shape (``dataset:`` / ``model:`` /
    ``plugin:`` and a plain path -> ``file``; ``DOI:`` / a bare ``10.`` ->
    ``reference``). An empty request yields the host itself, as an
    ``experiment`` when the host is an Experiment and a ``file`` otherwise.

    Args:
        sources: The caller's sources — typed refs, folders, or free strings.
        default_host: The host the document lives under, used when *sources* is
            empty (and to read the host's own id).

    Returns:
        One :class:`SourceRef` per source, in input order.
    """
    from molab.workspace.folder import Folder

    if not sources:
        host_name = type(default_host).__name__
        kind: SourceKind = "experiment" if host_name == "Experiment" else "file"
        return [SourceRef(kind=kind, ref=getattr(default_host, "id", default_host.name))]
    out: list[SourceRef] = []
    for item in sources:
        if isinstance(item, SourceRef):
            out.append(item)
        elif isinstance(item, Folder):
            cls_name = type(item).__name__
            mapped: SourceKind = "file"
            if cls_name == "Run":
                mapped = "run"
            elif cls_name == "Experiment":
                mapped = "experiment"
            out.append(SourceRef(kind=mapped, ref=getattr(item, "id", item.name)))
        else:
            text = str(item)
            if text.startswith(("dataset:", "model:", "plugin:")):
                out.append(SourceRef(kind="file", ref=text))
            elif text.upper().startswith("DOI:") or text.startswith("10."):
                out.append(SourceRef(kind="reference", ref=text))
            else:
                out.append(SourceRef(kind="file", ref=text))
    return out
