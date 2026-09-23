"""Class-named knowledge heads: ``Note`` → ``note.json``, never ``meta.json``."""

from __future__ import annotations

import re

_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")

KNOWLEDGE_HEAD_FILES: frozenset[str] = frozenset(
    {
        "note.json",
        "literature.json",
        "report.json",
        "finding.json",
        "plan.json",
        "observation.json",
    }
)

KNOWLEDGE_MD_SUFFIXES: tuple[str, ...] = (".md", ".mdx")
KNOWLEDGE_CONTAINER = "knowledges"

#: Slug of the OKF ``Plan`` Concept that carries an experiment's plan book.
#: A layout name belongs to the layer that owns the layout, so it lives here and
#: not in the workspace that mounts it.
PLAN_BOOK_NAME = "plan-book"


def is_knowledge_file(path: str) -> bool:
    """Whether *path* is a Knowledge markdown file."""
    lower = path.lower()
    return lower.endswith((".md", ".mdx"))


def as_knowledge_file(path: str) -> str:
    """Ensure *path* is a ``.md`` / ``.mdx`` file (default ``.md``)."""
    if is_knowledge_file(path):
        return path
    return f"{path}.md"


def knowledge_filename(cls: type) -> str:
    """Singular class-named JSON basename (``Note`` → ``note.json``)."""
    snake = _CAMEL_TO_SNAKE.sub("_", cls.__name__).lower()
    return f"{snake}.json"
