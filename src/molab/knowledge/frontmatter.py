"""The record and body of a Knowledge document, in either storage format.

A markdown document (``.md`` / ``.mdx``) carries its record as YAML
frontmatter through :mod:`molab.frontmatter`; an HTML document (``.html``)
carries it as JSON in its head through :mod:`molab.htmldoc`. Both functions
here dispatch on the document *path*'s suffix, so every reader and writer that
goes through them handles both formats. With no *path* the text is markdown.

Knowledge adds conventions of its own: empty values are not written, and a
markdown body starts at its first non-blank line (an HTML body is kept
verbatim). A broken head is returned as empty meta so a bad header never 500s
a walk.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from molab.frontmatter import dump, split
from molab.htmldoc import dump as dump_html
from molab.htmldoc import plain_text
from molab.htmldoc import split as split_html

from .naming import is_html_document


def split_frontmatter(text: str, *, path: object = None) -> tuple[dict[str, object], str]:
    """Split *text* into ``(meta, body)``. No head → empty meta + full text."""
    if path is not None and is_html_document(path):
        return split_html(text)
    meta, body = split(text)
    if body is text:
        return meta, body
    return meta, body.lstrip("\n")


def dump_frontmatter(meta: dict[str, object], body: str, *, path: object = None) -> str:
    """Render *meta* + *body* as the document file *path* names."""
    cleaned = {k: v for k, v in meta.items() if v is not None and v != "" and v != []}
    if path is not None and is_html_document(path):
        title = cleaned.get("name") or cleaned.get("title") or PurePosixPath(str(path)).stem
        return dump_html(cleaned, body, title=str(title))
    if body and not body.endswith("\n"):
        body = body + "\n"
    return dump(cleaned, body)


def document_text(body: str, *, path: object = None) -> str:
    """The readable text of a document body: an HTML body without its tags."""
    if path is not None and is_html_document(path):
        return plain_text(body)
    return body


def append_markdown(body: str, lines: str, *, path: object = None) -> str:
    """*body* with markdown *lines* appended; an HTML body gets them as one block."""
    prefix = body if not body or body.endswith("\n") else body + "\n"
    if path is not None and is_html_document(path):
        block = lines if lines.endswith("\n") else lines + "\n"
        return f"{prefix}<molab-markdown>\n{block}</molab-markdown>\n"
    return prefix + lines
