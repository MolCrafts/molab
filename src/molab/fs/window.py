"""Windowed text reads — show a slice of a huge file without loading it.

A run's ``stdout.log`` can be multi-gigabyte. Reading it whole to render the
last screenful costs the transfer, the server's memory, and the browser's —
three times the wrong thing. :func:`read_text_window` stats first and then
reads exactly one bounded range, so the cost of viewing a 10 GB log is the
same as viewing a 10 KB one.

The returned :class:`TextWindow` carries the byte cursors alongside the text,
which is what makes incremental follow possible: a poller passes back
``end`` as ``since_offset`` and receives only what was appended since.

Stdlib only — this is a layer-0 primitive shared by workspace, knowledge and
the server routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .base import FileSystem, PathArg

DEFAULT_TEXT_WINDOW_BYTES = 256 * 1024
"""Default window: a few screenfuls of log, small enough to be free."""

MAX_TEXT_WINDOW_BYTES = 2_000_000
"""Hard ceiling on a single window, mirroring the server's text-response cap."""


@dataclass(frozen=True, slots=True)
class TextWindow:
    """A decoded byte range of a file, plus the cursors to continue from.

    Attributes:
        text: The decoded window.
        start: Byte offset of the first returned byte.
        end: Byte offset just past the last returned byte — the cursor to pass
            as ``since_offset`` on the next poll.
        total_bytes: Size of the whole file at read time.
        truncated: The window is not the entire file.
        rewound: ``since_offset`` was past EOF (the file was truncated or
            rotated), so the window restarted from ``start``.
    """

    text: str
    start: int
    end: int
    total_bytes: int
    truncated: bool
    rewound: bool = False


def _align_forward(data: bytes) -> tuple[bytes, int]:
    """Drop a leading partial line; return the remainder and bytes dropped."""
    nl = data.find(b"\n")
    if nl == -1:
        return data, 0
    return data[nl + 1 :], nl + 1


def _align_back(data: bytes) -> tuple[bytes, int]:
    """Drop a trailing partial line; return the remainder and bytes dropped."""
    nl = data.rfind(b"\n")
    if nl == -1:
        return data, 0
    return data[: nl + 1], len(data) - (nl + 1)


def read_text_window(
    fs: FileSystem,
    path: PathArg,
    *,
    max_bytes: int = DEFAULT_TEXT_WINDOW_BYTES,
    mode: Literal["head", "tail"] = "tail",
    since_offset: int | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
    line_aligned: bool = True,
) -> TextWindow:
    """Read at most *max_bytes* of *path* as text — one ``stat``, one range read.

    Three ways to pick the window, in precedence order:

    * *since_offset* given — the bytes appended after that cursor (incremental
      follow). If the file has since shrunk below the cursor it was rotated or
      truncated, so the window restarts at 0 and ``rewound`` is set.
    * ``mode="tail"`` (default) — the last *max_bytes*, which is what a log
      viewer wants.
    * ``mode="head"`` — the first *max_bytes*, which is what a source viewer
      wants.

    With *line_aligned* the window is trimmed to whole lines: a partial last
    line is dropped when the window stops short of EOF, and a partial first
    line when the start was *chosen* by tail mode. A caller-supplied
    *since_offset* is never trimmed forward — it came from a previous window's
    ``end`` and is already on a boundary, so trimming would skip a whole line.
    A window containing no newline at all is returned as-is rather than
    emptied.

    Args:
        fs: The filesystem to read through.
        path: File to read.
        max_bytes: Window ceiling; clamped to :data:`MAX_TEXT_WINDOW_BYTES`.
        mode: ``"tail"`` or ``"head"``; ignored when *since_offset* is given.
        since_offset: Byte cursor from a previous window's ``end``.
        encoding: Text encoding.
        errors: Decode error policy; ``"replace"`` so a window that splits a
            multi-byte character still renders.
        line_aligned: Trim partial lines at the window edges.

    Returns:
        The :class:`TextWindow`.

    Raises:
        ValueError: *max_bytes* is not positive, or *since_offset* is negative.
        IsADirectoryError: *path* is a directory.
        FileNotFoundError: *path* does not exist.
    """
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive, got {max_bytes}")
    if since_offset is not None and since_offset < 0:
        raise ValueError(f"since_offset must be non-negative, got {since_offset}")
    cap = min(max_bytes, MAX_TEXT_WINDOW_BYTES)

    st = fs.stat(path)
    if st.is_dir:
        raise IsADirectoryError(str(path))
    total = st.size

    rewound = False
    # An arbitrary start may split a line and so gets trimmed forward; a
    # caller-supplied cursor must not be, since it came from a previous
    # window's `end` and trimming it would silently skip a whole line.
    start_is_arbitrary = False
    if since_offset is not None:
        if since_offset > total:
            # Rotated or truncated under us — restart rather than report a
            # negative delta.
            start = 0
            rewound = True
        else:
            start = since_offset
    elif mode == "tail":
        start = max(0, total - cap)
        start_is_arbitrary = start > 0
    else:
        start = 0

    want = min(cap, max(0, total - start))
    data = fs.read_range(path, start, want) if want else b""
    end = start + len(data)

    if line_aligned and data:
        if start_is_arbitrary:
            data, dropped = _align_forward(data)
            start += dropped
        if end < total:
            data, dropped = _align_back(data)
            end -= dropped

    return TextWindow(
        text=data.decode(encoding, errors=errors),
        start=start,
        end=end,
        total_bytes=total,
        truncated=start > 0 or end < total,
        rewound=rewound,
    )


__all__ = [
    "DEFAULT_TEXT_WINDOW_BYTES",
    "MAX_TEXT_WINDOW_BYTES",
    "TextWindow",
    "read_text_window",
]
