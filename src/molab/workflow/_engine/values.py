"""The run's content-addressed value store: the bytes behind every node record.

Every attempt of a run shares one store, the directory the workspace hands
out as ``run_context.values_dir`` (writers) / ``run.values_dir()`` (readers);
the workflow layer never composes that path. The node journal
(:mod:`.persistence`) records task inputs and outputs by **ref**
(``sha256:<hex>``), never by value, so a value appears on disk once however
many records name it: an upstream output and the downstream input it feeds
are the same bytes and therefore the same file, and two attempts that
produce the same value share it too.

**Encoding.** A value built only from ``dict`` (``str`` keys), ``list``,
``str``, ``int``, finite ``float``, ``bool`` and ``None`` — checked by exact
type, so a ``tuple`` or a ``str`` subclass does not qualify — is written as
canonical JSON (``sort_keys``, compact separators) to ``<hex>.json``; any
other value is pickled (protocol :data:`PICKLE_PROTOCOL`) to ``<hex>.pkl``.
The digest is over the encoded bytes, so the two encodings never collide.
A value that cannot be pickled raises :class:`UnrecordableValueError`; the
caller records why, and that node cannot be re-run from the record.

**Trust.** :meth:`ValueStore.get` unpickles. The store is a workspace record
(tracked in git, shared with collaborators), so load values only from
workspaces you trust — the same trust ``molab run`` already places in the
workflow script beside them.

Writes are atomic and go through :class:`~molab.workspace.file_store.FileStore`
on the given ``FileSystem`` (the local disk of the executing host by
default); reads go through the ``FileSystem`` too, so a remote workspace
reads its own values.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import re
from os import PathLike, fspath
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from molab.fs import FileSystem

#: The prefix of every ref.
REF_PREFIX = "sha256:"

#: The pickle protocol values are written with (fixed, so the bytes are stable).
PICKLE_PROTOCOL = 5

#: Longest preview string recorded for a pickled value.
PREVIEW_CHARS = 120

Encoding = Literal["json", "pickle"]

#: File suffix per encoding; ``<hex><suffix>`` is the workspace's legal entry
#: name in the values directory (``molab.workspace.naming.VALUE_FILE_RE``).
_SUFFIX: dict[str, str] = {"json": ".json", "pickle": ".pkl"}
_REF_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class UnrecordableValueError(ValueError):
    """A value can be neither JSON-encoded nor pickled, so it cannot be recorded."""


def _json_faithful(value: Any) -> bool:  # noqa: ANN401
    """True iff *value* decodes from JSON as an equal value of the same types."""
    kind = type(value)
    if value is None or kind in (str, int, bool):
        return True
    if kind is float:
        return math.isfinite(value)
    if kind is list:
        return all(_json_faithful(item) for item in value)
    if kind is dict:
        return all(type(k) is str and _json_faithful(v) for k, v in value.items())
    return False


def encode(value: Any) -> tuple[bytes, Encoding]:  # noqa: ANN401
    """Encode *value* as stored: canonical JSON when faithful, otherwise pickle.

    Raises:
        UnrecordableValueError: *value* cannot be pickled.
    """
    try:
        faithful = _json_faithful(value)
    except RecursionError:
        faithful = False
    if faithful:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return text.encode("utf-8"), "json"
    try:
        return pickle.dumps(value, protocol=PICKLE_PROTOCOL), "pickle"
    except Exception as exc:
        raise UnrecordableValueError(
            f"{type(value).__name__} value is neither JSON-safe nor picklable "
            f"({type(exc).__name__}: {exc})"
        ) from exc


def preview(value: Any) -> str:  # noqa: ANN401
    """A short ``repr`` of *value* for a record (never used to rebuild it)."""
    try:
        text = repr(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1] + "…"


def ref_digest(ref: str) -> str:
    """The hex digest of *ref*.

    Raises:
        ValueError: *ref* is not ``sha256:<64 hex>``.
    """
    match = _REF_RE.match(ref) if isinstance(ref, str) else None
    if match is None:
        raise ValueError(f"not a value ref: {ref!r}")
    return match.group(1)


class ValueStore:
    """Content-addressed values under one directory (see the module docstring)."""

    def __init__(self, root: str | PathLike[str], *, fs: FileSystem | None = None) -> None:
        from molab.workspace.fs_local import LocalFS

        self._root = fspath(root)
        self._fs: FileSystem = fs if fs is not None else LocalFS()

    @property
    def root(self) -> str:
        return self._root

    def _path(self, digest: str, encoding: Encoding) -> str:
        return self._fs.join(self._root, digest + _SUFFIX[encoding])

    def put(self, value: Any) -> str:  # noqa: ANN401
        """Store *value* (a no-op when its digest is already stored); return its ref."""
        return self.put_encoded(value)[0]

    def put_encoded(self, value: Any) -> tuple[str, Encoding]:  # noqa: ANN401
        """:meth:`put`, also returning the encoding used.

        Raises:
            UnrecordableValueError: *value* cannot be encoded.
        """
        data, encoding = encode(value)
        return self.put_bytes(data, encoding), encoding

    def put_bytes(self, data: bytes, encoding: Encoding) -> str:
        """Store bytes already in the store's *encoding* (see :func:`encode`).

        The ``process`` executor hands back a child's output this way, so a
        value is encoded once, in the process (and thread) that made it.
        """
        from molab.workspace.file_store import FileStore

        digest = hashlib.sha256(data).hexdigest()
        if not self._fs.exists(self._path(digest, encoding)):
            FileStore(self._root, fs=self._fs).put(digest + _SUFFIX[encoding], data)
        return REF_PREFIX + digest

    def encoding_of(self, ref: str) -> Encoding:
        """How *ref* is stored.

        Raises:
            FileNotFoundError: The store holds no value for *ref*.
        """
        digest = ref_digest(ref)
        for encoding in ("json", "pickle"):
            if self._fs.is_file(self._path(digest, encoding)):
                return encoding
        raise FileNotFoundError(f"value {ref} is not in {self._root}")

    def get(self, ref: str) -> Any:  # noqa: ANN401
        """Load the value *ref* names, verifying its digest.

        Raises:
            FileNotFoundError: The store holds no value for *ref*.
            ValueError: *ref* is malformed, or the stored bytes do not match it.
        """
        digest = ref_digest(ref)
        encoding = self.encoding_of(ref)
        data = self._fs.read_bytes(self._path(digest, encoding))
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"value {ref} in {self._root} is corrupt (digest mismatch)")
        return decode(data, encoding)


def decode(data: bytes, encoding: Encoding) -> Any:  # noqa: ANN401
    """The value *data* encodes (the inverse of :func:`encode`)."""
    if encoding == "json":
        return json.loads(data.decode("utf-8"))
    return pickle.loads(data)  # a workspace record; see "Trust"


__all__ = [
    "PICKLE_PROTOCOL",
    "REF_PREFIX",
    "Encoding",
    "UnrecordableValueError",
    "ValueStore",
    "decode",
    "encode",
    "preview",
    "ref_digest",
]
