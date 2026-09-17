"""Mount OKF Concepts into a workspace tree — the ``Folder`` ↔ ``Concept`` adapter.

Two storage families meet here. A :class:`~molab.workspace.folder.Folder`
composes its path from a parent chain, replaying the frozen layout
(``projects/`` / ``experiments/`` / ``runs/run-``). A
:class:`~molab.knowledge.concept.Concept` *is* its path. They are deliberately
unrelated: the OKF library must work on a plain directory with no workspace in
sight.

Yet knowledge still belongs *in* the tree — a finding under the Run it came
from, notes beside their experiment. Everything that mounting needs from the
workspace side is an **absolute directory and a filesystem**, never the
``Folder`` class itself, so the adapter is this thin. It is the one place that
knows how to put a Concept inside a Folder, which keeps the layering honest in
both directions: ``knowledge`` never imports ``workspace``, and ``workspace``
reaches ``knowledge`` only through its public surface.

**One deliberate difference from ``add_folder``.** A Concept mounted here writes
``meta.yaml`` and nothing else — no ``metadata.json``. That file is the
*workspace entity* record, and a note is not a workspace entity; a Concept's
authority is its ``meta.yaml``. Nothing enumerates knowledge by
``metadata.json``, so pre-existing Concepts that still carry one read back
unchanged; it is simply vestigial and is neither migrated nor consulted.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from molab.ids import slugify
from molab.knowledge.concept import Concept, append_link
from molab.knowledge.concepts import Note
from molab.knowledge.edges import EdgeRole
from molab.knowledge.knowledge_item import KnowledgeItem

from .folder import Folder

if TYPE_CHECKING:
    from .assets.base import Asset
    from .doc_embed import EntitySummary

__all__ = [
    "concept_dir",
    "embed",
    "entity_summary",
    "get_item",
    "has_item",
    "mount_knowledge_item",
    "mount_note",
]


def concept_dir(host: Folder, name: str) -> Path:
    """The absolute directory a Concept named *name* occupies under *host*.

    *name* is slugified at this boundary (as the ``Bundle`` create verbs do), so
    callers may pass a human name.
    """
    return Path(str(host.resolve())) / (slugify(name) or name)


def _mount(host: Folder, name: str, cls: type[Concept]) -> tuple[Concept, bool]:
    """Idempotently materialize a *cls* Concept under *host*.

    Returns the Concept and whether this call created it — evaluated **before**
    the write, because a repeat call is not a creation.
    """
    directory = concept_dir(host, name)
    fs = host._disk()
    created = not fs.is_dir(str(directory))
    concept = cls(directory, fs=fs)
    concept.write_meta()
    return concept, created


def mount_note(host: Folder, name: str, *, body: str = "") -> Note:
    """Idempotently mount a :class:`Note` under the workspace Folder *host*.

    Args:
        host: The Folder to mount under (an ``Experiment``, a ``Run``, the root).
        name: Human name; slugified to the Concept dir name.
        body: Initial ``index.md`` narrative (written only when non-empty).

    Returns:
        The mounted note (the existing one on a repeat call).
    """
    note, _created = _mount(host, name, Note)
    if body:
        note.set_body(body)
    return cast("Note", note)


def mount_knowledge_item(host: Folder, name: str) -> tuple[KnowledgeItem, bool]:
    """Idempotently mount a :class:`KnowledgeItem` under *host*.

    Returns:
        ``(item, newly_created)`` — the flag drives one-shot event emission at
        the caller, so it must be read before any write (it is).
    """
    item, created = _mount(host, name, KnowledgeItem)
    return cast("KnowledgeItem", item), created


def has_item(host: Folder, name: str) -> bool:
    """Whether a :class:`KnowledgeItem` named *name* is already mounted under *host*."""
    return host._disk().is_dir(str(concept_dir(host, name)))


def get_item(host: Folder, name: str) -> KnowledgeItem:
    """The :class:`KnowledgeItem` named *name* under *host*.

    Raises:
        FileNotFoundError: If no Concept directory is mounted at that name.
    """
    directory = concept_dir(host, name)
    if not host._disk().is_dir(str(directory)):
        raise FileNotFoundError(f"no knowledge item {name!r} under {host.resolve()}")
    return KnowledgeItem(directory, fs=host._disk())


def embed(
    note: Note,
    target: Folder | Concept | Asset,
    *,
    root: str | Path,
    role: EdgeRole | None = None,
) -> None:
    """Embed a live workspace entity into document *note* as one typed edge.

    Writes a single typed markdown link through the sole edge-writer
    :func:`~molab.knowledge.concept.append_link` -- never a hand-built markdown
    string. *target* is a :class:`Folder` (a ``Run`` / ``Experiment`` /
    ``ReferenceConcept`` / ``Note``) or an
    :class:`~molab.workspace.assets.base.Asset` (resolved to its in-tree record
    dir ``<scope_dir>/assets/<asset_id>/`` and pointed at, never copied).

    With *role* ``None`` the per-kind default is used
    (:func:`~molab.workspace.doc_embed.default_role_for`): a ``Run`` /
    ``Experiment`` -> ``records``, a ``ReferenceConcept`` -> ``cites``, any
    ``Asset`` (or other) -> ``references``; all from the frozen
    :class:`~molab.knowledge.edges.EdgeRole` vocabulary.

    This is a free function rather than a ``Bundle`` method because its
    ``Folder | Asset`` signature is workspace-shaped: it cannot follow ``Bundle``
    into the OKF library without dragging the workspace layer behind it.

    Args:
        note: The document the edge originates from.
        target: The live entity to embed (a ``Folder`` or an ``Asset``).
        root: The workspace root, needed only to anchor an ``Asset``.
        role: An explicit edge role; defaults to the per-kind default.

    Raises:
        TypeError: If *target* is neither a ``Folder`` nor an ``Asset``.
        FileNotFoundError: If an ``Asset`` target has no on-disk record dir
            (a missing precondition -- raised, never silently downgraded).
    """
    from .doc_embed import default_role_for, resolve_embed_target

    dst = resolve_embed_target(target, root=root, pin=_pinned_folder)  # ty: ignore[invalid-argument-type]
    append_link(
        note,
        str(dst.resolve()),
        role=role if role is not None else default_role_for(target),  # ty: ignore[invalid-argument-type]
    )


def _pinned_folder(directory: Path) -> Folder:
    """A path-only ``Folder`` whose ``resolve()`` is *directory* exactly.

    Built without ``__init__`` to bypass name/kind validation: its only job is
    to name a directory for :func:`~molab.workspace.doc_embed.resolve_embed_target`,
    which wraps an ``Asset``'s in-tree record dir this way so the payload is
    only ever pointed at.
    """
    from molab.path import Path as MolPath

    from .fs_local import LocalFileSystem

    parent = Folder.__new__(Folder)
    parent._parent = None
    parent._name = directory.name
    parent._kind = "bundle.parent"
    parent._root_path = MolPath(str(directory.parent))  # type: ignore[assignment]
    parent._disk_backend = LocalFileSystem()
    parent._children_cache = {}
    return parent


def entity_summary(target: Folder | Concept | Asset, *, root: str | Path) -> EntitySummary:
    """Return a read-only :class:`EntitySummary` for *target* (a UI-card projection).

    Args:
        target: The entity to summarize (a ``Folder`` or an ``Asset``).
        root: The workspace root; required only to anchor an ``Asset``.
    """
    from .doc_embed import summarize_entity

    return summarize_entity(target, root=root)  # ty: ignore[invalid-argument-type]
