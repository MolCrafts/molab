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

``Run._create_execution`` runs them, on the experiment's bound entrypoint, in that order around
creating the record, so each attempt's manifest is on its Execution record and
its copies are under ``executions/eNN/source/``.

Every read goes through the workspace's filesystem (``fs``), local or remote,
with that filesystem's own path rules (``FileSystem.resolve``): a remote path
is never resolved, read or handed to ``git`` on this machine, where it can name
another directory (macOS resolves ``/home/...`` to
``/System/Volumes/Data/home/...``). A remote tree's git state is unknown.

The workspace layer must not import upstream molab layers (see the layer DAG in
CLAUDE.md / ``test_import_guard``); this module uses only the stdlib and
workspace-local types.

A captured file's name is its path relative to the entrypoint's directory,
so two modules that share a basename (``pkg/utils.py`` and ``other/utils.py``)
stay two files under ``source/``. Stdlib and third-party imports are ignored.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from molab.ids import compute_content_hash, hash_bytes

from .domain import SourceFile, SourceManifest
from .file_store import FileStore
from .fs import FileSystem, PathArg
from .fs_local import LocalFS

__all__ = [
    "SourceCaptureError",
    "captured_names",
    "copy_sources",
    "local_import_digest",
    "source_manifest",
]


class SourceCaptureError(RuntimeError):
    """The captured source copy does not match its manifest.

    Raised when an original is missing or unreadable, a copy cannot be
    written, or a copy's digest differs from the one the manifest recorded
    (for example, the original was edited after the manifest was built).
    """


class _Tree:
    """The files the closure reads: a filesystem, or it after one pending write.

    ``fs`` is the workspace filesystem (local by default); every path is
    resolved and read through it, so a remote path keeps its own meaning.
    ``pending`` is ``(path, text)``: the file a caller is about to write and
    its text (``None`` when unknown: the file's text on disk when it has one,
    else it exists with no imports followed). It lets a pre-write check ask
    the closure the same question validation asks after the write.
    """

    def __init__(
        self, fs: FileSystem | None = None, pending: tuple[Path, str | None] | None = None
    ) -> None:
        self.fs: FileSystem = fs if fs is not None else LocalFS()
        self._path = self.resolve(pending[0]) if pending is not None else None
        self._text = pending[1] if pending is not None else None

    @property
    def local(self) -> bool:
        return isinstance(self.fs, LocalFS)

    def resolve(self, path: Path) -> Path:
        """*path* by the filesystem's rules: symlinks on a local disk, lexical remotely."""
        return Path(self.fs.resolve(path))

    def is_file(self, path: Path) -> bool:
        return self.resolve(path) == self._path or self.fs.is_file(path)

    def is_dir(self, path: Path) -> bool:
        resolved = self.resolve(path)
        return (self._path is not None and resolved in self._path.parents) or self.fs.is_dir(path)

    def read(self, path: Path) -> str | None:
        """*path*'s text (``None``: the pending file's unknown text)."""
        if self.resolve(path) == self._path and (
            self._text is not None or not self.fs.is_file(path)
        ):
            return self._text
        return self.fs.read_text(path, encoding="utf-8")

    def digest(self, path: Path) -> str:
        """*path*'s content digest; streamed (and memoized) on a local disk."""
        return compute_content_hash(path) if self.local else hash_bytes(self.fs.read_bytes(path))


_DISK = _Tree()


def _module_files(base: Path, dotted: str, names: list[str], tree: _Tree = _DISK) -> list[Path]:
    """First-party files a module path names under *base*, and its submodules.

    Walks ``a.b.c`` one segment at a time: a package contributes its
    ``__init__.py`` and is descended into, a module file ends the walk (any
    later segment is an attribute of it). When the walk ends on a package,
    each name in *names* that is itself a submodule there (``from lib import
    render`` → ``lib/render.py``) is included too — importing it runs it.
    A first segment that is not under *base* is not first-party: nothing.
    """
    found: list[Path] = []
    directory: Path | None = base
    for part in dotted.split(".") if dotted else []:
        if directory is None:
            break
        package = directory / part / "__init__.py"
        module = directory / f"{part}.py"
        if tree.is_file(package):
            found.append(tree.resolve(package))
            directory = directory / part
        elif tree.is_file(module):
            found.append(tree.resolve(module))
            directory = None
        elif tree.is_dir(directory / part):
            # A namespace package has no __init__.py, but its submodules
            # are still first-party source and contribute to the digest.
            directory = directory / part
        else:
            return found
    if directory is not None:
        for name in names:
            if name == "*":
                continue
            package = directory / name / "__init__.py"
            module = directory / f"{name}.py"
            if tree.is_file(package):
                found.append(tree.resolve(package))
            elif tree.is_file(module):
                found.append(tree.resolve(module))
    return found


