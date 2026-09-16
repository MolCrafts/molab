"""Conditional-GET helpers — ``ETag`` + ``If-None-Match`` for the list routes.

The UI polls. Even with a snapshot-backed handler that costs no file I/O, a
poll still serializes a few hundred kilobytes of JSON and re-parses it in the
browser. A read-model version is a perfect validator — it is bumped only when
something a reader can see changed — so the same poll becomes a 304 with an
empty body, and the client keeps the object identity it already has.

Pairing with ``Cache-Control: private, no-cache`` is what makes this work for
the generated ``fetch`` client: ``no-cache`` means "revalidate before reuse",
not "do not store", so the browser sends ``If-None-Match`` on its own and
turns the 304 back into a 200 from its cache. The application code (which
throws on any non-2xx) never sees the 304 at all.

Validators are **weak** (``W/"runs-42"``): the body is semantically equal for a
given version, but byte-equality across processes is not guaranteed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request, Response

__all__ = ["etag_matches", "not_modified", "weak_etag"]


def weak_etag(kind: str, version: int, *parts: object) -> str:
    """Build a weak validator, e.g. ``W/"runs-42"`` or ``W/"events-917-50"``.

    *parts* let a parameterized view (a filtered list, a page) get its own
    validator without colliding with the unfiltered one.
    """
    tail = "-".join(str(p) for p in parts if p is not None and p != "")
    body = f"{kind}-{version}" + (f"-{tail}" if tail else "")
    return f'W/"{body}"'


def _normalize(candidate: str) -> str:
    """Strip the weak prefix and quotes so ``W/"x"`` and ``"x"`` compare equal."""
    value = candidate.strip()
    if value.startswith(("W/", "w/")):
        value = value[2:]
    return value.strip('"')


def etag_matches(header: str | None, etag: str) -> bool:
    """Whether an ``If-None-Match`` *header* selects *etag*.

    Handles the comma-separated list form and ``*`` per RFC 9110, and compares
    weakly (the only comparison defined for weak validators).
    """
    if not header:
        return False
    wanted = _normalize(etag)
    for candidate in header.split(","):
        token = candidate.strip()
        if token == "*" or _normalize(token) == wanted:
            return True
    return False


def not_modified(request: Request, response: Response, etag: str) -> Response | None:
    """Stamp cache headers on *response*; return a 304 when the client is current.

    Always sets ``ETag`` and ``Cache-Control`` (so even a 200 primes the next
    conditional request). Returns a ready-to-return 304 ``Response`` when
    ``If-None-Match`` matches, else ``None`` — so a handler reads:

    ```python
    cached = not_modified(request, response, weak_etag("runs", snapshot.version))
    if cached is not None:
        return cached
    ```
    """
    from fastapi import Response as _Response

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    if etag_matches(request.headers.get("if-none-match"), etag):
        return _Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, no-cache"},
        )
    return None
