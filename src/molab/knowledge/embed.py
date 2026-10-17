"""Document-embed target resolution + entity summaries.

The support for the "Notion-style document" embed verb: a Knowledge document
embeds a live workspace entity — a ``Run`` / ``Experiment`` / ``Literature``
(all :class:`~molab.workspace.folder.Folder` subclasses) or an
:class:`~molab.workspace.domain.Asset` — as a typed provenance edge. This
module owns both halves of that verb:

- :func:`resolve_embed_target` — turn a ``Concept`` / ``Folder`` / ``Asset``
  target into the edge target. A project, experiment, run, or asset is its
  reference. A document is its path. Any other folder is its directory.
- :func:`default_role_for` — the per-kind default :class:`EdgeRole` (all drawn
  from the frozen vocabulary; no new roles): ``workspace.run`` /
  ``workspace.experiment`` -> ``records``, ``reference.reference`` -> ``cites``,
  everything else (including any ``Asset``) -> ``references``.
- :func:`summarize_entity` / :class:`EntitySummary` — a pure read projection of
  an entity's ``id`` / ``kind`` / ``title`` for a UI card. No new state.
- :func:`embed` — write one typed edge from a document to a live entity.

A target that is none of those kinds raises ``TypeError``.

The workspace layer is imported **inside the function bodies** (and in the
``if TYPE_CHECKING:`` block, which never executes): a module-level back-import
would make ``import molab.knowledge`` a cycle, because ``molab/__init__.py``
eagerly loads ``molab.workspace``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from .concept import Concept, append_link
from .concepts import REFERENCE_KIND, Literature
from .edges import DEFAULT_EDGE_ROLE, EdgeRole
from .search import extract_title

if TYPE_CHECKING:
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

__all__ = [
    "EntitySummary",
    "default_role_for",
    "embed",
    "resolve_embed_target",
    "summarize_entity",
]

# Per-kind default edge roles, all members of the frozen ``EdgeRole`` vocabulary
# (edges.py). A kind absent here defaults to ``DEFAULT_EDGE_ROLE`` ("references").
_DEFAULT_ROLE_BY_KIND: dict[str, EdgeRole] = {
    "workspace.run": "records",
    "workspace.experiment": "records",
    REFERENCE_KIND: "cites",
}


class EntitySummary(BaseModel, frozen=True):
    """A read-only projection of a workspace entity for a UI card.

    Attributes:
        id: The entity's stable id — a ``Folder``'s own id (a run/experiment id,
            deliberately not its directory name) or an ``Asset``'s ``id``.
            A ``Concept`` *is* its path, so its directory name is its id.
        kind: The concept/asset kind (e.g. ``"workspace.run"`` / ``"asset"``).
        title: A human title — the reference record's title, the ``index.md`` H1
            when present, else the entity's name.
    """

    id: str
    kind: str
    title: str


def default_role_for(target: Concept | Folder | Asset) -> EdgeRole:
    """Return the per-kind default embed :class:`EdgeRole` for *target*.

    All roles come from the frozen vocabulary (no new roles): a ``Run`` or
    ``Experiment`` folder -> ``records``, a ``Literature`` -> ``cites``,
    and any ``Asset`` (or other folder kind) -> ``references``
    (:data:`~molab.knowledge.edges.DEFAULT_EDGE_ROLE`).

    Args:
        target: The embed target (a ``Concept``, ``Folder`` or ``Asset``).

    Returns:
        The default role for *target*'s kind.

    Raises:
        TypeError: If *target* is none of the three.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

    if isinstance(target, Asset):
        return DEFAULT_EDGE_ROLE
    if isinstance(target, Concept):
        return _DEFAULT_ROLE_BY_KIND.get(target.type(), DEFAULT_EDGE_ROLE)
    if isinstance(target, Folder):
        return _DEFAULT_ROLE_BY_KIND.get(target.kind, DEFAULT_EDGE_ROLE)
    raise TypeError(f"embed target must be a Concept, Folder or Asset, got {type(target).__name__}")