def _import_files(current: Path, root: Path, node: ast.AST, tree: _Tree = _DISK) -> list[Path]:
    """First-party files one ``import`` statement in *current* names.

    Absolute imports resolve from *root* (the entrypoint's directory); a
    relative import from the package of *current*, walked up one directory
    per extra dot. ``import a.b`` names ``a/__init__.py`` and ``a/b.py``;
    ``from a import b`` names ``a/__init__.py`` and, when ``b`` is a
    submodule, ``a/b.py``.
    """
    if isinstance(node, ast.Import):
        return [f for alias in node.names for f in _module_files(root, alias.name, [], tree)]
    if not isinstance(node, ast.ImportFrom):
        return []
    names = [alias.name for alias in node.names]
    if node.level == 0:
        return _module_files(root, node.module or "", names, tree) if node.module else []
    base = current.parent
    for _ in range(node.level - 1):
        base = base.parent
    return _module_files(base, node.module or "", names, tree)


def _capture_name(root: Path, src: Path, tree: _Tree = _DISK) -> str:
    """*src* relative to the entrypoint directory, as a POSIX path.

    ``helper.py`` stays ``helper.py``. A relative import of ``pkg/utils.py``
    stays ``pkg/utils.py``. A file outside that directory cannot be stored:
    the copy lives under ``source/`` and must not escape it.
    """
    rel = Path(os.path.relpath(tree.resolve(src), tree.resolve(root)))
    if rel.is_absolute() or ".." in rel.parts:
        raise SourceCaptureError(
            f"source {src} is outside the entrypoint directory {root}; "
            "it cannot be stored under source/"
        )
    return rel.as_posix()


def _local_import_closure(entrypoint: Path, tree: _Tree = _DISK) -> list[Path]:
    """Entrypoint + transitively-imported first-party modules.

    A module is first-party when its file is under ``root`` (the entrypoint's
    directory): ``m.py`` or a package (including namespace packages), followed
    down a dotted path and into imported submodules (:func:`_import_files`) — ``from lib import
    render`` brings ``lib/render.py``, not just ``lib/__init__.py``. A
    relative import is resolved from the file that wrote it. Stdlib /
    third-party imports resolve to no file and are skipped. Returns the
    entrypoint first, then the rest sorted by path.
    """
    entrypoint = tree.resolve(entrypoint)
    root = entrypoint.parent
    seen: dict[Path, None] = {}
    stack = [entrypoint]
    while stack:
        current = tree.resolve(stack.pop())
        if current in seen or not tree.is_file(current):
            continue
        seen[current] = None
        try:
            text = tree.read(current)
            parsed = ast.parse(text, filename=str(current)) if text is not None else None
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if parsed is None:
            continue
        for node in ast.walk(parsed):
            for candidate in _import_files(current, root, node, tree):
                if candidate not in seen:
                    stack.append(candidate)
    rest = sorted((p for p in seen if p != entrypoint), key=lambda p: str(p))
    return [entrypoint, *rest]


def local_import_digest(module_file: PathArg) -> str | None:
    """Digest of the first-party modules *module_file* imports, itself excluded.

    The same closure an attempt captures as source: sibling ``.py`` modules
    imported anywhere in the file (a function body included), transitively.
    The importing file itself is left out — its own code is identified
    elsewhere — so the digest changes exactly when a helper module changes.

    Args:
        module_file: The file that defines the code being identified.

    Returns:
        ``sha256`` over the sorted ``(name, content digest)`` pairs, or
        ``None`` when the file imports no first-party module (or is missing).
    """
    path = Path(module_file).resolve()
    if not path.is_file():
        return None
    deps = _local_import_closure(path)[1:]
    if not deps:
        return None
    # Keyed by path under the importing file's directory: two packages'
    # ``__init__.py`` must not collapse onto one name.
    payload = "\n".join(
        f"{Path(os.path.relpath(dep, path.parent)).as_posix()}:{_sha256(dep)}" for dep in deps
    )
    return hashlib.sha256(payload.encode()).hexdigest()


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


def _captured(path: Path, tree: _Tree = _DISK) -> list[tuple[str, Path]]:
    """``(name under source/, original)`` for each file an attempt of *path* captures.

    Raises:
        SourceCaptureError: A file lies outside the entrypoint directory, or two
            files would be stored under one name.
    """
    root = path.parent
    captured: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for src in _local_import_closure(path, tree):
        name = _capture_name(root, src, tree)
        if name in seen:
            raise SourceCaptureError(f"two source files would be stored as {name!r}")
        seen.add(name)
        captured.append((name, src))
    return captured


