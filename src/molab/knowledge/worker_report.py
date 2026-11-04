"""The two structured records a supervised worker round exchanges.

A supervising agent (Tack) dispatches a worker with a *brief* — a
:class:`~molab.knowledge.concepts.Note` whose record is ``kind: brief`` —
and takes back a *worker report* — a :class:`~molab.knowledge.concepts.Report`
whose record is ``kind: worker_report``. The Delegation that dispatched the
round links both from its attempt. molab validates and stores them; the
supervisor writes them. Tack mirrors these models field for field, so the
names here are the contract.

A record is the frontmatter of the document minus the keys every document
carries (:data:`~molab.knowledge.record.COMMON_KEYS`). ``kind`` is the
discriminator: a record without one is an ordinary Report or Note, and a
record with another kind is left to the other checks. The frontmatter does
not write an empty value, so every list and mapping field defaults to empty:
a report with nothing to declare reads back the same as one that said so.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .record import COMMON_KEYS

__all__ = [
    "WORKER_RECORD_CLASSES",
    "BriefRecord",
    "CapabilityGap",
    "CheckItem",
    "Component",
    "Deviation",
    "Digest",
    "Outcome",
    "Product",
    "Protocol",
    "TokenUsage",
    "Verdict",
    "WorkerReportRecord",
    "check_worker_record",
    "parse_brief",
    "parse_worker_report",
]

Outcome = Literal["done", "partial", "blocked", "failed"]
Verdict = Literal["pass", "fail", "unknown"]
Component = Literal["molpy", "atomiverse", "molvis", "molab", "dsh", "tack"]
#: A lowercase sha256 hex digest, as ``hashlib.sha256(...).hexdigest()`` spells it.
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class TokenUsage(BaseModel):
    """Model tokens one worker round consumed, when the runtime reports them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: int = Field(ge=0)
    output: int = Field(ge=0)
    cache_read: int | None = Field(default=None, ge=0)
    cache_write: int | None = Field(default=None, ge=0)
    reasoning: int | None = Field(default=None, ge=0)


class CheckItem(BaseModel):
    """One acceptance check the worker ran, keyed by its name in ``checks``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    value: str | float | int | None = None
    note: str | None = None


class Product(BaseModel):
    """One thing the worker produced, by workspace-relative path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    description: str = ""


class Deviation(BaseModel):
    """Where the worker departed from the brief's protocol, and how."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    actual: str = Field(min_length=1)


class CapabilityGap(BaseModel):
    """A MolCrafts capability the task needed and did not find.

    Attributes:
        component: Which tool lacks it.
        title: What is missing, in one line.
        repro: How to reproduce the gap (a command, a snippet, a path).
        version: The component version the gap was seen on.
        fix: The change that would close it, if the worker knows.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component: Component
    title: str = Field(min_length=1)
    repro: str = Field(min_length=1)
    version: str | None = None
    fix: str | None = None


class WorkerReportRecord(BaseModel):
    """What a worker reports back; stored on a Report as ``kind: worker_report``.

    Attributes:
        delegation: Workspace-relative path of the Delegation document.
        attempt: The attempt id on that Delegation this report settles.
        brief: Workspace-relative path of the Brief the worker was given.
        brief_digest: The brief's ``digest``, so a report cannot answer a
            brief it was not given.
        outcome: How the round ended.
        summary: The worker's own account, in prose.
        checks: Every acceptance check by name, with its verdict.
        products: What was produced.
        files_changed: Workspace-relative paths the worker changed.
        workflow: Path of the workflow the worker ran, if any.
        protocol_deviations: Each departure from the brief's protocol.
        capability_gaps: Each MolCrafts capability found missing.
        open_questions: What the worker could not settle.
        next: What the worker suggests doing next.
        tokens: Model tokens consumed, or ``"unavailable"``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["worker_report"]
    delegation: str = Field(min_length=1)
    attempt: str = Field(min_length=1)
    brief: str = Field(min_length=1)
    brief_digest: Digest
    outcome: Outcome
    summary: str = Field(min_length=1)
    checks: dict[str, CheckItem] = Field(default_factory=dict)
    products: tuple[Product, ...] = ()
    files_changed: tuple[str, ...] = ()
    workflow: str | None = None
    protocol_deviations: tuple[Deviation, ...] = ()
    capability_gaps: tuple[CapabilityGap, ...] = ()
    open_questions: tuple[str, ...] = ()
    next: str | None = None
    tokens: Literal["unavailable"] | TokenUsage = "unavailable"


class Protocol(BaseModel):
    """How the worker must do the work, fixed before it starts.

    Attributes:
        reproduce: An execution ref or path the worker reproduces exactly.
        realization: ``"independent"`` when the worker runs its own realization
            instead of reproducing one.
        seed: The random seed to use.
        stereo: The stereochemistry policy.
        charges: How charges are neutralized.
        notes: Anything else the protocol fixes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reproduce: str | None = None
    realization: Literal["independent"] | None = None
    seed: int | None = None
    stereo: str | None = None
    charges: str | None = None
    notes: str | None = None


