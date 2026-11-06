"""Turn a finished Run's outcome into typed knowledge.

The explicit execution→knowledge verb for plain runs: a researcher harvests
a terminal run into a source-attributed Knowledge document mounted under the
run's experiment.

Harvesting is **interpretation, not archival**: the run's raw record already
lives in the run record, so a harvest without a narrative is refused —
knowledge is what the numbers *mean*. Preconditions error, never fall back:

* the run must be terminal (``succeeded`` / ``failed`` / ``cancelled`` /
  ``interrupted``) — a live run has no outcome to interpret yet;
* ``narrative`` must be non-empty.

The prose is the narrative. The writer appends one source link per citation.
Status, parameters, errors and result values stay on the run and on the
assets it registered. Each asset the latest
attempt registered is a source. A ``results`` entry must sit at one point in
those files, cited as :attr:`SourceRef.span`: ``/loss`` for a JSON field,
``loss@10000`` for the series value at step 10000. A result with no registered
asset, or one that matches nothing or more than one point, is refused.
The document's ``inputs`` are the cited asset ids for the next ``add_run``.
``read_cited`` reads the value at a span. The workflow does not import
knowledge; the caller passes those ids in.

A ``Run`` is a legitimate argument here: ``molab.knowledge`` depends on
``molab.workspace``, and every such import is confined to a function body so
the package import stays acyclic.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from molab.ids import slugify

from .concept import Knowledge
from .knowledge_item import SourceRef

if TYPE_CHECKING:
    from molab._typing import JSONValue
    from molab.fs import FileSystem
    from molab.workspace.domain import Asset
    from molab.workspace.run import Run

__all__ = ["perform"]

_MISSING = object()


def perform(
    kind: type[Knowledge],
    run: Run,
    *,
    narrative: str,
    created_by: str,
    results: dict[str, JSONValue] | None = None,
    name: str | None = None,
) -> Knowledge:
    """Harvest a terminal *run* into *kind* under its experiment.

    Called by :meth:`Finding.harvest`, :meth:`Observation.harvest`, and
    :meth:`Report.harvest`.

    Raises:
        ValueError: If *run* is not terminal, *narrative* is blank, or a
            result does not match exactly one point in a registered asset.
            A result with no registered asset is refused: the value is not
            copied into the document.
    """
    from molab.workspace.run import TERMINAL_STATUSES

    status = run.status_label
    if status not in TERMINAL_STATUSES:
        raise ValueError(
            f"run {run.id} is {status!r} — only a terminal run "
            f"({sorted(TERMINAL_STATUSES)}) has an outcome to harvest"
        )
    if not narrative.strip():
        raise ValueError(
            "harvest requires a non-empty narrative — knowledge is interpretation; "
            "the raw record already lives in the run record"
        )

    experiment = run.experiment
    item_name = name or f"{slugify(kind.__name__)}-{run.id}"
    sources = [SourceRef.of(run), SourceRef.of(experiment)]
    sources.extend(_asset_sources(run, results))
    return kind.create(
        experiment,
        item_name,
        sources=sources,
        created_by=created_by,
        text=narrative.strip() + "\n",  # source links are appended by the writer
    )


def _asset_sources(run: Run, results: dict[str, JSONValue] | None) -> list[SourceRef]:
    """One source per cited point, then any registered asset the results skip.

    A result is a point in a registered asset. With no asset to pin it on,
    the value would have nowhere to live, so the call is refused.
    """
    assets = _produced_assets(run)
    if not results:
        return [SourceRef.of(asset) for asset in assets]
    if not assets:
        key = next(iter(results))
        raise ValueError(f"result {key!r} must match one point in the assets this run registered")
    pinned = _pin(run, assets, results)
    pinned_ids = {asset.id for asset, _span in pinned}
    sources = [SourceRef.of(asset, span=span) for asset, span in pinned]
    sources.extend(SourceRef.of(asset) for asset in assets if asset.id not in pinned_ids)
    return sources


def _pin(run: Run, assets: list[Asset], results: dict[str, JSONValue]) -> list[tuple[Asset, str]]:
    """Locate each result at one point. Refuse a miss or an ambiguous hit."""
    from molab.workspace.asset_repository import payload_path_for

    workspace = run.experiment.project.workspace
    parsed: list[tuple[Asset, object | None]] = []
    for asset in assets:
        path = payload_path_for(workspace, asset.id)
        parsed.append((asset, _document_at(workspace.fs, path)))
    located: list[tuple[Asset, str]] = []
    for key, value in results.items():
        hits: list[tuple[Asset, str]] = []
        for asset, body in parsed:
            if body is None:
                continue
            spans = _locations(body, key, value)
            if len(spans) > 1:
                raise ValueError(f"result {key!r} matches more than one point in {asset.ref}")
            if len(spans) == 1:
                hits.append((asset, spans[0]))
        if not hits:
            raise ValueError(
                f"result {key!r} must match one point in the assets this run registered"
            )
        if len(hits) > 1:
            raise ValueError(f"result {key!r} matches more than one asset")
        located.append(hits[0])
    return located


def _produced_assets(run: Run) -> list[Asset]:
    """Assets the latest attempt of *run* registered.

    Attempt ids are run-local, so a sibling run's ``e01`` is not this run's.
    """
    from molab.workspace.asset_repository import assets_produced_by
    from molab.workspace.domain import ExecutionOrigin

    executions = run.executions
    if not executions:
        return []
    workspace = run.experiment.project.workspace
    execution_id = executions[-1].id
    return [
        asset
        for asset in assets_produced_by(workspace, execution_id)
        if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
    ]


def _document_at(fs: FileSystem, path: str) -> object | None:
    try:
        text = fs.read_text(path)
    except (UnicodeDecodeError, OSError, ValueError):
        return None
    return _parse(text)


def _parse(text: str) -> object | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    rows: list[object] = []
    for line in text.splitlines():
        piece = line.strip()
        if not piece:
            continue
        try:
            rows.append(json.loads(piece))
        except json.JSONDecodeError:
            return None
    return rows or None


def _locations(body: object, key: str, value: object) -> list[str]:
    found: list[str] = []
    if isinstance(body, dict):
        held = body.get(key, _MISSING)
        if held is not _MISSING and _same(held, value):
            found.append(_pointer(key))
        if isinstance(held, list):
            found.extend(_series_spans(key, held, value))
    if isinstance(body, list):
        found.extend(_record_spans(body, key, value))
    return _unique(found)


def _series_spans(key: str, points: list[object], value: object) -> list[str]:
    spans: list[str] = []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            continue
        point_value = point["value"] if "value" in point else point.get("v", _MISSING)
        if point_value is _MISSING or not _same(point_value, value):
            continue
        step = point["step"] if "step" in point else point.get("s", _MISSING)
        if _is_step(step) and _series_key_ok(key):
            spans.append(f"{key}@{_step_token(step)}")
        else:
            field = "value" if "value" in point else "v"
            spans.append(f"{_pointer(key)}/{index}/{_escape(field)}")
    return spans


def _record_spans(rows: list[object], key: str, value: object) -> list[str]:
    spans: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_key = row.get("k", row.get("key"))
        if row_key != key:
            continue
        row_value = row["v"] if "v" in row else row.get("value", _MISSING)
        if row_value is _MISSING or not _same(row_value, value):
            continue
        step = row["s"] if "s" in row else row.get("step", _MISSING)
        if _is_step(step) and _series_key_ok(key):
            spans.append(f"{key}@{_step_token(step)}")
        else:
            field = "v" if "v" in row else "value"
            spans.append(f"/{index}/{_escape(field)}")
    return spans


def _value_at(body: object, span: str) -> JSONValue:
    if span.startswith("/"):
        return _read_pointer(body, span)
    key, sep, step_text = span.rpartition("@")
    if not sep or not key:
        raise ValueError(f"span {span!r} is not a JSON pointer or a series point")
    try:
        step = json.loads(step_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"span {span!r} has no step") from exc
    found = _series_values(body, key, step)
    if len(found) != 1:
        raise ValueError(f"span {span!r} is not one point in the asset")
    return found[0]


def _series_values(body: object, key: str, step: object) -> list[JSONValue]:
    found: list[JSONValue] = []
    if isinstance(body, dict):
        held = body.get(key)
        if isinstance(held, list):
            for point in held:
                if not isinstance(point, dict):
                    continue
                point_step = point["step"] if "step" in point else point.get("s", _MISSING)
                if not _same(point_step, step):
                    continue
                point_value = point["value"] if "value" in point else point.get("v", _MISSING)
                if point_value is not _MISSING:
                    found.append(cast("JSONValue", point_value))
    if isinstance(body, list):
        for row in body:
            if not isinstance(row, dict):
                continue
            row_key = row.get("k", row.get("key"))
            row_step = row["s"] if "s" in row else row.get("step", _MISSING)
            if row_key == key and _same(row_step, step):
                row_value = row["v"] if "v" in row else row.get("value", _MISSING)
                if row_value is not _MISSING:
                    found.append(cast("JSONValue", row_value))
    return found


def _read_pointer(body: object, pointer: str) -> JSONValue:
    if not pointer.startswith("/"):
        raise ValueError(f"span {pointer!r} is not a JSON pointer")
    current: object = body
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"span {pointer!r} is not in the asset")
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"span {pointer!r} is not in the asset") from exc
        else:
            raise ValueError(f"span {pointer!r} is not in the asset")
    return cast("JSONValue", current)


def _pointer(key: str) -> str:
    return "/" + _escape(key)


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _series_key_ok(key: str) -> bool:
    return "#" not in key and "@" not in key


def _is_step(step: object) -> bool:
    return isinstance(step, (int, float)) and not isinstance(step, bool)


def _step_token(step: object) -> str:
    return json.dumps(step)


def _same(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    return left == right


def _unique(items: list[str]) -> list[str]:
    found: list[str] = []
    for item in items:
        if item not in found:
            found.append(item)
    return found
