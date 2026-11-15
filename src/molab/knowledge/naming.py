"""Knowledge file names: ``knowledges/<stem>.md``, ``.html`` or ``.tex``."""

from __future__ import annotations

from typing import Literal

KNOWLEDGE_MD_SUFFIXES: tuple[str, ...] = (".md", ".mdx")
KNOWLEDGE_HTML_SUFFIX = ".html"
KNOWLEDGE_TEX_SUFFIX = ".tex"
KNOWLEDGE_SUFFIXES: tuple[str, ...] = (
    *KNOWLEDGE_MD_SUFFIXES,
    KNOWLEDGE_HTML_SUFFIX,
    KNOWLEDGE_TEX_SUFFIX,
)
KNOWLEDGE_CONTAINER = "knowledges"
#: The directory under ``knowledges/`` that holds the figures documents cite.
KNOWLEDGE_MEDIA_DIR = "figs"

#: How a document is stored: YAML frontmatter + markdown, an HTML document, or
#: a LaTeX document (the record in a leading comment block, :mod:`molab.texdoc`).
KnowledgeFormat = Literal["md", "html", "tex"]
KNOWLEDGE_FORMATS: tuple[KnowledgeFormat, ...] = ("md", "html", "tex")
_FORMAT_SUFFIX: dict[KnowledgeFormat, str] = {
    "md": ".md",
    "html": KNOWLEDGE_HTML_SUFFIX,
    "tex": KNOWLEDGE_TEX_SUFFIX,
}


def is_knowledge_file(path: str) -> bool:
    """Whether *path* is a Knowledge document file (markdown, HTML or TeX)."""
    return path.lower().endswith(KNOWLEDGE_SUFFIXES)


def is_html_document(path: object) -> bool:
    """Whether *path* names an HTML knowledge document."""
    return str(path).lower().endswith(KNOWLEDGE_HTML_SUFFIX)


def is_tex_document(path: object) -> bool:
    """Whether *path* names a TeX knowledge document."""
    return str(path).lower().endswith(KNOWLEDGE_TEX_SUFFIX)


def document_format(path: object) -> KnowledgeFormat:
    """The storage format of the document at *path*."""
    if is_html_document(path):
        return "html"
    return "tex" if is_tex_document(path) else "md"


def knowledge_stem(name: str) -> str:
    """*name* without its knowledge suffix; any other name unchanged."""
    lower = name.lower()
    for suffix in KNOWLEDGE_SUFFIXES:
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return name


def as_knowledge_file(path: str, format: KnowledgeFormat = "md") -> str:
    """Ensure *path* is a knowledge file; a suffix-less path gains *format*'s suffix."""
    if is_knowledge_file(path):
        return path
    return f"{path}{_FORMAT_SUFFIX[format]}"
