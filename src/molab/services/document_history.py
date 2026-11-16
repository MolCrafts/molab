"""Git versions of one served knowledge file, compared with its working copy.

A read-model over git: it never writes the repository or the file.
"""

from __future__ import annotations

import re
from difflib import unified_diff
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from molab.knowledge.naming import is_knowledge_file
from molab.workspace.fs_local import LocalFS
from molab.workspace.history import FileRevision, GitHistory
from molab.workspace.scope import as_folder

__all__ = ["DocumentHistory", "document_history"]


class DocumentHistory(BaseModel):
    """Git versions of one served knowledge file and an optional working-copy comparison."""

    available: bool
    revisions: list[FileRevision]
    commit: str | None = None
    body: str | None = None
    diff: str | None = None


def document_history(
    workspace: object, document: str, *, commit: str | None = None, limit: int = 50
) -> DocumentHistory:
    """Inspect file history, including manual commits, without changing Git or the file."""
    served = as_folder(workspace)
    path = PurePosixPath(document)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[-2] != "knowledges"
        or not is_knowledge_file(document)
        or (commit is not None and not re.fullmatch(r"[0-9a-f]{40,64}", commit))
        or not 1 <= limit <= 200
    ):
        raise ValueError("expected a served knowledge path, full commit id, and limit 1-200")
    if not isinstance(served.fs, LocalFS):
        return DocumentHistory(available=False, revisions=[])
    boundary = Path(str(served.resolve())).resolve()
    absolute = (boundary / str(path)).resolve()
    if not absolute.is_relative_to(boundary):
        raise ValueError("document must be inside the served scope")
    repo = Path(str(served.asset_host().resolve())).resolve()
    relative = absolute.relative_to(repo).as_posix()
    history = GitHistory(repo)
    revisions = history.file_revisions(relative, limit=limit)
    result = DocumentHistory(available=history.enabled(), revisions=revisions)
    if commit is None:
        return result
    if not any(revision.commit == commit for revision in revisions):
        raise LookupError("Version is not among this document's listed revisions")
    content = history.show(commit, relative)
    if content is None:
        raise LookupError("Document did not exist at that revision")
    current = absolute.read_text(encoding="utf-8") if absolute.is_file() else ""
    result.commit = commit
    result.body = content
    result.diff = "".join(
        unified_diff(
            content.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"{document}@{commit[:8]}",
            tofile=f"{document} (working copy)",
        )
    )
    return result
