"""What ``molab init`` rewrites in the knowledge an older molab wrote.

Each step makes an old document legal without losing what it says:

* a retired class becomes the class that does its job now
  (:data:`RETIRED_CLASSES`): a ``Delegation`` — the scope, goal, acceptance
  and stop conditions of supervised work — is a ``Plan``;
* a frontmatter key the class does not declare (``gaps`` on a Todo,
  ``holds_under`` on a Finding, a delegation record) moves to the end of the
  narrative as one fenced YAML block, so ``knowledge.fields`` has nothing to
  report and no value is lost;
* a link labelled with a retired role is relabelled (:data:`RETIRED_ROLES`):
  ``records`` and ``supersedes`` fold into ``derived_from``, since the run a
  document records and the document it revises are both what it derives from.
  A link inside code is left alone;
* a link to an attempt's record file (``…/executions/<x>/execution.json``)
  becomes that execution's ``molab:`` ref: an older molab cited an attempt by
  the path of its record, and a Report or Finding rests on the ref.

A declared key whose value the class refuses (a ``verdict`` outside the
vocabulary) is not a shape to migrate: it is left for ``molab validate`` to
report. ``molab init`` runs :func:`migrate_knowledge` once per call; a second
run changes nothing.
"""

from __future__ import annotations

import posixpath
from typing import TYPE_CHECKING

import yaml

from .edges import encode_label

if TYPE_CHECKING:
    from collections.abc import Mapping

    from molab.workspace import Workspace

    from .edges import EdgeRole

__all__ = ["RETIRED_CLASSES", "RETIRED_ROLES", "migrate_knowledge"]

RETIRED_CLASSES: dict[str, str] = {"Delegation": "Plan"}
"""Each retired class name and the class that holds its documents now."""

RETIRED_ROLES: dict[str, EdgeRole] = {"records": "derived_from", "supersedes": "derived_from"}
"""Each retired role token and the role it now is."""


def migrate_knowledge(ws: Workspace) -> list[str]:
    """Rewrite every document of *ws* an older molab left in a retired shape.

    Returns:
        The documents rewritten.
    """
    from .concept import Knowledge, read_text_or_none
    from .concepts import class_of
    from .frontmatter import dump_frontmatter, split_frontmatter
    from .mutation import mutation

    rewritten: list[str] = []
    for path in Knowledge(ws.root, fs=ws.fs)._document_paths():
        text = read_text_or_none(path, fs=ws.fs)
        if text is None:
            continue
        meta, body = split_frontmatter(text, path=path)
        declared = meta.get("class")
        current = RETIRED_CLASSES.get(declared, declared) if isinstance(declared, str) else None
        klass = class_of({"class": current})
        if klass is None:
            continue  # not a document: validate reports knowledge.class
        model = klass.FIELDS
        moved = _undeclared(meta, set(model.model_fields) if model is not None else set())
        head = {key: value for key, value in meta.items() if key not in moved}
        head["class"] = current
        narrative = _attempt_refs(_relabel(_with_moved(body, moved, str(current), path)), path, ws)
        if head == meta and narrative == body:
            continue
        doc = klass(path, fs=ws.fs)
        with mutation(doc, "knowledge.edited", f"migrate {doc.name}"):
            ws.fs.atomic_write_text(path, dump_frontmatter(head, narrative, path=path))
        rewritten.append(path)
    return rewritten


def _undeclared(meta: Mapping[str, object], declared: set[str]) -> dict[str, object]:
    """The keys of *meta* that are neither common nor *declared*, in their order."""
    from .fields import own_fields

    return {key: value for key, value in own_fields(meta).items() if key not in declared}


def _with_moved(body: str, moved: Mapping[str, object], cls: str, path: str) -> str:
    """*body* with *moved* appended as one fenced YAML block, or *body* when none."""
    from .frontmatter import append_markdown

    if not moved:
        return body
    data = yaml.safe_dump(
        dict(moved), sort_keys=False, allow_unicode=True, default_flow_style=False, width=1 << 30
    )
    block = (
        "\n## Moved fields\n\n"
        f"`molab init` moved these frontmatter keys here: a {cls} does not declare them.\n\n"
        f"```yaml\n{data}```\n"
    )
    return append_markdown(body, block, path=path)


def _attempt_refs(body: str, path: str, ws: Workspace) -> str:
    """*body* with each local link to an attempt's record spelled as the execution's ref.

    The record is ``<run>/executions/<x>/execution.json``, it must exist, and
    ``<run>`` must be a run of *ws*. Every other link is kept as written.
    """
    from molab.workspace.execution_repository import EXECUTION_RECORD_FILENAME
    from molab.workspace.naming import EXECUTION_CONTAINER
    from molab.workspace.refs import MolabRef
    from molab.workspace.run import Run

    from .concept import markdown_links
    from .content_rules import _is_local

    pieces: list[str] = []
    cursor = 0
    for link in markdown_links(body):
        target = link.group(2)
        if not _is_local(target):
            continue
        record = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        attempt = posixpath.dirname(record)
        container = posixpath.dirname(attempt)
        if (
            posixpath.basename(record) != EXECUTION_RECORD_FILENAME
            or posixpath.basename(container) != EXECUTION_CONTAINER
            or not ws.fs.is_file(record)
        ):
            continue
        run = ws.folder_at(posixpath.dirname(container))
        if not isinstance(run, Run):
            continue
        ref = MolabRef(
            experiment_id=run.experiment.id,
            run_id=run.id,
            execution_id=posixpath.basename(attempt),
        )
        pieces.append(body[cursor : link.start(2)])
        pieces.append(str(ref))
        cursor = link.end(2)
    pieces.append(body[cursor:])
    return "".join(pieces)


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
