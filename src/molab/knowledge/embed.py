"""Embed defaults + entity summaries.

The support for the "Notion-style document" embed verb: a Knowledge document
embeds a live workspace entity — a ``Run`` / ``Experiment`` / ``Literature``
or an :class:`~molab.workspace.domain.Asset` — as a typed provenance edge
written by :func:`~molab.knowledge.concept.append_link`. This module holds
what that edge writer does not:

- :func:`default_role_for` — the per-kind default :class:`EdgeRole`: a run or
  experiment -> ``derived_from``, a :class:`Literature` -> ``cites``,
  everything else (including any ``Asset``) -> ``references``.
- :func:`summarize_entity` / :class:`EntitySummary` — a pure read projection of
  an entity's ``id`` / ``kind`` / ``title`` for a UI card. No new state. A
  document's kind is its class name.

A target that is none of those kinds raises ``TypeError``.

The workspace layer is imported **inside the function bodies** (and in the
``if TYPE_CHECKING:`` block, which never executes): a module-level back-import
would make ``import molab.knowledge`` a cycle, because ``molab/__init__.py``
eagerly loads ``molab.workspace``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from .concept import Concept
from .concepts import Literature
from .edges import DEFAULT_EDGE_ROLE, EdgeRole
from .search import extract_title

if TYPE_CHECKING:
    from molab.workspace.domain import Asset
    from molab.workspace.folder import Folder

__all__ = [
    "EntitySummary",
    "default_role_for",
    "summarize_entity",
]


class EntitySummary(BaseModel, frozen=True):
    """A read-only projection of a workspace entity for a UI card.

    Attributes:
        id: The entity's stable id — a ``Folder``'s own id (a run/experiment id,
            deliberately not its directory name) or an ``Asset``'s ``id``.
            A ``Concept`` *is* its path, so its directory name is its id.
        kind: A document's class name, a folder's record ``type`` (e.g.
            ``"workspace.run"``), or ``"asset"``.
        title: A human title — the reference record's title, the ``index.md`` H1
            when present, else the entity's name.
    """

    id: str
    kind: str
    title: str


def default_role_for(target: Concept | Folder | Asset) -> EdgeRole:
    """Return the per-kind default embed :class:`EdgeRole` for *target*.

    A ``Run`` or ``Experiment`` folder -> ``derived_from``, a ``Literature`` -> ``cites``,
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
    from molab.workspace.experiment import Experiment
    from molab.workspace.folder import Folder
    from molab.workspace.run import Run

    if isinstance(target, Literature):
        return "cites"
    if isinstance(target, (Run, Experiment)):
        return "derived_from"
    if isinstance(target, (Asset, Concept, Folder)):
        return DEFAULT_EDGE_ROLE
    raise TypeError(f"embed target must be a Concept, Folder or Asset, got {type(target).__name__}")


def summarize_entity(target: Concept | Folder | Asset) -> EntitySummary:
    """Project *target* to an :class:`EntitySummary` (a pure read; writes nothing).

    - A ``Folder`` (``Run`` / ``Experiment``): ``id`` is the entity's own id
      (never its directory name — the two are deliberately different),
      ``kind`` is its head ``type`` (falling back to the folder's kind), and
      ``title`` is the ``index.md`` H1, else the directory name.
    - A ``Concept``: ``id`` is the document path, because that path is the
      document; ``kind`` is its class name; ``title`` is :meth:`Concept.title`.
    - An ``Asset``: ``id`` is the asset id, ``kind`` is ``"asset"``, and
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
        return EntitySummary(id=target.id, kind="asset", title=target.title)
    if isinstance(target, Concept):
        # A document's identity is its path.
        return EntitySummary(id=str(target.path), kind=type(target).__name__, title=target.title())
    if isinstance(target, Folder):
        raw_type = target.read_meta().get("type")
        kind = str(raw_type) if raw_type is not None else target.kind
        title = extract_title(target.read_index()) or target.name
        # A Folder's id lives in its record and is deliberately not the
        # directory name (a run dir is ``seed=1``, not the run id).
        return EntitySummary(id=target.metadata.id, kind=kind, title=title)
    raise TypeError(
        f"summary target must be a Concept, Folder or Asset, got {type(target).__name__}"
    )
