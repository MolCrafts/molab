"""A LaTeX document with a JSON record: the TeX form of a fenced markdown file.

The record a YAML frontmatter would hold sits, as JSON, in a block of ``%%``
comment lines at the top of the file; the body follows verbatim::

    %% molab-record
    %% {
    %%   "class": "Manuscript",
    %%   "name": "NaCl NEMD"
    %% }
    %% end molab-record
    \\documentclass{revtex4-2}
    ...

Every record line is a TeX comment, so the file compiles as it stands.
:func:`dump` writes exactly that shape and :func:`split` reads it back, so
``dump(*split(text))`` reproduces a file this module wrote. Reading is
tolerant: no record block, an unterminated one, broken JSON or a record that
is not an object reads as ``{}``.

The links a markdown document carries in its narrative live in a TeX body as
whole-line comments (``% - [@cites label](target)``); :func:`link_text` is the
body with everything else blanked, for the markdown link scanner.
:func:`cite_keys` lists the keys of the body's ``\\cite`` commands and
:func:`rename_cite_key` renames one of them.

Layer 0: stdlib only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

#: The first line of a record block.
BEGIN = "%% molab-record"
#: The last line of a record block.
END = "%% end molab-record"
#: The prefix of every line inside a record block.
_PREFIX = "%% "
#: The key written last, as :mod:`molab.frontmatter` does.
_LAST_KEY = "index"

#: A ``\cite``-family command and its key list: ``\cite``, ``\citep``,
#: ``\citet*``, ``\citeauthor``, ``\nocite``, with up to two optional arguments.
_CITE = re.compile(r"\\(?:no)?cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
#: An unescaped ``%`` and the rest of its line.
_COMMENT = re.compile(r"(?<!\\)%.*")


def split(text: str) -> tuple[dict[str, object], str]:
    """Split a TeX document into ``(record, body)``.

    The body is everything after the record block's last line. Without a
    complete record block at the top, the record is empty and the body is the
    whole text.
    """
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != BEGIN:
        return {}, text
    try:
        end = next(i for i, line in enumerate(lines) if line.rstrip("\r") == END)
    except StopIteration:
        return {}, text
    raw = "\n".join(_unprefix(line.rstrip("\r")) for line in lines[1:end])
    body = "\n".join(lines[end + 1 :])
    try:
        loaded = json.loads(raw)
    except ValueError:
        return {}, body
    if not isinstance(loaded, dict):
        return {}, body
    return {str(key): value for key, value in loaded.items()}, body


def _unprefix(line: str) -> str:
    if line.startswith(_PREFIX):
        return line[len(_PREFIX) :]
    return line[2:] if line.startswith("%%") else line


def dump(meta: Mapping[str, object], body: str) -> str:
    """Render *meta* + *body* as a TeX document; *body* is written verbatim.

    Keys keep their order, except ``index``, which is written last. The JSON
    is indented and escapes newlines inside strings, so each of its lines is
    one comment line.
    """
    ordered = {key: value for key, value in meta.items() if key != _LAST_KEY}
    if _LAST_KEY in meta:
        ordered[_LAST_KEY] = meta[_LAST_KEY]
    record = json.dumps(ordered, indent=2, ensure_ascii=False)
    lines = [BEGIN, *(f"{_PREFIX}{line}" for line in record.split("\n")), END]
    return "\n".join(lines) + "\n" + body


def link_text(body: str) -> str:
    """*body* with every character outside a whole-line ``%`` comment blanked.

    Offsets are kept (each blanked character becomes a space, newlines stay),
    so a match against the result is a match against *body*.
    """
    kept: list[str] = []
    for line in body.split("\n"):
        kept.append(line if line.lstrip().startswith("%") else " " * len(line))
    return "\n".join(kept)


def _live_end(line: str) -> int:
    """Where *line*'s comment starts (an unescaped ``%``), or its length."""
    match = _COMMENT.search(line)
    return match.start() if match is not None else len(line)


def rename_cite_key(body: str, old: str, new: str) -> str:
    """*body* with the citation key *old* replaced by *new* in every live ``\\cite``.

    Only a whole key inside a ``\\cite``-family command changes; the spacing
    around it, a key that merely contains *old*, prose and commented-out text
    are kept byte for byte.
    """

    def rekey(match: re.Match[str]) -> str:
        keys = match.group(1)
        parts = keys.split(",")
        renamed = [part.replace(old, new) if part.strip() == old else part for part in parts]
        start = match.start(1) - match.start()
        return match.group(0)[:start] + ",".join(renamed) + match.group(0)[start + len(keys) :]

    lines = []
    for line in body.split("\n"):
        end = _live_end(line)
        lines.append(_CITE.sub(rekey, line[:end]) + line[end:])
    return "\n".join(lines)


def cite_keys(body: str) -> tuple[str, ...]:
    """The citation keys of *body*'s ``\\cite``-family commands, in first-use order.

    Commented-out text is skipped, and so is ``\\nocite{*}``'s ``*``.
    """
    found: list[str] = []
    for line in body.split("\n"):
        live = line[: _live_end(line)]
        for match in _CITE.finditer(live):
            for key in match.group(1).split(","):
                key = key.strip()
                if key and key != "*" and key not in found:
                    found.append(key)
    return tuple(found)
