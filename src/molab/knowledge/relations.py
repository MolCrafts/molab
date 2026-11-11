"""Edit narrative graph links at the canonical markdown parser's source ranges.

There is no relation store: an occurrence identifies one link in the current
document, and every mutation requires the digest of that document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .concept import Concept, append_link, markdown_links
from .edges import EdgeRole, encode_label, link_line, parse_role, validate_role
from .frontmatter import append_markdown
from .record import RecordConflictError, digest_of


@dataclass(frozen=True)
class RelationLink:
    """One editable link; offsets address the current narrative, never a cache."""

    id: int
    target: str
    role: EdgeRole
    label: str
    start: int
    end: int
    label_start: int
    label_end: int


def relation_links(doc: Concept, body: str | None = None) -> list[RelationLink]:
    """Read typed links using the same parser and resolution as the graph.

    Code examples, anchors and non-link schemes are not relationships. Images
    remain media: changing their alt text is not a graph authoring operation.
    """
    narrative = doc.read() if body is None else body
    found = []
    for match in markdown_links(narrative):
        if match.start() > 0 and narrative[match.start() - 1] == "!":
            continue
        scan = doc.scan_links(match.group(0))
        if scan.typed_concepts:
            target, role = scan.typed_concepts[0]
        elif scan.external:
            target, role = scan.external[0], "references"
        else:
            continue
        _, label = parse_role(match.group(1))
        found.append(
            RelationLink(
                len(found),
                target,
                role,
                label,
                match.start(),
                match.end(),
                match.start(1),
                match.end(1),
            )
        )
    return found


def mutate_relation(
    doc: Concept,
    *,
    action: Literal["add", "replace", "remove"],
    if_match: str,
    occurrence: int | None = None,
    target: str | None = None,
    role: EdgeRole = "references",
    text: str | None = None,
) -> str:
    """Write one relation and return the new digest; callers serialize writes.

    Removing an inline link keeps its human label as prose. A standalone list
    item disappears whole. Role edits replace only the label's role channel,
    preserving its text, original target spelling and surrounding narrative.
    """
    if digest_of(doc) != if_match:
        raise RecordConflictError(f"{doc.path} changed since it was read")
    validate_role(role)
    if action == "add":
        if not target:
            raise ValueError("add requires a target")
        if text is not None and any(char in text for char in "[]\r\n"):
            raise ValueError("relation labels cannot contain brackets or newlines")
        if text is not None and role == "references" and parse_role(text)[0] != role:
            raise ValueError("a reference label cannot begin with a typed relation sigil")
        if any(char in target for char in "()\r\n"):
            raise ValueError("relation targets cannot contain parentheses or newlines")
        if target.startswith(("http://", "https://")):
            _validate_web_role(role)
            line = link_line(encode_label(role, text or target), target) + "\n"
            doc.write(append_markdown(doc.read(), line, path=doc.path))
        else:
            append_link(doc, target, text=text, role=role)
    else:
        body = doc.read()
        links = relation_links(doc, body)
        if occurrence is None or occurrence < 0 or occurrence >= len(links):
            raise ValueError("relation occurrence no longer exists")
        link = links[occurrence]
        if action == "replace":
            if link.target.startswith(("http://", "https://")):
                _validate_web_role(role)
            body = (
                body[: link.label_start] + encode_label(role, link.label) + body[link.label_end :]
            )
        elif action == "remove":
            start = body.rfind("\n", 0, link.start) + 1
            end = body.find("\n", link.end)
            end = len(body) if end < 0 else end
            prefix, suffix = body[start : link.start], body[link.end : end]
            if re.fullmatch(r"[ \t]*(?:[-+*]|\d+[.)])[ \t]+", prefix) and not suffix.strip():
                body = body[:start] + body[min(end + 1, len(body)) :]
            else:
                body = body[: link.start] + link.label + body[link.end :]
        else:
            raise ValueError(f"unknown relation action {action!r}")
        doc.write(body)
    return digest_of(doc)


def _validate_web_role(role: EdgeRole) -> None:
    if role not in {"references", "cites", "derived_from"}:
        raise ValueError("web links support references, cites or derived_from")
