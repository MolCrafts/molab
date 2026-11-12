"""The record of a reasoning document.

:class:`~molab.knowledge.concepts.Hypothesis` stores ``verdict``: where the
claim stands against the evidence.

The vocabulary is closed. A value outside it is refused on write and
reported by ``molab validate``; it is never replaced by the default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

HypothesisVerdict = Literal["open", "supported", "refuted", "unsettled"]


class HypothesisRecord(BaseModel):
    """The verdict a Hypothesis document stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: HypothesisVerdict = "open"


def parse_hypothesis(raw: Mapping[str, object] | None) -> HypothesisRecord:
    """Validate the one field a Hypothesis owns. An absent ``verdict`` is ``open``.

    Raises:
        ValueError: ``verdict`` is present and outside the vocabulary.
    """
    if raw is None or "verdict" not in raw:
        return HypothesisRecord()
    try:
        return HypothesisRecord.model_validate({"verdict": raw["verdict"]})
    except ValidationError as exc:
        raise ValueError(
            f"a Hypothesis verdict is one of {', '.join(get_args(HypothesisVerdict))}; "
            f"got {raw['verdict']!r}"
        ) from exc


__all__ = [
    "HypothesisRecord",
    "HypothesisVerdict",
    "parse_hypothesis",
]