def captured_names(
    entrypoint: PathArg,
    *,
    pending: tuple[PathArg, str | None] | None = None,
    fs: FileSystem | None = None,
) -> tuple[str, ...]:
    """The names, relative to its directory, of the files an attempt of *entrypoint* captures.

    The one rule for "which files beside a workflow script belong to it":
    :func:`source_manifest` stores exactly these, the layout validator holds
    them legal beside an experiment's ``workflow.py``, and the pre-write
    path check asks it about the tree as it will be after the write.

    Args:
        entrypoint: The workflow script; it must be a file (or the pending one).
        pending: ``(path, text)`` of a file about to be written: the closure
            is read as if it were already there (``text`` ``None``: present,
            imports unknown).
        fs: The filesystem the tree is read through; defaults to the local one.

    Returns:
        POSIX paths (``workflow.py``, ``helper.py``, ``pkg/units.py``), the
        entrypoint first.

    Raises:
        FileNotFoundError: *entrypoint* is not a file.
        SourceCaptureError: The closure cannot be stored under ``source/``.
    """
    tree = _Tree(fs, (Path(pending[0]), pending[1]) if pending is not None else None)
    path = tree.resolve(Path(entrypoint))
    if not tree.is_file(path):
        raise FileNotFoundError(f"source entrypoint {str(entrypoint)!r} is not a file")
    return tuple(name for name, _src in _captured(path, tree))


def source_manifest(
    entrypoint: PathArg, *, now: datetime | None = None, fs: FileSystem | None = None
) -> SourceManifest:
    """Describe the source an attempt would capture, without copying anything.

    A pure read: it hashes the **originals** (the entrypoint and its
    first-party import closure) and queries their VCS state, and writes no
    file. Call it before creating the Execution record, so a missing
    entrypoint fails while no record exists yet.

    Args:
        entrypoint: The defining script (the file molab re-imports to execute).
        now: Capture timestamp (injectable for deterministic tests); defaults
            to the current UTC time.
        fs: The workspace filesystem the originals are read through; defaults
            to the local one.

    Returns:
        The manifest: ``entrypoint`` is the basename, ``locator`` the resolved
        absolute path (never hashed; used only to locate the originals at
        capture time),
        ``files`` the closure with the entrypoint first and the rest sorted by
        name, plus ``vcs_commit`` / ``vcs_dirty`` (both ``None``, unknown, for
        a tree read through a remote filesystem: ``git`` runs on this machine
        only) and ``captured_at``.

    Raises:
        FileNotFoundError: *entrypoint* is not a file.
        SourceCaptureError: A file in the closure (the entrypoint included)
            exists but cannot be read.
    """
    tree = _Tree(fs)
    path = tree.resolve(Path(entrypoint))
    if not tree.fs.is_file(path):
        raise FileNotFoundError(f"source entrypoint {str(entrypoint)!r} is not a file")
    files: list[SourceFile] = []
    for name, src in _captured(path, tree):
        try:
            files.append(SourceFile(name=name, sha256=tree.digest(src)))
        except OSError as exc:
            raise SourceCaptureError(f"cannot read source {name!r}: {exc}") from exc
    commit, dirty = _vcs_state(path.parent) if tree.local else (None, None)
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

    Each original is read through *fs* from ``Path(manifest.locator).parent
    / name``, where *name* is the path relative to the entrypoint directory —
    the originals live with the workspace, as :func:`source_manifest` read
    them — and written through ``FileStore(execution_dir, fs=fs).put("source/<name>")``,
    so every write under a run goes through one FileStore; each copy is then
    read back and checked against the manifest's digest. Calling it again
    overwrites the copies.

    Args:
        manifest: What to copy, from :func:`source_manifest`.
        execution_dir: The attempt's directory (``.../executions/e01``).
        fs: The workspace filesystem, for the originals and the copies;
            defaults to the local one.

    Raises:
        SourceCaptureError: An original is missing or unreadable, a copy
            cannot be written or read back, or a copy's digest differs from
            the manifest (e.g. the original changed after the manifest).
    """
    origin = Path(manifest.locator).parent
    store = FileStore(execution_dir, fs=fs)
    disk = fs if fs is not None else LocalFS()
    for entry in manifest.files:
        relpath = f"source/{entry.name}"
        try:
            original = disk.read_bytes(origin / entry.name)
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
