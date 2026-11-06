"""YAML frontmatter for Knowledge markdown files.

A thin knowledge-shaped wrapper over :mod:`molab.frontmatter`, the one parser
and dumper for a fenced markdown head. Knowledge adds two conventions of its
own: empty values are not written, and the body starts at its first
non-blank line. Broken YAML is returned as empty meta so a bad header never
500s a walk.
"""

from __future__ import annotations

from molab.frontmatter import dump, split


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split *text* into ``(meta, body)``. No fence → empty meta + full text."""
    meta, body = split(text)
    if body is text:
        return meta, body
    return meta, body.lstrip("\n")


def dump_frontmatter(meta: dict[str, object], body: str) -> str:
    """Render *meta* + *body* as a markdown file with a YAML fence."""
    cleaned = {k: v for k, v in meta.items() if v is not None and v != "" and v != []}
    if body and not body.endswith("\n"):
        body = body + "\n"
    return dump(cleaned, body)
