"""Rewrite the edge roles the vocabulary retired.

``records`` and ``supersedes`` are folded into ``derived_from``: the run a
document records and the document it revises are both what it derives from.
``molab init`` runs :func:`migrate_retired_roles` over a workspace once; a
label the vocabulary no longer knows would otherwise read as ``references``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .edges import encode_label

if TYPE_CHECKING:
    from molab.fs import FileSystem, PathArg

    from .edges import EdgeRole

__all__ = ["RETIRED_ROLES", "migrate_retired_roles"]

RETIRED_ROLES: dict[str, EdgeRole] = {"records": "derived_from", "supersedes": "derived_from"}
"""Each retired role token and the role it now is."""


def migrate_retired_roles(root: PathArg, *, fs: FileSystem) -> list[str]:
    """Relabel every retired-role link of the documents under *root*.

    Only the label changes; the target and the rest of the document are kept,
    and a link inside code is left alone.

    Returns:
        The documents rewritten.
    """
    from .concept import Knowledge

    rewritten: list[str] = []
    for doc in Knowledge(root, fs=fs).walk():
        body = doc.read()
        relabelled = _relabel(body)
        if relabelled != body:
            doc._store_relinked(relabelled)
            rewritten.append(str(doc.path))
    return rewritten


def _relabel(body: str) -> str:
    """*body* with each retired-role link label spelled in its current role."""
    from .concept import markdown_links

    pieces: list[str] = []
    cursor = 0
    for link in markdown_links(body):
        label = link.group(1)
        if not label.startswith("@"):
            continue
        token, _sep, rest = label[1:].partition(" ")
        role = RETIRED_ROLES.get(token)
        if role is None:
            continue
        pieces.append(body[cursor : link.start(1)])
        pieces.append(encode_label(role, rest))
        cursor = link.end(1)
    pieces.append(body[cursor:])
    return "".join(pieces)
