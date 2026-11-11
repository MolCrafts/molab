"""Knowledge file names: ``knowledges/<stem>.md`` or ``knowledges/<stem>.html``."""

from __future__ import annotations

from typing import Literal

KNOWLEDGE_MD_SUFFIXES: tuple[str, ...] = (".md", ".mdx")
KNOWLEDGE_HTML_SUFFIX = ".html"
KNOWLEDGE_SUFFIXES: tuple[str, ...] = (*KNOWLEDGE_MD_SUFFIXES, KNOWLEDGE_HTML_SUFFIX)
KNOWLEDGE_CONTAINER = "knowledges"
#: The directory under ``knowledges/`` that holds the figures documents cite.
KNOWLEDGE_MEDIA_DIR = "figs"

#: How a document is stored: YAML frontmatter + markdown, or an HTML document.
KnowledgeFormat = Literal["md", "html"]
KNOWLEDGE_FORMATS: tuple[KnowledgeFormat, ...] = ("md", "html")


def is_knowledge_file(path: str) -> bool:
    """Whether *path* is a Knowledge document file (markdown or HTML)."""
    return path.lower().endswith(KNOWLEDGE_SUFFIXES)


def is_html_document(path: object) -> bool:
    """Whether *path* names an HTML knowledge document."""
    return str(path).lower().endswith(KNOWLEDGE_HTML_SUFFIX)


def document_format(path: object) -> KnowledgeFormat:
    """The storage format of the document at *path*."""
    return "html" if is_html_document(path) else "md"


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
    return f"{path}{KNOWLEDGE_HTML_SUFFIX if format == 'html' else '.md'}"
