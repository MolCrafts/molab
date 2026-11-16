"""The one timestamp convention for workspace records: timezone-aware UTC.

Every record timestamp is written as aware UTC. A naive value in an older
record was written by ``datetime.now()`` — local time — so it is read as
local time and converted, never relabelled: two records can always be
ordered, and the instant stays the one that was recorded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, overload

from pydantic import AfterValidator

__all__ = ["UtcDatetime", "as_utc", "utc_now"]


def utc_now() -> datetime:
    """The current time as aware UTC."""
    return datetime.now(UTC)


@overload
def as_utc(value: datetime) -> datetime: ...
@overload
def as_utc(value: datetime | None) -> datetime | None: ...
def as_utc(value: datetime | None) -> datetime | None:
    """*value* as aware UTC. A naive value is local time (how it was written)."""
    if value is None:
        return None
    return value.astimezone(UTC)


#: A model field that always holds aware UTC.
UtcDatetime = Annotated[datetime, AfterValidator(as_utc)]
