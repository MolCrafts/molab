"""Knowledge file names: ``knowledges/<stem>.md``."""

from __future__ import annotations

KNOWLEDGE_MD_SUFFIXES: tuple[str, ...] = (".md", ".mdx")
KNOWLEDGE_CONTAINER = "knowledges"


def is_knowledge_file(path: str) -> bool:
    """Whether *path* is a Knowledge markdown file."""
    lower = path.lower()
    return lower.endswith((".md", ".mdx"))


def as_knowledge_file(path: str) -> str:
    """Ensure *path* is a ``.md`` / ``.mdx`` file (default ``.md``)."""
    if is_knowledge_file(path):
        return path
    return f"{path}.md"
