"""Document-embed target resolution + entity summaries.

The support for the "Notion-style document" embed verb: a Knowledge document
embeds a live workspace entity — a ``Run`` / ``Experiment`` / ``Literature``
(all :class:`~molab.workspace.folder.Folder` subclasses) or an
:class:`~molab.workspace.assets.base.Asset` — as a typed provenance edge. This
module owns both halves of that verb:

- :func:`resolve_embed_target` — turn a ``Concept`` / ``Folder`` / ``Asset``
  target into the path an edge points at. A ``Concept`` or ``Folder`` is its own
  directory; an ``Asset`` is resolved to its in-tree record directory
  ``<scope_dir>/assets/<asset_id>/`` (pointed at, never copied).
- :func:`default_role_for` — the per-kind default :class:`EdgeRole` (all drawn
  from the frozen vocabulary; no new roles): ``workspace.run`` /
  ``workspace.experiment`` -> ``records``, ``reference.reference`` -> ``cites``,
  everything else (including any ``Asset``) -> ``references``.
- :func:`summarize_entity` / :class:`EntitySummary` — a pure read projection of
  an entity's ``id`` / ``kind`` / ``title`` for a UI card. No new state.
- :func:`embed` — write one typed edge from a document to a live entity.

Missing preconditions (an ``Asset`` with no resolvable record dir, or no
``root`` to anchor one) raise — never a silent fallback.

The workspace layer is imported **inside the function bodies** (and in the
``if TYPE_CHECKING:`` block, which never executes): a module-level back-import
would make ``import molab.knowledge`` a cycle, because ``molab/__init__.py``
eagerly loads ``molab.workspace``.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .bundle_index import extract_title
from .concept import Concept, append_link
from .concepts import REFERENCE_KIND, Literature
from .edges import DEFAULT_EDGE_ROLE, EdgeRole

if TYPE_CHECKING:
    from molab.workspace.assets.base import Asset, AssetScope
    from molab.workspace.folder import Folder

__all__ = [
    "EntitySummary",
    "asset_record_dir",
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
            deliberately not its directory name) or an ``Asset``'s ``asset_id``.
            A ``Concept`` *is* its path, so its directory name is its id.
        kind: The concept/asset kind (e.g. ``"workspace.run"`` / ``"data"``).
        title: A human title — the reference record's title, the ``index.md`` H1
            when present, else the entity's name.
    """

    id: str
    kind: str
    title: str


def _scope_dir(root: Path, scope: AssetScope) -> Path:
    """Anchor an :class:`AssetScope` to its on-disk directory under *root*.

    A scope carries entity **ids**; a path carries human **names**. The two are
    deliberately different, so this walks the tree and matches ids rather than
    string-building a path out of them.

    Args:
        root: The workspace root directory.
        scope: The asset's owning scope.

    Returns:
        The scope's on-disk directory.

    Raises:
        FileNotFoundError: If any id in the scope names no entity.
    """
    from molab.workspace.workspace import Workspace

    if scope.kind == "workspace":
        return Path(root)
    workspace = Workspace(root)
    project = workspace.get_project(scope.ids[0])
    if scope.kind == "project":
        return Path(project.project_dir)
    experiment = project.get_experiment(scope.ids[1])
    if scope.kind == "experiment":
        return Path(experiment.experiment_dir)
    return Path(experiment.get_run(scope.ids[2]).run_dir)


def asset_record_dir(asset: Asset, root: str | PathLike[str] | None) -> Path:
    """Resolve *asset* to its in-tree record dir ``<scope_dir>/assets/<asset_id>/``.

    This is the same location :func:`molab.workspace.assets.scan` reads a user
    ``DataAsset`` from; the asset payload is only *pointed at* by an embed edge,
    never copied. The directory is anchored from the workspace *root* via the
    frozen Layout naming law (:func:`_scope_dir`).

    Args:
        asset: The asset whose record dir to locate.
        root: The workspace root to anchor the asset's scope against.

    Returns:
        The absolute record directory (guaranteed to exist).

    Raises:
        ValueError: If *root* is ``None`` (an ``Asset`` cannot be anchored).
        FileNotFoundError: If no record dir exists for the asset — e.g. an asset
            known only from a manifest, with no ``assets/<id>/`` directory.
    """
    if root is None:
        raise ValueError(
            f"asset_record_dir requires a workspace root to anchor asset {asset.asset_id!r}"
        )
    record_dir = _scope_dir(Path(root), asset.scope) / "assets" / asset.asset_id
    if not record_dir.is_dir():
        raise FileNotFoundError(f"no record directory for asset {asset.asset_id!r} at {record_dir}")
    return record_dir


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
    from molab.workspace.assets.base import Asset
    from molab.workspace.folder import Folder

    if isinstance(target, Asset):
        return DEFAULT_EDGE_ROLE
    if isinstance(target, Concept):
        return _DEFAULT_ROLE_BY_KIND.get(target.type(), DEFAULT_EDGE_ROLE)
    if isinstance(target, Folder):
        return _DEFAULT_ROLE_BY_KIND.get(target.kind, DEFAULT_EDGE_ROLE)
    raise TypeError(f"embed target must be a Concept, Folder or Asset, got {type(target).__name__}")