class BriefRecord(BaseModel):
    """What a worker is dispatched with; stored on a Note as ``kind: brief``.

    Attributes:
        delegation: Workspace-relative path of the Delegation document.
        round: Which round of that delegation this brief opens (from 1).
        digest: sha256 hex of the brief's narrative, as written.
        inputs: Workspace-relative paths of the plan, answer and report
            documents the brief was compiled from.
        protocol: The protocol the worker is held to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["brief"]
    delegation: str = Field(min_length=1)
    round: int = Field(ge=1)
    digest: Digest
    inputs: tuple[str, ...] = ()
    protocol: Protocol


#: ``kind`` → the one document class a record of that kind is stored on.
WORKER_RECORD_CLASSES: Mapping[str, str] = MappingProxyType(
    {"worker_report": "Report", "brief": "Note"}
)

_MODELS: Mapping[str, type[WorkerReportRecord] | type[BriefRecord]] = MappingProxyType(
    {"worker_report": WorkerReportRecord, "brief": BriefRecord}
)


def parse_worker_report(raw: Mapping[str, object]) -> WorkerReportRecord:
    """Validate a ``worker_report`` record from a frontmatter mapping.

    The common document keys are ignored; any other unknown key is an error.

    Raises:
        ValueError: The fields do not form a valid record. The message names
            each offending field.
    """
    return _validate("worker_report", WorkerReportRecord, raw)


def parse_brief(raw: Mapping[str, object]) -> BriefRecord:
    """Validate a ``brief`` record from a frontmatter mapping.

    Raises:
        ValueError: The fields do not form a valid record. The message names
            each offending field.
    """
    return _validate("brief", BriefRecord, raw)


def _validate[RecordT: BaseModel](
    kind: str, model: type[RecordT], raw: Mapping[str, object]
) -> RecordT:
    payload = {key: value for key, value in raw.items() if key not in COMMON_KEYS}
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid {kind} record: {exc}") from exc


def check_worker_record(
    of: type,
    record: Mapping[str, object] | None,
    *,
    existing: Mapping[str, object] | None,
) -> None:
    """Reject a write whose resulting ``worker_report`` or ``brief`` record is invalid.

    Dispatches on ``kind`` — the incoming *record*'s, else the stored one's.
    A ``worker_report`` is valid only on a Report and a ``brief`` only on a
    Note; any other kind, or none, is not this module's and is left alone.
    *existing* is the stored frontmatter (``None`` on create). The incoming
    record is merged over it, as the write will, and the result validated.
    A rewrite that touches no field of the record (a narrative-only edit) is
    left alone.

    Raises:
        ValueError: The record is on the wrong class, or the merged record
            is invalid. The message names the field.
    """
    payload = dict(record or {})
    stored = dict(existing or {})
    kind = payload.get("kind", stored.get("kind"))
    if not isinstance(kind, str) or kind not in WORKER_RECORD_CLASSES:
        return
    owner = WORKER_RECORD_CLASSES[kind]
    if of.__name__ != owner:
        raise ValueError(f"a {kind} record belongs on a {owner}, not a {of.__name__}")
    model = _MODELS[kind]
    if existing is not None and not (set(payload) & set(model.model_fields)):
        return
    _validate(kind, model, {**stored, **payload})
