"""YAML frontmatter on a markdown file — the one implementation.

A file opens with a ``---`` fence, a YAML mapping, and a closing ``---``
fence; everything after is the body. Two owners write this shape: workspace
(a Folder's ``index.md`` record) and knowledge (``knowledges/<slug>.md``).
Both go through here, so there is one parser and one dumper.

Values are JSON values. Loading does not turn an ISO timestamp into a
``datetime`` (the timestamp resolver is off), and dumping never sees one:
callers pass ``model_dump(mode="json")``. A string YAML 1.1 would read back
as another type (``on``, ``no``, ``0123``, an ISO timestamp) is quoted by the
safe dumper, so a round-trip returns the same value.

Broken YAML reads as no frontmatter, so a bad header never breaks a walk.

Layer 0: stdlib, pyyaml and :mod:`molab.fs` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from molab.fs import FileSystem, PathArg

FENCE = "---"

#: The key written last, so a person reading the head sees the record first.
_LAST_KEY = "index"

_HEAD_CHUNK = 4096

_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


class _Loader(yaml.SafeLoader):
    """Safe loader that leaves ISO timestamps as strings."""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class _Dumper(yaml.SafeDumper):
    """Safe dumper; block style, sequences indented under their key, no anchors."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        del indentless
        super().increase_indent(flow, False)

    def ignore_aliases(self, data: object) -> bool:  # noqa: ARG002
        # Two rows sharing one params dict must not come out as ``&id001``.
        return True


_Dumper.add_representer(tuple, lambda dumper, data: dumper.represent_list(list(data)))


def _close(text: str) -> tuple[int, int, int] | None:
    """Locate the YAML head between an opening and a closing ``---`` line.

    Returns:
        ``(head_start, head_end, body_start)`` — the YAML text is
        ``text[head_start:head_end]`` and the body starts just past the
        closing fence's line — or ``None`` when either fence is missing.
    """
    first = text.find("\n")
    if first < 0 or text[:first].rstrip("\r") != FENCE:
        return None
    head_start = pos = first + 1
    while True:
        nl = text.find("\n", pos)
        line_end = len(text) if nl < 0 else nl
        if text[pos:line_end].rstrip("\r") == FENCE:
            return head_start, pos, len(text) if nl < 0 else nl + 1
        if nl < 0:
            return None
        pos = nl + 1


def _parse(raw: str) -> dict[str, object] | None:
    try:
        loaded = yaml.load(raw, Loader=_Loader)
    except yaml.YAMLError:
        return None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        return None
    return {str(key): value for key, value in loaded.items()}


def split(text: str) -> tuple[dict[str, object], str]:
    """Split *text* into ``(meta, body)``.

    No opening fence, no closing fence, broken YAML, or a head that is not a
    mapping all return ``({}, text)``. Exactly the closing fence's line is
    removed, so ``dump(*split(text))`` reproduces a file this module wrote.
    """
    bounds = _close(text)
    if bounds is None:
        return {}, text
    head_start, head_end, body_start = bounds
    meta = _parse(text[head_start:head_end])
    if meta is None:
        return {}, text
    return meta, text[body_start:]


def dump(meta: Mapping[str, object], body: str) -> str:
    """Render *meta* + *body* as a markdown file with a YAML fence.

    Keys keep their order, except ``index``, which is written last. Empty
    *meta* returns *body* unchanged (no fence).
    """
    if not meta:
        return body
    ordered = {key: value for key, value in meta.items() if key != _LAST_KEY}
    if _LAST_KEY in meta:
        ordered[_LAST_KEY] = meta[_LAST_KEY]
    head = yaml.dump(
        ordered,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1 << 30,
    )
    return f"{FENCE}\n{head}{FENCE}\n{body}"


def read_head(fs: FileSystem, path: PathArg) -> dict[str, object] | None:
    """Read the frontmatter of *path* without reading its body.

    Reads growing windows from the start of the file until the closing fence
    is in hand. A missing file, a file that does not open with a fence, or an
    unterminated head returns ``None``; broken YAML returns ``{}``.
    """
    chunk = _HEAD_CHUNK
    data = b""
    while True:
        try:
            piece = fs.read_range(path, len(data), chunk)
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            return None
        except OSError:
            return None
        data += piece
        if len(data) >= len(FENCE) and not data.startswith(FENCE.encode()):
            return None
        eof = len(piece) < chunk
        text = data.decode("utf-8", errors="replace")
        bounds = _close(text)
        # A fence line cut at the window edge may be ``---`` + more; wait for
        # its newline unless the file has ended.
        if bounds is not None and (eof or bounds[2] < len(text)):
            return _parse(text[bounds[0] : bounds[1]]) or {}
        if eof:
            return None
        chunk *= 2


__all__ = ["FENCE", "dump", "read_head", "split"]
