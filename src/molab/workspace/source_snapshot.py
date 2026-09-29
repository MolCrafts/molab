"""Source capture — the exact workflow source an Execution was created from.

A path and an AST hash of the entrypoint cannot give the code back: if the file
is later edited or deleted, the code that produced an attempt is unrecoverable. This module captures the entrypoint **plus its first-party
local-module import closure** (sibling ``.py`` modules in the entrypoint's
directory, transitively), per attempt, in two steps:

1. :func:`source_manifest` reads the originals and returns a
   :class:`~molab.workspace.domain.SourceManifest` (locator, per-file sha256,
   VCS commit and dirty flag). It writes nothing, so a missing entrypoint fails
   before any record exists.
2. :func:`copy_sources` copies the originals into ``<execution_dir>/source/``
   and verifies every copy against the manifest, raising
   :class:`SourceCaptureError` on any mismatch.

``Run.create_execution(source_entrypoint=...)`` runs them in that order around
creating the record, so each attempt's manifest is on its Execution record and
its copies are under ``executions/eNN/source/``.

The workspace layer must not import upstream molab layers (see the layer DAG in
CLAUDE.md / ``test_import_guard``); this module uses only the stdlib and
workspace-local types.

Scope (v1): first-party modules are flat siblings resolved as ``<root>/<name>.py``
where ``root`` is the entrypoint's directory. Package subdirectories and
namespace packages are out of scope; stdlib and third-party imports are ignored
(they have no sibling file). This matches the flat-module layout of the molab
consumer scripts (e.g. ``phase1.py`` importing ``eval_df`` / ``experiment``).
"""

from __future__ import annotations

import ast
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from molab.ids import compute_content_hash, hash_bytes

from .domain import SourceFile, SourceManifest
from .file_store import FileStore
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem

__all__ = ["SourceCaptureError", "copy_sources", "source_manifest"]


class SourceCaptureError(RuntimeError):
    """The captured source copy does not match its manifest.

    Raised when an original is missing or unreadable, a copy cannot be
    written, or a copy's digest differs from the one the manifest recorded
    (for example, the original was edited after the manifest was built).
    """


def _local_import_closure(entrypoint: Path) -> list[Path]:
    """Entrypoint + transitively-imported first-party sibling ``.py`` modules.

    A module name ``m`` is first-party iff ``<root>/m.py`` exists (``root`` =
    the entrypoint's directory). Dotted imports contribute their first segment.
    Stdlib / third-party imports resolve to no sibling file and are skipped.
    Returns the entrypoint first, then the rest sorted by filename (deterministic).
    """
    entrypoint = entrypoint.resolve()
    root = entrypoint.parent
    seen: dict[Path, None] = {}
    stack = [entrypoint]
    while stack:
        current = stack.pop().resolve()
        if current in seen or not current.is_file():
            continue
        seen[current] = None
        try:
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        for name in names:
            candidate = (root / f"{name}.py").resolve()
            if candidate.is_file() and candidate not in seen:
                stack.append(candidate)
    rest = sorted((p for p in seen if p != entrypoint), key=lambda p: p.name)
    return [entrypoint, *rest]


def _sha256(path: Path) -> str:
    # Streams (and memoizes) rather than holding the whole file in memory —
    # a snapshotted source tree can contain generated data files, not just
    # the few-KB scripts this was written for.
    return compute_content_hash(path)


_REDIRECTING_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def _git_stdout(directory: Path, *args: str) -> str | None:
    """Stdout of one read-only ``git`` query in *directory*, or ``None``.

    ``None`` covers every way the answer is unknown: git is not installed
    (``OSError``), the query hangs (``TimeoutExpired``), or git refuses
    (non-zero exit, e.g. *directory* is outside any repository).
    ``--no-optional-locks`` keeps ``status`` from refreshing the index, so
    reading the user's repository never writes to it. An inherited
    ``GIT_DIR`` / ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE`` (e.g. molab launched
    from a git hook) is dropped so ``-C`` decides the repository; an fsmonitor
    daemon is never started; stdin is closed so git cannot prompt.
    """
    env = dict(os.environ)
    for name in _REDIRECTING_GIT_ENV:
        env.pop(name, None)
    try:
        done = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(directory),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def _vcs_state(directory: Path) -> tuple[str | None, bool | None]:
    """The git commit and dirty flag of the repository holding *directory*.

    Modelled on ``GitHistory._git`` but not reusing it: that method is bound
    to the workspace root and injects molab's commit identity, while this
    queries whatever repository the user's source lives in.

    Returns:
        ``(commit, dirty)``. Each is ``None`` when unknown (no git, outside a
        repository, timeout). Dirty is repository-wide and counts untracked
        files: if the entrypoint itself is untracked, the commit does not
        contain it, so the tree is dirty. A script inside the workspace
        records the workspace history's HEAD, which is the truth.
    """
    head = _git_stdout(directory, "rev-parse", "HEAD")
    commit = (head.strip() or None) if head is not None else None
    status = _git_stdout(directory, "status", "--porcelain")
    dirty = bool(status.strip()) if status is not None else None
    return commit, dirty


