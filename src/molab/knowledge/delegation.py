"""The structured record a :class:`~molab.knowledge.concepts.Delegation` stores.

A delegation is one bounded, resumable piece of supervised work: the scope it
is bound to, the goal, the actions it may take on its own, its budget and what
it has spent, its acceptance and stop conditions, what it is waiting on, and
the worker attempts made so far. A supervising agent (Tack) reads and writes
it; molab only validates and stores it. The narrative is the human summary.

The record is the frontmatter of the document, minus the keys every document
carries (``class`` / ``name`` / ``created_by`` / ``tags`` / ``status``). A
document-level ``status`` is the lifecycle status shared with Note; the
delegation's own lifecycle is ``state``: ``open`` and ``waiting`` (on compute)
take steps, ``blocked`` waits on a person (its ``questions``), ``paused`` is
held by a person, ``done`` and ``stopped`` are final. ``amendments`` record
every change a person made to its terms; ``writes`` key the documents it wrote
so a retried write is not doubled. ``answers`` keep what a person answered
when it was blocked, ``approvals`` what a person approved at each human gate
(the parameters, the plan, a dry run, the results — each about one document
or entity), and ``last_decision`` the supervisor's latest decision document.
An attempt links the brief it was dispatched with and the report it came back
with (:mod:`molab.knowledge.worker_report`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .worker_report import Digest, TokenUsage

__all__ = [
    "DELEGATION_ACTIONS",
    "DELEGATION_FIELDS",
    "DelegationAmendment",
    "DelegationAnswer",
    "DelegationApproval",
    "DelegationAttempt",
    "DelegationBudget",
    "DelegationDecision",
    "DelegationRecord",
    "DelegationWait",
    "DelegationWrite",
    "check_delegation_record",
    "parse_delegation",
]

DelegationKind = Literal["research", "capability"]
DelegationState = Literal["open", "waiting", "blocked", "paused", "done", "stopped"]
WaitState = Literal["pending", "resolved", "expired"]
ApprovalGate = Literal["parameters", "plan", "dry_run", "results"]
DelegationAction = Literal[
    "read",
    "create_experiment",
    "create_run",
    "start_execution",
    "cancel_execution",
    "write_knowledge",
    "delegate_worker",
]

#: The closed set of actions a delegation may authorize.
DELEGATION_ACTIONS: frozenset[str] = frozenset(get_args(DelegationAction))


class DelegationBudget(BaseModel):
    """Limits (or amounts spent). ``None`` on a limit means unlimited."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_usd: float | None = Field(default=None, ge=0)
    worker_runs: int | None = Field(default=None, ge=0)
    executions: int | None = Field(default=None, ge=0)
    wall_hours: float | None = Field(default=None, ge=0)


class DelegationWait(BaseModel):
    """One thing the delegation waits on before its next step.

    Attributes:
        id: Stable id within this delegation.
        target: The ``molab:`` ref waited on (a run or an execution).
        project: The project id the target lives under (a ``molab:`` run ref
            names its experiment, not its project).
        kind: What is awaited. Only ``execution`` (an attempt reaching a
            terminal status) today.
        request_key: The idempotency key the attempt was requested with, so a
            lost submit response is found again instead of resubmitted.
        on_resolve: What the supervisor intends to do once it resolves.
        next_check_at: ISO-8601 time of the next check, if scheduled.
        deadline: ISO-8601 time after which the wait expires.
        state: ``pending``, ``resolved`` or ``expired``.
        outcome: The observed terminal status once resolved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    project: str | None = None
    kind: Literal["execution"] = "execution"
    request_key: str | None = None
    on_resolve: str = ""
    next_check_at: str | None = None
    deadline: str | None = None
    state: WaitState = "pending"
    outcome: str | None = None


class DelegationAttempt(BaseModel):
    """One worker attempt and what it cost.

    Attributes:
        brief: Workspace-relative path of the ``brief`` Note it was given.
        brief_digest: That brief's digest, as dispatched.
        report: Workspace-relative path of the ``worker_report`` Report it
            came back with, once linked.
        tokens: Model tokens it consumed; ``"unavailable"`` when the runtime
            does not report them; ``None`` until settled.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    worker: str = Field(min_length=1)
    task: str = ""
    status: str = ""
    summary: str = ""
    cost_usd: float | None = Field(default=None, ge=0)
    turns: int | None = Field(default=None, ge=0)
    files_changed: tuple[str, ...] = ()
    check: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    brief: str | None = None
    brief_digest: Digest | None = None
    report: str | None = None
    tokens: Literal["unavailable"] | TokenUsage | None = None


