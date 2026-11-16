"""The record and body of a Knowledge document, in either storage format.

A markdown document (``.md`` / ``.mdx``) carries its record as YAML
frontmatter through :mod:`molab.frontmatter`; an HTML document (``.html``)
carries it as JSON in its head through :mod:`molab.htmldoc`; a TeX document
(``.tex``) carries it as JSON in a leading comment block through
:mod:`molab.texdoc`. The functions here dispatch on the document *path*'s
suffix, so every reader and writer that goes through them handles every
format. With no *path* the text is markdown.

Knowledge adds conventions of its own: empty values are not written, and a
markdown body starts at its first non-blank line (an HTML or TeX body is
kept verbatim). A broken head is returned as empty meta so a bad header never 500s
a walk.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from molab.frontmatter import dump, split
from molab.htmldoc import dump as dump_html
from molab.htmldoc import plain_text
from molab.htmldoc import split as split_html
from molab.texdoc import dump as dump_tex
from molab.texdoc import split as split_tex

from .naming import is_html_document, is_tex_document


def split_frontmatter(text: str, *, path: object = None) -> tuple[dict[str, object], str]:
    """Split *text* into ``(meta, body)``. No head → empty meta + full text."""
    if path is not None and is_html_document(path):
        return split_html(text)
    if path is not None and is_tex_document(path):
        return split_tex(text)
    meta, body = split(text)
    if body is text:
        return meta, body
    return meta, body.lstrip("\n")


def dump_frontmatter(meta: dict[str, object], body: str, *, path: object = None) -> str:
    """Render *meta* + *body* as the document file *path* names."""
    cleaned = {k: v for k, v in meta.items() if v is not None and v != "" and v != []}
    if path is not None and is_html_document(path):
        from .index_section import document_title

        title = document_title(cleaned, body, PurePosixPath(str(path)).stem)
        return dump_html(cleaned, body, title=title)
    if path is not None and is_tex_document(path):
        return dump_tex(cleaned, body)
    if body and not body.endswith("\n"):
        body = body + "\n"
    return dump(cleaned, body)


def document_text(body: str, *, path: object = None) -> str:
    """The readable text of a document body: an HTML body without its tags."""
    if path is not None and is_html_document(path):
        return plain_text(body)
    return body


def append_markdown(body: str, lines: str, *, path: object = None) -> str:
    """*body* with markdown *lines* appended.

    An HTML body gets them as one ``<molab-markdown>`` block; a TeX body gets
    each as a whole-line ``%`` comment, where the link scanner reads it and
    TeX does not.
    """
    prefix = body if not body or body.endswith("\n") else body + "\n"
    if path is not None and is_tex_document(path):
        return prefix + "".join(f"% {line}\n" for line in lines.rstrip("\n").split("\n"))
    if path is not None and is_html_document(path):
        block = lines if lines.endswith("\n") else lines + "\n"
        return f"{prefix}<molab-markdown>\n{block}</molab-markdown>\n"
    return prefix + lines
