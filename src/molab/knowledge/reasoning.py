"""Records of the two reasoning documents.

* :class:`~molab.knowledge.concepts.Hypothesis` stores ``verdict``: where the
  claim stands against the evidence.
* :class:`~molab.knowledge.concepts.Decision` stores ``status``: whether the
  choice is made or still waits for a person.

Each vocabulary is closed. A value outside it is refused on write and
reported by ``molab validate``; it is never replaced by the default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

HypothesisVerdict = Literal["open", "supported", "refuted", "unsettled"]
DecisionStatus = Literal["open", "made"]


class HypothesisRecord(BaseModel):
    """The verdict a Hypothesis document stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: HypothesisVerdict = "open"


class DecisionRecord(BaseModel):
    """The status a Decision document stores. ``open`` waits for a person."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DecisionStatus = "made"


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


def parse_decision(raw: Mapping[str, object] | None) -> DecisionRecord:
    """Validate the one field a Decision owns. An absent ``status`` is ``made``.

    Raises:
        ValueError: ``status`` is present and outside the vocabulary.
    """
    if raw is None or "status" not in raw:
        return DecisionRecord()
    try:
        return DecisionRecord.model_validate({"status": raw["status"]})
    except ValidationError as exc:
        raise ValueError(
            f"a Decision status is one of {', '.join(get_args(DecisionStatus))}; "
            f"got {raw['status']!r}"
        ) from exc


__all__ = [
    "DecisionRecord",
    "DecisionStatus",
    "HypothesisRecord",
    "HypothesisVerdict",
    "parse_decision",
    "parse_hypothesis",
]
