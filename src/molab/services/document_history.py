"""Versions of one served knowledge file, read from git.

A version is a commit that changed the file's content, numbered ``v1`` (the
oldest) to ``vN`` (the newest). Renames and moves are followed, so a moved
document keeps its versions, and each version is read at the path the file
had in that commit. A working file that differs from its newest version is an
uncommitted working copy, not a numbered version.

A read-model over git: it never writes the repository or the file. History is
a soft dependency — no git, a non-local filesystem, or a git error leaves the
versions unavailable and never fails the live document read.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from molab.knowledge.naming import is_knowledge_file
from molab.workspace.fs_local import LocalFS
from molab.workspace.history import FileRevision, GitHistory
from molab.workspace.scope import as_folder

__all__ = [
    "DocumentHistory",
    "DocumentVersion",
    "DocumentVersionRead",
    "document_history",
    "document_version",
]


class DocumentVersion(FileRevision):
    """One numbered version of a knowledge file: ``v1`` is its first commit."""

    number: int


class DocumentHistory(BaseModel):
    """A knowledge file's versions, newest first, and an optional comparison with its working copy."""

    available: bool
    versions: list[DocumentVersion]
    uncommitted: bool = False
    """Whether the working file differs from its newest version (or has none yet)."""
    version: int | None = None
    """The version :attr:`diff` compares with the working copy."""
    diff: str | None = None


class DocumentVersionRead(BaseModel):
    """One version's file text, and the absolute path the file had in that commit."""

    version: DocumentVersion
    file: str
    text: str


@dataclass(frozen=True)
class _Located:
    history: GitHistory
    absolute: Path
    versions: list[DocumentVersion]


def _locate(workspace: object, document: str) -> _Located | None:
    """Validate *document* and list its versions; ``None`` when history is unavailable.

    Raises:
        ValueError: *document* is not a knowledge file inside the served scope.
    """
    served = as_folder(workspace)
    path = PurePosixPath(document)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[-2] != "knowledges"
        or not is_knowledge_file(document)
    ):
        raise ValueError("expected a knowledge document path inside the served scope")
    if not isinstance(served.fs, LocalFS):
        return None
    boundary = Path(str(served.resolve())).resolve()
    absolute = (boundary / str(path)).resolve()
    if not absolute.is_relative_to(boundary):
        raise ValueError("document must be inside the served scope")
    repo = Path(str(served.asset_host().resolve())).resolve()
    history = GitHistory(repo)
    if not history.enabled():
        return None
    revisions = history.file_revisions(absolute.relative_to(repo).as_posix())
    total = len(revisions)
    versions = [
        DocumentVersion(**revision.model_dump(), number=total - index)
        for index, revision in enumerate(revisions)
    ]
    return _Located(history=history, absolute=absolute, versions=versions)


def _text_of(located: _Located, version: DocumentVersion) -> str:
    text = located.history.show(version.commit, version.path)
    if text is None:
        raise LookupError(f"v{version.number} could not be read from git")
    return text


_UNAVAILABLE = "document versions are unavailable in this workspace"


def _version(located: _Located, number: int) -> DocumentVersion:
    found = next((item for item in located.versions if item.number == number), None)
    if found is None:
        raise LookupError(f"this document has no v{number}")
    return found


def document_history(
    workspace: object, document: str, *, version: int | None = None
) -> DocumentHistory:
    """List a knowledge file's versions; with *version*, diff it against the working copy.

    Raises:
        ValueError: *document* is not a served knowledge path, or *version* < 1.
        LookupError: *version* is given and versions are unavailable, or the
            document has no such version.
    """
    if version is not None and version < 1:
        raise ValueError("version numbers start at 1")
    located = _locate(workspace, document)
    if located is None:
        if version is not None:
            raise LookupError(_UNAVAILABLE)
        return DocumentHistory(available=False, versions=[])
    exists = located.absolute.is_file()
    current = located.absolute.read_text(encoding="utf-8") if exists else ""
    newest = located.versions[0] if located.versions else None
    committed = None if newest is None else located.history.show(newest.commit, newest.path)
    # A git error while reading the newest version is not a reported difference.
    uncommitted = exists and (newest is None or (committed is not None and committed != current))
    if version is None:
        return DocumentHistory(available=True, versions=located.versions, uncommitted=uncommitted)
    diff = unified_diff(
        _text_of(located, _version(located, version)).splitlines(keepends=True),
        current.splitlines(keepends=True),
        fromfile=f"{document}@v{version}",
        tofile=f"{document} (working copy)",
    )
    return DocumentHistory(
        available=True,
        versions=located.versions,
        uncommitted=uncommitted,
        version=version,
        diff="".join(diff),
    )


def document_version(workspace: object, document: str, number: int) -> DocumentVersionRead:
    """Read version *number* of a knowledge file, at the path it had in that commit.

    Raises:
        ValueError: *document* is not a served knowledge path, or *number* < 1.
        LookupError: versions are unavailable, or the document has no such version.
    """
    if number < 1:
        raise ValueError("version numbers start at 1")
    located = _locate(workspace, document)
    if located is None:
        raise LookupError(_UNAVAILABLE)
    chosen = _version(located, number)
    return DocumentVersionRead(
        version=chosen,
        file=str(located.history.root / chosen.path),
        text=_text_of(located, chosen),
    )
