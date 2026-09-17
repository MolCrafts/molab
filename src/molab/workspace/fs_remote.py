"""RemoteFileSystem — delegates to a molq Transport, implementing FileSystem."""

from __future__ import annotations

import base64
import io
import json
import os
import posixpath
import shlex
import tarfile
from collections.abc import Collection, Iterable
from typing import IO, Any, cast

from molq.transport import CommandResult, Transport

from .fs import DirEntry, PathArg, StatResult


class RemoteFileSystem:
    """FileSystem backed by a molq Transport (local or SSH).

    Accepts ``str`` or any :class:`os.PathLike[str]` (incl. :class:`molab.Path`);
    paths are normalized to ``str`` via :func:`os.fspath` before string ops or
    transport calls.  All path arguments are interpreted on the transport's
    filesystem.

    Every operation goes through a :class:`molq.transport.Transport` method —
    including the bulk ones (:meth:`scandir`, :meth:`read_range`,
    :meth:`walk_entries`, :meth:`fetch_files`), which the Transport has no
    named method for and so express as a single ``run(["sh", "-c", ...])``.
    That is one round-trip each, which is the whole point: the per-path
    Protocol turns a 5000-run tree into 10 000 round-trips, while
    :meth:`fetch_files` fetches the same thing in one.
    """

    def __init__(self, transport: Transport) -> None:
        # molq.transport.Transport is a narrow Protocol; this class also uses
        # filesystem ops (is_dir/listdir/rename/copy/stat/…) that the concrete
        # transports provide but the Protocol doesn't statically declare. Widen
        # to Any so the dynamic surface resolves without changing runtime behavior.
        self._t: Any = transport
        # GNU `find -printf` is the fast path for scandir/walk_entries. BSD and
        # macOS `find` lack it; we discover that from the first failure and
        # never pay for it again.
        self._gnu_find: bool = True

    # ── Path ops (static — string manipulation only) ────────────────────

    @staticmethod
    def join(*parts: PathArg) -> str:
        """POSIX-join path segments, preserving an absolute remote root.

        Remote workspaces live at absolute paths (``/home/...``).  A naive
        ``"/".join(p.strip("/") ...)`` drops the leading slash and turns
        marker checks like ``exists(<root>/workspace.json)`` into relative
        lookups that always miss — which is why ``molab info -ws host:/abs``
        reported "No workspace found" even when the file was present.
        """
        cleaned = [os.fspath(p) for p in parts if p]
        if not cleaned:
            return ""
        return posixpath.join(*cleaned)

    @staticmethod
    def dirname(path: PathArg) -> str:
        s = os.fspath(path)
        return s.rsplit("/", 1)[0] if "/" in s else "."

    @staticmethod
    def basename(path: PathArg) -> str:
        s = os.fspath(path)
        return s.rsplit("/", 1)[-1] if s else ""

    @staticmethod
    def resolve(path: PathArg) -> str:
        return os.fspath(path)

    @staticmethod
    def is_absolute(path: PathArg) -> bool:
        return os.fspath(path).startswith(("/", "~/"))

    # ── Delegated to Transport ──────────────────────────────────────────

    def exists(self, path: PathArg) -> bool:
        return self._t.exists(os.fspath(path))

    def is_dir(self, path: PathArg) -> bool:
        return self._t.is_dir(os.fspath(path))

    def is_file(self, path: PathArg) -> bool:
        return self._t.is_file(os.fspath(path))

    def mkdir(self, path: PathArg, *, parents: bool = True, exist_ok: bool = True) -> None:
        self._t.mkdir(os.fspath(path), parents=parents, exist_ok=exist_ok)

    def listdir(self, path: PathArg) -> list[str]:
        return self._t.listdir(os.fspath(path))

    def read_text(self, path: PathArg, encoding: str = "utf-8") -> str:  # noqa: ARG002
        return self._t.read_text(os.fspath(path))

    def read_bytes(self, path: PathArg) -> bytes:
        return self._t.read_bytes(os.fspath(path))

    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[Any]:  # noqa: ARG002
        return io.StringIO(self._t.read_text(os.fspath(path)))

    def write_text(self, path: PathArg, content: str, *, mode: int = 0o600) -> None:  # noqa: ARG002
        self._t.write_text(os.fspath(path), content)

    def write_bytes(self, path: PathArg, content: bytes, *, mode: int = 0o600) -> None:  # noqa: ARG002
        self._t.write_bytes(os.fspath(path), content)

    def rename(self, src: PathArg, dst: PathArg) -> None:
        self._t.rename(os.fspath(src), os.fspath(dst))

    def remove(self, path: PathArg, *, recursive: bool = False) -> None:
        self._t.remove(os.fspath(path), recursive=recursive)

    def copy(self, src: PathArg, dst: PathArg) -> None:
        self._t.copy(os.fspath(src), os.fspath(dst))

    def copytree(self, src: PathArg, dst: PathArg, *, dirs_exist_ok: bool = False) -> None:  # noqa: ARG002
        self._t.copytree(os.fspath(src), os.fspath(dst))

    def stat(self, path: PathArg) -> StatResult:
        d = cast("dict[str, Any]", self._t.stat(os.fspath(path)))
        return StatResult(**d)

    def lstat(self, path: PathArg) -> StatResult:
        return self.stat(path)

    def touch(self, path: PathArg) -> None:
        self._t.touch(os.fspath(path))

    def chmod(self, path: PathArg, mode: int) -> None:
        self._t.chmod(os.fspath(path), mode)

    def getsize(self, path: PathArg) -> int:
        return self._t.getsize(os.fspath(path))

    def symlink(self, src: PathArg, dst: PathArg) -> None:
        self._t.symlink(os.fspath(src), os.fspath(dst))

    def glob(self, path: PathArg, pattern: str) -> Iterable[str]:
        base = os.fspath(path)
        for name in self._t.listdir(base):
            if _glob_match(name, pattern):
                yield self.join(base, name)

    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]:
        # One scandir per directory. The previous body paid an extra `is_dir`
        # round-trip per *entry*, so a tree of M entries cost >= 2M round-trips;
        # the listing already knows which children are directories.
        base = os.fspath(path)
        try:
            entries = self.scandir(base, with_stat=False)
        except (FileNotFoundError, NotADirectoryError):
            return
        for entry in entries:
            full = self.join(base, entry.name)
            if _glob_match(entry.name, pattern):
                yield full
            if entry.is_dir:
                yield from self.rglob(full, pattern)

    # ── Bulk ops (one round-trip each; see the class docstring) ─────────

    def _run_script(self, script: str) -> CommandResult:
        """Ship *script* to the transport's shell as a single command."""
        return self._t.run(["sh", "-c", script])

    def scandir(self, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:  # noqa: ARG002 — remote listings carry metadata for free
        """List a directory with per-entry type and metadata in one round-trip.

        ``with_stat`` is accepted for Protocol conformance but ignored: the
        remote listing carries size and mtime whether or not we ask, so there
        is nothing to save by declining them.
        """
        target = os.fspath(path)
        if self._gnu_find:
            entries = self._scandir_find(target)
            if entries is not None:
                return entries
        return self._scandir_fallback(target)

    def _scandir_find(self, target: str) -> list[DirEntry] | None:
        """GNU ``find -printf`` listing, or ``None`` if this host lacks it.

        Fields are ``%y`` (type of the entry itself, ``l`` for a symlink),
        ``%Y`` (type after following it, ``L``/``N`` for loop/dangling), size,
        mtime and name, NUL-separated and base64-wrapped so names that are not
        valid UTF-8 survive the transport's text capture.
        """
        q = shlex.quote(target)
        script = (
            f"find {q} -mindepth 1 -maxdepth 1 "
            r"-printf '%y\t%Y\t%s\t%T@\t%f\0' | base64"
        )
        result = self._run_script(script)
        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            if "no such file" in stderr:
                raise FileNotFoundError(target)
            if "not a directory" in stderr:
                raise NotADirectoryError(target)
            if "printf" in stderr or "unknown predicate" in stderr or "illegal option" in stderr:
                self._gnu_find = False  # BSD/macOS find — stop trying.
                return None
            raise OSError(f"remote scandir failed: {target}: {result.stderr}")
        return _parse_find_records(base64.b64decode(result.stdout or ""))

    def _scandir_fallback(self, target: str) -> list[DirEntry]:
        """Portable listing: one listdir plus one stat per entry."""
        if not self._t.is_dir(target):
            if self._t.exists(target):
                raise NotADirectoryError(target)
            raise FileNotFoundError(target)
        entries: list[DirEntry] = []
        for name in self._t.listdir(target):
            full = self.join(target, name)
            try:
                st = self.stat(full)
            except (FileNotFoundError, OSError):
                entries.append(DirEntry(name=name, is_dir=False, is_file=False, is_symlink=True))
                continue
            entries.append(
                DirEntry(
                    name=name,
                    is_dir=st.is_dir,
                    is_file=st.is_file,
                    is_symlink=False,
                    size=st.size,
                    mtime=st.mtime,
                )
            )
        return entries

    def read_range(self, path: PathArg, offset: int, length: int) -> bytes:
        """Read one bounded byte range — never transfers the whole file."""
        if offset < 0 or length < 0:
            raise ValueError(f"read_range needs non-negative offset/length, got {offset}/{length}")
        if length == 0:
            return b""
        target = os.fspath(path)
        q = shlex.quote(target)
        # `tail -c +N` is 1-based; head -c bounds the transfer at the source.
        script = f"tail -c +{offset + 1} -- {q} | head -c {length} | base64"
        result = self._run_script(script)
        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            if "is a directory" in stderr:
                raise IsADirectoryError(target)
            if "no such file" in stderr or "cannot open" in stderr:
                raise FileNotFoundError(target)
            raise OSError(f"remote read_range failed: {target}: {result.stderr}")
        return base64.b64decode(result.stdout or "")

    def walk_entries(
        self, root: PathArg, *, max_depth: int, prune: Collection[str] = ()
    ) -> dict[str, list[DirEntry]]:
        """Walk *root* to *max_depth* in one round-trip, pruning named dirs.

        Returns ``{directory: [children]}`` for every directory visited. This
        is what makes a remote workspace's navigation tree loadable at all: the
        per-path Protocol needs a round-trip per directory, this needs one.

        Args:
            root: Directory to walk.
            max_depth: Maximum depth below *root*.
            prune: Directory names never descended into (``executions``,
                ``artifacts``, …).

        Returns:
            Mapping of absolute directory path to its listing. Empty when the
            host lacks GNU ``find`` (callers fall back to per-level scandir).
        """
        target = os.fspath(root)
        q = shlex.quote(target)
        prune_expr = ""
        if prune:
            names = " -o ".join(f"-name {shlex.quote(n)}" for n in sorted(prune))
            prune_expr = f"\\( {names} \\) -prune -o "
        script = (
            f"find {q} -maxdepth {max_depth} {prune_expr}"
            r"-printf '%y\t%Y\t%s\t%T@\t%p\0' | base64"
        )
        result = self._run_script(script)
        if result.returncode != 0:
            return {}
        out: dict[str, list[DirEntry]] = {}
        for kind, target_kind, size, mtime, full in _iter_find_fields(
            base64.b64decode(result.stdout or "")
        ):
            if full == target:
                out.setdefault(target, [])
                continue
            parent = full.rsplit("/", 1)[0] if "/" in full else "."
            name = full.rsplit("/", 1)[-1]
            entry = _entry_from_fields(name, kind, target_kind, size, mtime)
            out.setdefault(parent, []).append(entry)
            if entry.is_dir:
                out.setdefault(full, [])
        return out

    def fetch_files(
        self,
        root: PathArg,
        *,
        names: Collection[str],
        max_bytes: int,
        prune: Collection[str] = (),
    ) -> dict[str, bytes]:
        """Fetch every small file named in *names* under *root*, in one trip.

        The navigation-metadata bulk load: ``run.json`` / ``_ops/run.json`` /
        ``assets.json`` / ``meta.yaml`` for a whole workspace arrive as one
        tar stream instead of one round-trip apiece.

        Args:
            root: Directory to search.
            names: Basenames to collect.
            max_bytes: Per-file size ceiling; larger files are skipped so a
                stray big file cannot blow up the transfer.
            prune: Directory names never descended into.

        Returns:
            Mapping of absolute path to file bytes; empty when the host lacks
            the required tools.
        """
        target = os.fspath(root)
        if not names:
            return {}
        q = shlex.quote(target)
        name_expr = " -o ".join(f"-name {shlex.quote(n)}" for n in sorted(names))
        prune_expr = ""
        if prune:
            pruned = " -o ".join(f"-name {shlex.quote(n)}" for n in sorted(prune))
            prune_expr = f"\\( {pruned} \\) -prune -o "
        script = (
            f"cd {q} && find . {prune_expr}-type f \\( {name_expr} \\) "
            f"-size -{max_bytes}c -print0 | tar --null -T - -cf - | base64"
        )
        result = self._run_script(script)
        if result.returncode != 0:
            return {}
        raw = base64.b64decode(result.stdout or "")
        if not raw:
            return {}
        out: dict[str, bytes] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r|") as tf:
                for member in tf:
                    if not member.isfile():
                        continue
                    fh = tf.extractfile(member)
                    if fh is None:
                        continue
                    rel = member.name.removeprefix("./")
                    out[self.join(target, rel)] = fh.read()
        except (tarfile.TarError, OSError):
            return {}
        return out

    # ── Atomic I/O ──────────────────────────────────────────────────────

    def atomic_write_json(self, path: PathArg, data: object) -> None:
        content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        self._t.write_text(os.fspath(path), content)

    def atomic_write_text(self, path: PathArg, content: str, *, encoding: str = "utf-8") -> None:  # noqa: ARG002
        self._t.write_text(os.fspath(path), content)


def _glob_match(name: str, pattern: str) -> bool:
    """Simple glob matching: * matches anything, otherwise exact."""
    import fnmatch

    return fnmatch.fnmatch(name, pattern)


def _iter_find_fields(raw: bytes) -> Iterable[tuple[str, str, str, str, str]]:
    """Split a NUL-separated ``find -printf`` stream into its five fields.

    Names are decoded with ``surrogateescape`` so a filename that is not valid
    UTF-8 round-trips instead of raising. Records with the wrong field count
    (a name containing a tab would not produce one — ``%f`` is last, so tabs
    inside it stay in the final split) are skipped.
    """
    for record in raw.split(b"\0"):
        if not record:
            continue
        fields = record.decode("utf-8", errors="surrogateescape").split("\t", 4)
        if len(fields) != 5:
            continue
        yield cast("tuple[str, str, str, str, str]", tuple(fields))


def _entry_from_fields(name: str, kind: str, target_kind: str, size: str, mtime: str) -> DirEntry:
    """Build a :class:`DirEntry` from one ``find -printf`` record.

    ``%y`` is the entry's own type (``l`` for a symlink); ``%Y`` is the type
    after following it, with ``L`` (loop) and ``N`` (dangling) for links that
    resolve to nothing — both of which report neither dir nor file, matching
    :meth:`LocalFileSystem.scandir`.
    """
    try:
        size_int = int(size)
    except ValueError:
        size_int = 0
    try:
        mtime_float = float(mtime)
    except ValueError:
        mtime_float = 0.0
    return DirEntry(
        name=name,
        is_dir=target_kind == "d",
        is_file=target_kind == "f",
        is_symlink=kind == "l",
        size=size_int,
        mtime=mtime_float,
    )


def _parse_find_records(raw: bytes) -> list[DirEntry]:
    """Parse a one-level ``find -printf`` listing into entries."""
    return [
        _entry_from_fields(name, kind, target_kind, size, mtime)
        for kind, target_kind, size, mtime, name in _iter_find_fields(raw)
    ]