def source_manifest(entrypoint: PathArg, *, now: datetime | None = None) -> SourceManifest:
    """Describe the source an attempt would capture, without copying anything.

    A pure read: it hashes the **originals** (the entrypoint and its
    first-party import closure) and queries their VCS state, and writes no
    file. Call it before creating the Execution record, so a missing
    entrypoint fails while no record exists yet.

    Args:
        entrypoint: The defining script (the file molab re-imports to execute).
        now: Capture timestamp (injectable for deterministic tests); defaults
            to the current UTC time.

    Returns:
        The manifest: ``entrypoint`` is the basename, ``locator`` the resolved
        absolute path (never hashed; used only to locate the originals at
        capture time),
        ``files`` the closure with the entrypoint first and the rest sorted by
        name, plus ``vcs_commit`` / ``vcs_dirty`` and ``captured_at``.

    Raises:
        FileNotFoundError: *entrypoint* is not a file.
        SourceCaptureError: A file in the closure (the entrypoint included)
            exists but cannot be read.
    """
    path = Path(entrypoint).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"source entrypoint {str(entrypoint)!r} is not a file")
    files: list[SourceFile] = []
    for src in _local_import_closure(path):
        try:
            files.append(SourceFile(name=src.name, sha256=_sha256(src)))
        except OSError as exc:
            raise SourceCaptureError(f"cannot read source {src.name!r}: {exc}") from exc
    commit, dirty = _vcs_state(path.parent)
    return SourceManifest(
        entrypoint=path.name,
        locator=str(path),
        files=tuple(files),
        vcs_commit=commit,
        vcs_dirty=dirty,
        captured_at=now or datetime.now(UTC),
    )


def copy_sources(
    manifest: SourceManifest, execution_dir: PathArg, *, fs: FileSystem | None = None
) -> None:
    """Copy the manifest's files into ``<execution_dir>/source/`` and verify them.

    Each original is read from ``Path(manifest.locator).parent / name`` (the
    v1 closure is flat siblings of the entrypoint, so that is complete),
    written through ``FileStore(execution_dir, fs=fs).put("source/<name>")``
    — so a local script reaches a remote workspace, and every write under a
    run goes through one FileStore — then read back and checked against the
    manifest's digest. Calling it again overwrites the copies.

    Args:
        manifest: What to copy, from :func:`source_manifest`.
        execution_dir: The attempt's directory (``.../executions/e01``).
        fs: The workspace filesystem; defaults to the local one.

    Raises:
        SourceCaptureError: An original is missing or unreadable, a copy
            cannot be written or read back, or a copy's digest differs from
            the manifest (e.g. the original changed after the manifest).
    """
    origin = Path(manifest.locator).parent
    store = FileStore(execution_dir, fs=fs)
    disk = fs if fs is not None else LocalFileSystem()
    for entry in manifest.files:
        relpath = f"source/{entry.name}"
        try:
            original = (origin / entry.name).read_bytes()
        except OSError as exc:
            raise SourceCaptureError(f"cannot read source {entry.name!r}: {exc}") from exc
        try:
            target = store.put(relpath, original)
            copied = hash_bytes(disk.read_bytes(target))
        except (OSError, ValueError) as exc:
            raise SourceCaptureError(f"cannot write source copy {relpath!r}: {exc}") from exc
        if copied != entry.sha256:
            raise SourceCaptureError(
                f"source copy {relpath!r} has digest {copied}, manifest recorded "
                f"{entry.sha256}; the original changed after the manifest was built"
            )
