"""Measure a Milestone's checks from the files runs registered.

A :class:`~molab.knowledge.concepts.Milestone` that declares ``checks`` does
not take its status from whoever writes it. :func:`evaluate_milestone` reads
each check's span from a registered asset, records the value with the asset's
ref and content digest, and sets ``met`` / ``missed`` / ``open`` from the
arithmetic. The bytes it accepts are a run's own: registered by an attempt
molab ran itself, in a run that molab ran to success, and not swapped since by
``asset replace``. An imported file, an adopted attempt's file and the file
of a run that never succeeded measure nothing.

:func:`evidence_problems` asks the same of a document on disk, so
``molab validate`` reports a measurement typed by hand, and one whose asset
was replaced after it was read.

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from .concepts import (
    Milestone,
    MilestoneCheck,
    MilestoneFields,
    MilestoneMeasurement,
    settled_status,
)
from .fields import digest_of, own_fields, replace_fields
from .frontmatter import append_markdown
from .knowledge_item import SourceRef

if TYPE_CHECKING:
    from molab.workspace import Workspace
    from molab.workspace.domain import Asset
    from molab.workspace.refs import MolabRef

__all__ = ["AcceptanceError", "evaluate_milestone", "evidence_problems"]


class AcceptanceError(ValueError):
    """A check that cannot be measured from the source it was given."""


#: The spans a link target can carry as a fragment without breaking the link.
_LINKABLE_SPAN: Final = re.compile(r"[A-Za-z0-9_./@~-]+")


def evaluate_milestone(doc: Milestone, measures: Mapping[str, str]) -> MilestoneFields:
    """Measure checks of *doc* and write its status from the result.

    Each entry of *measures* names a check id and the ``molab:asset/<id>``
    that holds its value. A check measured before and named again is measured
    anew; one not named keeps its earlier measurement. A status typed by hand
    that the measurements do not carry is replaced. The narrative is kept,
    and gains one ``derived_from`` link per measured asset, at the check's span.

    Args:
        doc: An existing Milestone that declares checks.
        measures: Check id -> asset reference.

    Returns:
        The fields as written.

    Raises:
        AcceptanceError: *doc* declares no checks, an id names no check, or a
            source is not a run's own registered file with a finite number at
            the check's span.
        DigestConflictError: *doc* changed while it was being measured.
        FileNotFoundError: *doc* does not exist.
    """
    read = digest_of(doc)
    fields = _declared(doc)
    checks = {check.id: check for check in fields.checks}
    if not checks:
        raise AcceptanceError(f"{doc.name} declares no checks; its status is judged by reading")
    for check_id in measures:
        if check_id not in checks:
            raise AcceptanceError(f"{doc.name} declares no check {check_id!r}")
    workspace = _workspace_of(doc)
    fresh = {
        check_id: _measure(workspace, checks[check_id], ref) for check_id, ref in measures.items()
    }
    earlier = {item.check: item for item in fields.measurements}
    measurements = tuple(
        found
        for check in fields.checks
        if (found := fresh.get(check.id, earlier.get(check.id))) is not None
    )
    evaluated = fields.model_copy(
        update={
            "measurements": measurements,
            "status": settled_status(fields.checks, measurements),
        }
    )
    replaced = [earlier[check_id] for check_id in fresh if check_id in earlier]
    body = _relinked(doc, checks, drop=replaced, add=list(fresh.values()))
    replace_fields(
        doc, evaluated.model_dump(mode="json", exclude_none=True), body=body, if_match=read
    )
    return evaluated


def evidence_problems(doc: Milestone) -> list[str]:
    """Why *doc*'s measurements do not rest on the bytes they cite; ``[]`` when they do.

    Each measurement is read again: its asset must still be its run's own,
    hold the digest that was recorded, and hold the recorded value at the
    check's span.
    """
    fields = doc.fields()
    if not fields.measurements:
        return []
    checks = {check.id: check for check in fields.checks}
    try:
        workspace = _workspace_of(doc)
    except AcceptanceError as exc:
        return [str(exc)]
    problems: list[str] = []
    for item in fields.measurements:
        try:
            found = _measure(workspace, checks[item.check], item.ref)
        except AcceptanceError as exc:
            problems.append(f"check {item.check!r}: {exc}")
            continue
        if found.digest != item.digest:
            problems.append(f"check {item.check!r}: {item.ref} changed since it was measured")
        elif found.value != item.value:
            problems.append(
                f"check {item.check!r}: records {item.value}, but {item.ref} holds {found.value}"
            )
    return problems


def _declared(doc: Milestone) -> MilestoneFields:
    """*doc*'s fields; a status that disagrees with its measurements is read as unset."""
    try:
        return doc.fields()
    except ValueError as refused:
        stored = own_fields(doc.frontmatter())
        stored.pop("status", None)
        try:
            return MilestoneFields.model_validate(stored)
        except ValueError:
            raise AcceptanceError(
                f"{doc.name} holds fields its class refuses: {refused}"
            ) from refused


def _workspace_of(doc: Milestone) -> Workspace:
    from molab.workspace import Workspace

    from .location import enclosing_workspace_root

    root = enclosing_workspace_root(doc.path, fs=doc.fs)
    if root is None:
        raise AcceptanceError(f"{doc.path} is not inside a workspace")
    return Workspace(root, fs=doc.fs)