def resolve_embed_target(
    target: Concept | Folder | Asset,
    *,
    root: str | PathLike[str] | None,
) -> Path:
    """Resolve *target* to the directory an embed edge points at.

    A ``Concept`` or ``Folder`` target is its own directory. An ``Asset`` is
    resolved to its in-tree record dir (:func:`asset_record_dir`), so the asset
    payload is only ever *pointed at*, never copied or linked into the note.

    It answers a path rather than a live object on purpose: an edge target is a
    path (:func:`~molab.knowledge.concept.append_link` takes a Concept or a bare
    path), so nothing here has to reconstruct the target's class — which is what
    let this seam work across two storage families at once.

    Args:
        target: The embed target (a ``Concept``, ``Folder`` or ``Asset``).
        root: The workspace root, needed only to anchor an ``Asset``.

    Returns:
        The absolute directory the edge points at.

    Raises:
        TypeError: If *target* is none of the three.
        ValueError: If an ``Asset`` target has no *root* to anchor it.
        FileNotFoundError: If an ``Asset`` target has no on-disk record dir.
    """
    from molab.workspace.assets.base import Asset
    from molab.workspace.folder import Folder

    if isinstance(target, Asset):
        return asset_record_dir(target, root)
    if isinstance(target, Concept):
        return Path(str(target.path))
    if isinstance(target, Folder):
        return Path(str(target.resolve()))
    raise TypeError(f"embed target must be a Concept, Folder or Asset, got {type(target).__name__}")


def summarize_entity(
    target: Concept | Folder | Asset, *, root: str | PathLike[str] | None = None
) -> EntitySummary:
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
    - An ``Asset``: ``id`` is the ``asset_id``, ``kind`` is the asset kind, and
      ``title`` is the asset name. *root* is required to anchor the asset (its
      record dir must be locatable), matching the embed verb's precondition.

    Args:
        target: The entity to summarize (a ``Concept``, ``Folder`` or ``Asset``).
        root: The workspace root; required only when *target* is an ``Asset``.

    Returns:
        The read-only :class:`EntitySummary`.

    Raises:
        TypeError: If *target* is none of the three.
        ValueError: If an ``Asset`` target has no *root* to anchor it.
        FileNotFoundError: If an ``Asset`` target has no on-disk record dir.
    """
    from molab.workspace.assets.base import Asset
    from molab.workspace.folder import Folder

    if isinstance(target, Asset):
        # Anchor + validate the asset is locatable in the tree (raises on a
        # missing root or record dir -- no silent fallback).
        asset_record_dir(target, root)
        # ``kind`` is declared only on concrete Asset subclasses (DataAsset,
        # ...), not the abstract base -- read it the way ``assets.scan`` does.
        kind = str(getattr(target, "kind", ""))
        return EntitySummary(id=target.asset_id, kind=kind, title=target.name)
    if isinstance(target, (Concept, Folder)):
        meta = target.read_meta()
        raw_type = meta.get("type")
        default_kind = target.type() if isinstance(target, Concept) else target.kind
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
    root: str | PathLike[str] | None,
    role: EdgeRole | None = None,
) -> None:
    """Embed a live workspace entity into document *note* as one typed edge.

    Any Concept can carry an edge (a ``Note`` narrating a run, a ``Literature``
    citing its source), so *note* is typed at the family, not at ``Note``.

    Writes a single typed markdown link through the sole edge-writer
    :func:`~molab.knowledge.concept.append_link` — never a hand-built markdown
    string. *target* is a ``Concept`` / ``Folder`` (a ``Run`` / ``Experiment`` /
    ``Literature`` / ``Note``) or an :class:`Asset` (resolved to its in-tree
    record dir and pointed at, never copied). With *role* ``None`` the per-kind
    default is used (:func:`default_role_for`).

    Args:
        note: The document the edge originates from.
        target: The live entity to embed.
        root: The workspace root, needed only to anchor an ``Asset``.
        role: An explicit edge role; defaults to the per-kind default.

    Raises:
        TypeError: If *target* is none of the three.
        ValueError: If an ``Asset`` target has no *root* to anchor it.
        FileNotFoundError: If an ``Asset`` target has no on-disk record dir.
    """
    dst = resolve_embed_target(target, root=root)
    append_link(note, dst, role=role if role is not None else default_role_for(target))
