"""Workspace re-exports of ``molab.knowledge`` product classes.

Knowledge types live in ``molab.knowledge``. This module re-exports the same
objects and hosts ``write_knowledge`` sugar (``add_knowledge`` / ``knowledge``)
used by Project and Experiment.
"""

from __future__ import annotations

from pathlib import Path

from molab.ids import slugify
from molab.knowledge import (
    Finding,
    Knowledge,
    KnowledgeNotFoundError,
    Literature,
    Note,
    Observation,
    Plan,
    Report,
    SourceKind,
    SourceRef,
)
from molab.knowledge.errors import KnowledgeNotFoundError as _KnowledgeLookup
from molab.knowledge.naming import knowledge_filename

from .edges import EdgeRole
from .folder import Folder

KNOWLEDGE_CONTAINER = "knowledges"
PLAN_BOOK_NAME = "plan-book"
KNOWLEDGE_INDEX_FILENAME = "knowledges.json"

_PRODUCTS: dict[str, type[Knowledge]] = {
    "Note": Note,
    "Literature": Literature,
    "Report": Report,
    "Finding": Finding,
    "Plan": Plan,
    "Observation": Observation,
}

_SOURCED: tuple[type[Knowledge], ...] = (Finding, Report, Plan, Observation)


def parse_knowledge_class(name: str) -> type[Knowledge]:
    """Map a class name onto a Knowledge subclass (including condemned aliases)."""
    if name in _PRODUCTS:
        return _PRODUCTS[name]
    raise ValueError(
        f"unknown knowledge class {name!r}; expected one of: {', '.join(sorted(_PRODUCTS))}"
    )


def knowledge_dir(host: Folder, name: str) -> Path:
    """Absolute markdown path for knowledge named *name* under *host*."""
    stem = slugify(name) or name
    return Path(str(host.resolve())) / KNOWLEDGE_CONTAINER / f"{stem}.md"


def normalize_sources(
    sources: list[SourceRef | Folder | str] | None,
    *,
    default_host: Folder,
) -> list[SourceRef]:
    """Accept SourceRef, Folder, or free strings (dataset: / DOI: / path)."""
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


def _workspace_root(folder: Folder) -> Path:
    cur = Path(str(folder.resolve()))
    while True:
        if (cur / "workspace.json").is_file():
            return cur
        if cur.parent == cur:
            return Path(str(folder.resolve()))
        cur = cur.parent


def add_knowledge(
    self: Folder,
    name: str,
    of: type[Knowledge],
    text: str = "",
    *,
    sources: list[SourceRef | Folder | str] | None = None,
    created_by: str = "user",
    title: str = "",
) -> Knowledge:
    """Write knowledge under *self* (a Project or Experiment)."""
    from .knowledge_write import write_knowledge

    host = self
    cite: list[tuple[Folder, EdgeRole]] = []
    if type(host).__name__ == "Experiment":
        cite.append((host, "derived_from"))
    return write_knowledge(
        host,
        name=name,
        of=of,
        sources=normalize_sources(sources, default_host=host),
        created_by=created_by,
        text=text,
        title=title or name,
        cite=cite,
    )


def knowledge(self: Folder, name: str) -> Knowledge:
    """Get existing knowledge by name (must exist)."""
    host = self
    dest = knowledge_dir(host, name)
    try:
        return Knowledge.open(dest, fs=host._disk())
    except _KnowledgeLookup:
        raise KnowledgeNotFoundError(name) from None


def set_knowledge(
    self: Folder,
    name: str,
    of: type[Knowledge] | None = None,
    text: str | None = None,
    *,
    sources: list[SourceRef | Folder | str] | None = None,
    created_by: str | None = None,
    title: str = "",
) -> Knowledge:
    from .knowledge_write import write_knowledge

    host = self
    item = knowledge(host, name)
    existing_sources: list[SourceRef] = list(getattr(item, "_sources", ()) or [])
    return write_knowledge(
        host,
        name=name,
        of=of if of is not None else type(item),
        sources=(
            normalize_sources(sources, default_host=host)
            if sources is not None
            else existing_sources or normalize_sources(None, default_host=host)
        ),
        created_by=created_by if created_by is not None else "user",
        text=text if text is not None else item.read(),
        title=title or name,
    )


def del_knowledge(self: Folder, name: str) -> None:
    host = self
    dest = knowledge_dir(host, name)
    fs = host._disk()
    if fs.is_dir(str(dest)):
        fs.remove(str(dest), recursive=True)


def has_knowledge(self: Folder, name: str) -> bool:
    host = self
    dest = knowledge_dir(host, name)
    try:
        Knowledge.open(dest, fs=host._disk())
    except _KnowledgeLookup:
        return False
    return True


def knowledges(self: Folder) -> list[Knowledge]:
    host = self
    container = Path(str(host.resolve())) / KNOWLEDGE_CONTAINER
    fs = host._disk()
    if not fs.is_dir(str(container)):
        return []
    return list(Knowledge(container, fs=fs).walk())


__all__ = [
    "KNOWLEDGE_CONTAINER",
    "KNOWLEDGE_INDEX_FILENAME",
    "PLAN_BOOK_NAME",
    "Finding",
    "Knowledge",
    "KnowledgeNotFoundError",
    "Literature",
    "Note",
    "Observation",
    "Plan",
    "Report",
    "SourceKind",
    "SourceRef",
    "add_knowledge",
    "del_knowledge",
    "has_knowledge",
    "knowledge",
    "knowledge_dir",
    "knowledge_filename",
    "knowledges",
    "normalize_sources",
    "parse_knowledge_class",
    "set_knowledge",
]