def _measure(workspace: Workspace, check: MilestoneCheck, ref: str) -> MilestoneMeasurement:
    """Read *check*'s span from the asset *ref* names."""
    from .harvest import _document_at, _value_at

    asset = _produced_asset(workspace, ref)
    try:
        payload = workspace.assets_at(asset.scope).payload_path(asset.id)
    except (KeyError, ValueError, OSError) as exc:
        raise AcceptanceError(f"the bytes of {ref} cannot be read: {exc}") from exc
    body = _document_at(workspace.fs, payload)
    if body is None:
        raise AcceptanceError(f"{ref} is not a JSON file a value can be read from")
    try:
        value = _value_at(body, check.span)
    except ValueError as exc:
        raise AcceptanceError(f"{ref}: {exc}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AcceptanceError(f"{ref}#{check.span} holds {value!r}, which is not a number")
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number):
        raise AcceptanceError(f"{ref}#{check.span} holds {value!r}, which is not a finite number")
    return MilestoneMeasurement(
        check=check.id,
        ref=ref,
        digest=asset.content.digest,
        value=number,
        passed=check.passes(number),
    )


def _produced_asset(workspace: Workspace, ref: str) -> Asset:
    """The asset *ref* names, when its bytes are a run's own.

    The producing attempt is one molab ran, its run has an attempt molab ran
    to success, and nothing replaced the bytes since. The producing attempt
    itself need not have succeeded: a resumed run keeps what the failed
    attempt registered, and a later attempt that registers the same bytes
    becomes their producer whether or not it then fails.
    """
    from molab.workspace.domain import Asset, ExecutionOrigin, ExecutionStatus
    from molab.workspace.refs import InvalidRefError, MolabRef, parse_ref

    try:
        parsed = parse_ref(ref)
    except InvalidRefError as exc:
        raise AcceptanceError(f"{ref!r} is not an asset reference") from exc
    if parsed.kind != "asset":
        raise AcceptanceError(f"{ref!r} is not an asset reference")
    asset = _found(workspace, parsed, f"{ref} names no asset in this workspace")
    assert isinstance(asset, Asset)
    origin = asset.origin
    if not isinstance(origin, ExecutionOrigin):
        raise AcceptanceError(f"no attempt produced {ref}: it was imported")
    if asset.replaced_at is not None:
        raise AcceptanceError(
            f"{ref} holds bytes `molab asset replace` put there, not the ones its attempt produced"
        )
    run_ref = MolabRef(experiment_id=origin.experiment_id, run_id=origin.run_id)
    produced_by = MolabRef(
        experiment_id=origin.experiment_id,
        run_id=origin.run_id,
        execution_id=origin.execution_id,
    )
    run = _found(workspace, run_ref, f"{ref} names {run_ref}, which does not exist")
    try:
        attempts = list(getattr(run, "executions", ()))
    except (RuntimeError, ValueError, OSError) as exc:
        raise AcceptanceError(f"the attempts behind {ref} cannot be read: {exc}") from exc
    producer = next((item for item in attempts if item.id == origin.execution_id), None)
    if producer is None:
        raise AcceptanceError(f"{ref} names {produced_by}, which does not exist")
    if not producer.observed:
        raise AcceptanceError(
            f"{ref} comes from {produced_by}, which molab did not run: it was adopted"
        )
    if not any(
        item.status == ExecutionStatus.SUCCEEDED and item.sealed and item.observed
        for item in attempts
    ):
        raise AcceptanceError(
            f"{ref} comes from {produced_by}, which is {producer.status.value}, and no attempt "
            "of its run that molab ran has succeeded"
        )
    return asset


def _found(workspace: Workspace, ref: MolabRef, missing: str) -> object:
    """What *ref* names in *workspace*; every way it cannot be had is an ``AcceptanceError``."""
    from molab.workspace.errors import RefNotFoundError

    try:
        return workspace.find(ref)
    except RefNotFoundError as exc:
        raise AcceptanceError(missing) from exc
    except (LookupError, RuntimeError, ValueError, OSError) as exc:
        # An id in two scopes, an unmigrated store, a record that does not read.
        raise AcceptanceError(f"{ref} cannot be resolved: {exc}") from exc


def _relinked(
    doc: Milestone,
    checks: Mapping[str, MilestoneCheck],
    *,
    drop: list[MilestoneMeasurement],
    add: list[MilestoneMeasurement],
) -> str:
    """*doc*'s narrative with the links of *drop* removed and those of *add* present once."""
    base = str(doc.path.parent)

    def line(item: MilestoneMeasurement) -> str:
        span = checks[item.check].span
        # A span with a space or a bracket would cut the link short: cite the asset alone.
        linkable = span if _LINKABLE_SPAN.fullmatch(span) else None
        return SourceRef(kind="asset", ref=item.ref, span=linkable).link_line(base)

    wanted = list(dict.fromkeys(line(item) for item in add))
    stale = {line(item) for item in drop} - set(wanted)
    kept = [text for text in doc.read().splitlines() if text not in stale]
    body = "\n".join(kept) + "\n"
    missing = [text for text in wanted if text not in kept]
    if not missing:
        return body
    return append_markdown(body, "\n".join(missing) + "\n", path=doc.path)