def resolve_embed_target(target: Concept | Folder | Asset) -> str:
    """The edge target for *target*.

    A project, experiment, run, or asset is its ``molab:`` reference. A
    knowledge document is its path. Any other folder is its absolute directory.

    Raises:
        TypeError: If *target* is none of those.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.experiment import Experiment
    from molab.workspace.folder import Folder
    from molab.workspace.project import Project
    from molab.workspace.refs import ref_of
    from molab.workspace.run import Run

    if isinstance(target, (Project, Experiment, Run, Asset)):
        return str(ref_of(target))
    if isinstance(target, Concept):
        return str(target.path)
    if isinstance(target, Folder):
        return str(target.resolve())
    raise TypeError(f"embed target must be a Concept, Folder or Asset, got {type(target).__name__}")


def summarize_entity(target: Concept | Folder | Asset) -> EntitySummary:
    """Project *target* to an :class:`EntitySummary` (a pure read; writes nothing).

    - A ``Folder`` (``Run`` / ``Experiment`` / ``Literature``): ``id`` is the
      entity's own id (never its directory name — the two are deliberately
      different), ``kind`` is its head ``type`` (falling back to the folder's
      kind), and ``title`` walks three branches: the reference-kind head title,
      a ``Literature``'s ``ReferenceMeta.title``, else the ``index.md`` H1 (else
      the directory name).
    - A ``Concept``: the same projection, with two differences — a ``Concept``
      *is* its path, so ``id`` is the directory name; and its narrative is read
      at that path.
    - An ``Asset``: ``id`` is the asset id, ``kind`` is ``asset.kind``, and
      ``title`` is the asset title.

    Args:
        target: The entity to summarize (a ``Concept``, ``Folder`` or ``Asset``).

    Returns:
        The read-only :class:`EntitySummary`.

    Raises:
        TypeError: If *target* is none of the three.
    """
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

    if isinstance(target, Asset):
        return EntitySummary(id=target.id, kind=target.kind, title=target.title)
    if isinstance(target, Concept):
        meta = target.frontmatter()
        raw_type = target.type()
        default_kind = raw_type
    elif isinstance(target, Folder):
        meta = target.read_meta()
        raw_type = meta.get("type")
        default_kind = target.kind
    else:
        meta = {}
        raw_type = None
        default_kind = ""
    if isinstance(target, (Concept, Folder)):
        kind = str(raw_type) if raw_type is not None else default_kind
        title: str | None = None
        if kind in {REFERENCE_KIND, "literature", "reference"}:
            ref_title = meta.get("title")
            if isinstance(ref_title, str) and ref_title:
                title = ref_title
            else:
                if isinstance(target, Literature):
                    bib_title = target.record.title
                    if isinstance(bib_title, str) and bib_title:
                        title = bib_title
        if title is None:
            narrative = target.read() if isinstance(target, Concept) else target.read_index()
            title = extract_title(narrative) or target.name
        # A Concept *is* its path, so its directory name is its id; a Folder
        # carries an id in its entity record that is deliberately not the
        # directory name (a run dir is ``seed=1``, not the run id).
        entity_id = target.name if isinstance(target, Concept) else target.metadata.id
        return EntitySummary(id=entity_id, kind=kind, title=title)
    raise TypeError(
        f"summary target must be a Concept, Folder or Asset, got {type(target).__name__}"
    )


def embed(
    note: Concept,
    target: Concept | Folder | Asset,
    *,
    role: EdgeRole | None = None,
) -> None:
    """Embed a live workspace entity into document *note* as one typed edge.

    Any Concept can carry an edge (a ``Note`` narrating a run, a ``Literature``
    citing its source), so *note* is typed at the family, not at ``Note``.

    Writes a single typed markdown link through the sole edge-writer
    :func:`~molab.knowledge.concept.append_link` — never a hand-built markdown
    string. *target* is a ``Concept``, a workspace ``Folder`` (a ``Run`` or
    ``Experiment``), or an :class:`Asset`. A folder or asset is linked by the
    reference :func:`resolve_embed_target` returns. With *role* ``None`` the
    per-kind default is used (:func:`default_role_for`).

    Args:
        note: The document the edge originates from.
        target: The live entity to embed.
        role: An explicit edge role; defaults to the per-kind default.

    Raises:
        TypeError: If *target* is none of the three.
    """
    dst = resolve_embed_target(target)
    append_link(note, dst, role=role if role is not None else default_role_for(target))
