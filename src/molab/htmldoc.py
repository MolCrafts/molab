"""An HTML document with a JSON record: the HTML form of a fenced markdown file.

The record a YAML frontmatter would hold sits, as JSON, in one
``<script type="application/json" id="molab-record">`` in the head; the body
is stored verbatim between ``<body>`` and ``</body>``::

    <!doctype html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script type="application/json" id="molab-record">
    {record as JSON}
    </script>
    </head>
    <body>
    {body}
    </body>
    </html>

:func:`dump` writes exactly that shape and :func:`split` reads it back, so
``dump(*split(text), title=...)`` reproduces a file this module wrote. Reading
is tolerant: no record script reads as ``{}``, broken JSON or a record that is
not an object reads as ``{}``, and a file without ``<body>`` is all body after
its head. :func:`plain_text` is the readable text of a body, for an excerpt
or a search index.

Layer 0: stdlib only.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping

#: The ``id`` of the script element that holds the record.
RECORD_ID = "molab-record"

#: The key written last, as :mod:`molab.frontmatter` does.
_LAST_KEY = "index"

_RECORD = re.compile(
    r"<script\b[^>]*\bid\s*=\s*([\"'])" + RECORD_ID + r"\1[^>]*>(?P<json>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HEAD_CLOSE = re.compile(r"</head\s*>", re.IGNORECASE)
_BODY_OPEN = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_SPACES = re.compile(r"[ \t]+")


def _record(text: str) -> tuple[dict[str, object], int]:
    """The record in *text* and the offset just past its script element."""
    match = _RECORD.search(text)
    if match is None:
        return {}, 0
    try:
        loaded = json.loads(match.group("json"))
    except ValueError:
        return {}, match.end()
    if not isinstance(loaded, dict):
        return {}, match.end()
    return {str(key): value for key, value in loaded.items()}, match.end()


def _trim_one_newline(body: str) -> str:
    """*body* without one leading and one trailing newline (the ones :func:`dump` adds)."""
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    if body.endswith("\r\n"):
        body = body[:-2]
    elif body.endswith("\n"):
        body = body[:-1]
    return body


def split(text: str) -> tuple[dict[str, object], str]:
    """Split an HTML document into ``(record, body)``.

    The body is the inner content of ``<body>`` with one leading and one
    trailing newline removed. Without ``<body>`` it is the text after
    ``</head>``, or the whole text when there is no head either.
    """
    meta, record_end = _record(text)
    head = _HEAD_CLOSE.search(text, record_end)
    start = head.end() if head is not None else record_end
    opened = _BODY_OPEN.search(text, start)
    if opened is None:
        if head is None and record_end == 0:
            return meta, text
        return meta, text[start:]
    closes = list(_BODY_CLOSE.finditer(text, opened.end()))
    end = closes[-1].start() if closes else len(text)
    return meta, _trim_one_newline(text[opened.end() : end])


def _record_json(meta: Mapping[str, object]) -> str:
    """*meta* as indented JSON that cannot end its script element early."""
    ordered = {key: value for key, value in meta.items() if key != _LAST_KEY}
    if _LAST_KEY in meta:
        ordered[_LAST_KEY] = meta[_LAST_KEY]
    raw = json.dumps(ordered, indent=2, ensure_ascii=False)
    # ``</`` would close the script and ``<!--`` would open a comment state
    # inside it; both escapes are legal JSON and read back as the same string.
    return raw.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def dump(meta: Mapping[str, object], body: str, *, title: str = "") -> str:
    """Render *meta* + *body* as an HTML document; *body* is written verbatim.

    Keys keep their order, except ``index``, which is written last.
    """
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<script type="application/json" id="{RECORD_ID}">\n'
        f"{_record_json(meta)}\n"
        "</script>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def plain_text(body: str) -> str:
    """The readable text of an HTML *body*: comments and tags removed, entities decoded.

    Attribute values go with their tags. Markdown inside an element stays as
    written, so a ``# heading`` line is still a heading line.
    """
    text = _TAG.sub(" ", _COMMENT.sub(" ", body))
    lines = (_SPACES.sub(" ", line).strip() for line in html.unescape(text).splitlines())
    return "\n".join(line for line in lines if line)


__all__ = ["RECORD_ID", "dump", "plain_text", "split"]
