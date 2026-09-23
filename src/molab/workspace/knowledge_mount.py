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

from .folder import Folder
from .knowledge import KNOWLEDGE_CONTAINER

if TYPE_CHECKING:
    from .assets.base import Asset
    from .doc_embed import EntitySummary

__all__ = [
    "concept_dir",
    "embed",
    "entity_summary",
    "mount_note",
]


def concept_dir(host: Folder, name: str) -> Path:
    """The absolute directory a Concept named *name* occupies under *host*.

    Knowledge lives at ``<host>/knowledges/<slug>/``.
    """
    return Path(str(host.resolve())) / KNOWLEDGE_CONTAINER / (slugify(name) or name)


def _mount(host: Folder, name: str, cls: type[Concept]) -> tuple[Concept, bool]:
    """Idempotently materialize a *cls* Concept under *host*.

    Returns the Concept and whether this call created it — evaluated **before**
    the write, because a repeat call is not a creation.
    """
    directory = concept_dir(host, name)
    fs = host._disk()
    created = not fs.is_dir(str(directory))
    concept = cls(directory, fs=fs)
    if hasattr(concept, "write"):
        concept.write()
    else:
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
        note.write(body)
    return cast("Note", note)


def embed(
    note: Concept,
    target: Concept | Folder | Asset,
    *,
    root: str | Path,
    role: EdgeRole | None = None,
) -> None:
    """Embed a live workspace entity into document *note* as one typed edge.

    Any Concept can carry an edge (a ``Note`` narrating a run, a
    ``KnowledgeItem`` citing its source), so *note* is typed at the family,
    not at ``Note``.

    Writes a single typed markdown link through the sole edge-writer
    :func:`~molab.knowledge.concept.append_link` -- never a hand-built markdown
    string. *target* is a :class:`Folder` (a ``Run`` / ``Experiment`` /
    ``Literature`` / ``Note``) or an
    :class:`~molab.workspace.assets.base.Asset` (resolved to its in-tree record
    dir ``<scope_dir>/assets/<asset_id>/`` and pointed at, never copied).

    With *role* ``None`` the per-kind default is used
    (:func:`~molab.workspace.doc_embed.default_role_for`): a ``Run`` /
    ``Experiment`` -> ``records``, a ``Literature`` -> ``cites``, any
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

    dst = resolve_embed_target(target, root=root)
    append_link(note, dst, role=role if role is not None else default_role_for(target))


def entity_summary(target: Folder | Concept | Asset, *, root: str | Path) -> EntitySummary:
    """Return a read-only :class:`EntitySummary` for *target* (a UI-card projection).

    Args:
        target: The entity to summarize (a ``Folder`` or an ``Asset``).
        root: The workspace root; required only to anchor an ``Asset``.
    """
    from .doc_embed import summarize_entity

    return summarize_entity(target, root=root)