class DelegationDecision(BaseModel):
    """The supervisor's latest decision document and what it decided.

    Attributes:
        path: Workspace-relative path of the decision document.
        kind: The decision's kind, as the supervisor names it.
        next: What it decided to do next, if anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    next: str | None = None


class DelegationAnswer(BaseModel):
    """What a person answered when the delegation was blocked on a question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    by: str = Field(min_length=1)
    text: str = Field(min_length=1)


class DelegationApproval(BaseModel):
    """What a person approved at one human gate.

    Attributes:
        gate: Which gate: ``parameters``, ``plan``, ``dry_run`` or ``results``.
        target: What the approval is about — a workspace-relative knowledge or
            experiment path, or a ``molab:`` ref.
        by: Who approved.
        at: ISO-8601 time of the approval.
        note: What the person said, if anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: ApprovalGate
    target: str = Field(min_length=1)
    by: str = Field(min_length=1)
    at: str = Field(min_length=1)
    note: str | None = None


class DelegationAmendment(BaseModel):
    """One recorded change to a delegation's terms, made by a person.

    Attributes:
        at: ISO-8601 time of the change.
        by: Who made it.
        reason: Why.
        changes: The fields changed, as ``{field: new value}``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: str = Field(min_length=1)
    by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    changes: dict[str, object] = Field(default_factory=dict)


class DelegationWrite(BaseModel):
    """A knowledge document this delegation wrote, keyed by its content.

    A retried write with the same key returns the recorded document instead
    of writing a second one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    path: str = Field(min_length=1)


class DelegationRecord(BaseModel):
    """Everything a Delegation stores beyond the common document keys."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DelegationKind = "research"
    goal: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    actions: tuple[DelegationAction, ...] = ("read",)
    budget: DelegationBudget = DelegationBudget()
    spent: DelegationBudget = DelegationBudget(
        worker_usd=0, worker_runs=0, executions=0, wall_hours=0
    )
    acceptance: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    state: DelegationState = "open"
    waits: tuple[DelegationWait, ...] = ()
    attempts: tuple[DelegationAttempt, ...] = ()
    supervisor: dict[str, str] = Field(default_factory=dict)
    current_plan: str | None = None
    questions: tuple[str, ...] = ()
    amendments: tuple[DelegationAmendment, ...] = ()
    writes: tuple[DelegationWrite, ...] = ()
    last_decision: DelegationDecision | None = None
    answers: tuple[DelegationAnswer, ...] = ()
    approvals: tuple[DelegationApproval, ...] = ()

    @model_validator(mode="after")
    def _ids_unique(self) -> DelegationRecord:
        for label, rows in (("wait", self.waits), ("attempt", self.attempts)):
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"delegation {label} ids repeat: {ids}")
        return self


#: The frontmatter keys a Delegation owns.
DELEGATION_FIELDS: frozenset[str] = frozenset(DelegationRecord.model_fields)


def parse_delegation(raw: Mapping[str, object]) -> DelegationRecord:
    """Validate the delegation fields of a frontmatter mapping.

    Keys outside :data:`DELEGATION_FIELDS` (``class``, ``name``, ``tags`` …)
    are ignored.

    Raises:
        ValueError: The fields do not form a valid record.
    """
    payload = {key: value for key, value in raw.items() if key in DELEGATION_FIELDS}
    try:
        return DelegationRecord.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid Delegation record: {exc}") from exc


def check_delegation_record(
    record: Mapping[str, object] | None,
    *,
    existing: Mapping[str, object] | None,
) -> None:
    """Reject a Delegation write whose resulting record is invalid.

    *existing* is the stored frontmatter (``None`` on create). The incoming
    *record* is merged over it, as the write will, and the result validated.
    A create must carry ``goal`` and ``scope``. A rewrite that touches no
    delegation field (a narrative-only edit) is left alone.

    Raises:
        ValueError: The merged record is invalid, or a create misses goal/scope.
    """
    payload = dict(record or {})
    if existing is not None and not (set(payload) & DELEGATION_FIELDS):
        return
    if existing is None and ("goal" not in payload or "scope" not in payload):
        raise ValueError("a Delegation stores its goal and its scope")
    parse_delegation({**dict(existing or {}), **payload})
