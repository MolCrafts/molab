"""``CountingFileSystem`` — a call-counting wrapper around any ``FileSystem``.

Used by the syscall-budget tests to lock statements such as "listing 1000
runs opens at most 1000 files and never calls ``exists``". It delegates every
attribute to the wrapped filesystem via ``__getattr__`` (the pattern from
``tests/test_agent/test_remote_session.py``), so it works with
``LocalFileSystem``, the in-memory fakes and ``CachedRemoteFileSystem`` alike.

It is not a ``LocalFileSystem`` subclass, but it *reports* the wrapped
class through ``__class__`` so every ``isinstance(fs, LocalFileSystem)`` gate
(``Workspace`` root resolution, the workspace-events remote-root guard,
``Folder.move_to``) sees through the wrapper — otherwise a counting workspace
would silently be treated as remote and the measured paths would differ from
the real ones.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

_READ_METHODS = frozenset({"read_text", "read_bytes", "read_range"})


class CountingFileSystem:
    """Wrap *inner* and count every method call by name and by basename."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: Counter[str] = Counter()
        self.by_basename: Counter[tuple[str, str]] = Counter()
        self.log: list[tuple[str, str, dict[str, object]]] = []
        self.bytes_read: int = 0

    # ── inspection ────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.calls.clear()
        self.by_basename.clear()
        self.log.clear()
        self.bytes_read = 0

    def total(self) -> int:
        return sum(self.calls.values())

    def count(self, *names: str) -> int:
        return sum(self.calls[n] for n in names)

    def opens(self) -> int:
        """Whole-file reads: ``open`` + ``read_text`` + ``read_bytes``."""
        return self.count("open", "read_text", "read_bytes")

    def stats(self) -> int:
        return self.count("stat", "lstat", "getsize")

    def probes(self) -> int:
        """Existence probes that a try-read should have replaced."""
        return self.count("exists", "is_dir", "is_file")

    def for_basename(self, basename: str, method: str | None = None) -> int:
        if method is None:
            return sum(n for (m, b), n in self.by_basename.items() if b == basename)
        return self.by_basename[(method, basename)]

    def assert_at_most(self, **limits: int) -> None:
        """``fs.assert_at_most(open=10, exists=0)`` — raises with the full counter."""
        bad = {
            name: (self.calls[name], cap) for name, cap in limits.items() if self.calls[name] > cap
        }
        assert not bad, f"fs call budget exceeded {bad!r}; all calls: {dict(self.calls)!r}"

    # ── delegation ────────────────────────────────────────────────────────

    @property
    def inner(self) -> Any:
        return self._inner

    @property
    def __class__(self) -> type:  # type: ignore[override]
        """The wrapped class, so ``isinstance`` gates see through the wrapper."""
        return type(self._inner)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr) or name.startswith("_"):
            return attr
        return self._wrap(name, attr)

    def _wrap(self, name: str, attr: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: object, **kwargs: object) -> Any:
            first = args[0] if args else kwargs.get("path", "")
            path = str(first)
            self.calls[name] += 1
            self.by_basename[(name, path.rsplit("/", 1)[-1])] += 1
            self.log.append((name, path, dict(kwargs)))
            result = attr(*args, **kwargs)
            if name in _READ_METHODS and isinstance(result, (str, bytes)):
                self.bytes_read += len(result)
            return result

        return wrapped
