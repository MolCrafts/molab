"""Run-local host metrics: JSONL WAL under an attempt's ``artifacts/`` (``.mlp.jsonl``).

On-disk layout under a run / execution root (see
:mod:`molab.plugins.metrics.mlp_names`)::

    artifacts/<stem>.mlp.jsonl   # append-only WAL — the persist surface

Default writer stem is ``metrics`` → ``artifacts/metrics.mlp.jsonl``.
Leftover ``*.mlp.zarr/`` and ``*.mlp.index.json`` are ignored.

**Layering**

* Foreign dialects (event JSONL, CSV, LAMMPS log, TensorBoard, …) convert
  into this module's writer and land in the WAL via :class:`FileStore`.
* A molab Run is a workspace host (``run.json`` + run-root ``alive``), not a
  MolRec record. Filename gate ``*.mlp.jsonl`` is the host surface; the WAL
  is not catalogued as an :class:`~molab.workspace.domain.Artifact`.
* :meth:`MetricsWriter.flush` does not densify.

Wire API (``read_run_metrics``) returns compact event records so the UI and
``GET …/metrics`` stay stable. All reads accept an optional
:class:`~molab.workspace.fs.FileSystem` so remote workspaces use the same
code path as local ones (never bare ``pathlib`` against a remote root).
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

from molab._typing import JSONValue
from molab.plugins.metrics.mlp_names import (
    DEFAULT_MLP_STEM,
    MLP_JSONL_SUFFIX,
    is_mlp_jsonl,
    is_mlp_zarr,
    mlp_index_name,
    mlp_jsonl_name,
    mlp_zarr_name,
)
from molab.workspace.execution_dirs import ARTIFACTS, product_dirs
from molab.workspace.file_store import FileStore
from molab.workspace.fs import FileSystem
from molab.workspace.fs_local import LocalFileSystem

# Re-export naming constants so existing ``from metrics import …`` call sites
# and docs can cite one module. Prefer :mod:`mlp_names` for new code.
METRICS_STEM = DEFAULT_MLP_STEM
METRICS_JSONL_NAME = mlp_jsonl_name()
METRICS_ZARR_NAME = mlp_zarr_name()
METRICS_INDEX_NAME = mlp_index_name()

MetricRecord = dict[str, JSONValue]

_VALID_TYPES = {"scalar", "histogram", "text", "image_ref", "json"}

_Append = Callable[[str | Path, str], object]


@dataclass
class MetricReadResult:
    """Result returned by a metrics read query."""

    records: list[MetricRecord] = field(default_factory=list)
    next_line: int = 0
    series: list[dict[str, JSONValue]] = field(default_factory=list)
    parse_errors: int = 0


def _default_fs() -> FileSystem:
    return LocalFileSystem()


def _discover_named(
    run_dir: Path | str,
    *,
    fs: FileSystem,
    suffix: str,
    prefer_stem: str = DEFAULT_MLP_STEM,
    want_dir: bool = False,
) -> str | None:
    """Return absolute path of the preferred ``*<suffix>`` entry under *run_dir*."""
    root = str(run_dir)
    if not fs.exists(root):
        return None
    try:
        names = fs.listdir(root)
    except OSError:
        return None
    preferred = f"{prefer_stem}{suffix}"
    candidates: list[str] = []
    for name in names:
        if not name.lower().endswith(suffix.lower()):
            continue
        path = fs.join(root, name)
        try:
            ok = fs.is_dir(path) if want_dir else fs.is_file(path)
        except OSError:
            continue
        if ok:
            candidates.append(name)
    if not candidates:
        return None
    if preferred in candidates:
        return fs.join(root, preferred)
    return fs.join(root, sorted(candidates)[0])


def _metrics_roots(run_dir: Path | str, fs: FileSystem) -> list[str]:
    """Run root first, then each ``executions/<id>/`` (per-attempt metrics)."""
    root = str(run_dir)
    roots = [root]
    execs = fs.join(root, "executions")
    if fs.is_dir(execs):
        try:
            names = fs.listdir(execs)
        except OSError:
            names = []
        for name in sorted(names):
            path = fs.join(execs, name)
            if fs.is_dir(path):
                roots.append(path)
    return roots


def _discover_jsonl_in_root(root: str, *, fs: FileSystem) -> str | None:
    """Search every directory declared to hold products, then the root itself.

    Which directories those are is the declaration's answer, not a list
    written here — a tier added later is searched without touching this.
    """
    for directory in product_dirs():
        hit = _discover_named(
            fs.join(root, directory.name), fs=fs, suffix=MLP_JSONL_SUFFIX, want_dir=False
        )
        if hit is not None:
            return hit
    return _discover_named(root, fs=fs, suffix=MLP_JSONL_SUFFIX, want_dir=False)


def discover_mlp_jsonl(run_dir: Path | str, *, fs: FileSystem | None = None) -> str | None:
    """Locate a ``*.mlp.jsonl`` WAL under *run_dir* or its executions.

    At each root, a declared product directory wins over a same-level file.
    Later execution directories override earlier ones and the run root.
    """
    fs = fs or _default_fs()
    found: str | None = None
    for root in _metrics_roots(run_dir, fs):
        hit = _discover_jsonl_in_root(root, fs=fs)
        if hit is not None:
            found = hit
    return found


def has_metrics_wal(run_dir: Path | str, *, fs: FileSystem | None = None) -> bool:
    """True when a live ``*.mlp.jsonl`` WAL exists under *run_dir*."""
    return discover_mlp_jsonl(run_dir, fs=fs) is not None


def has_metrics(run_dir: Path | str, *, fs: FileSystem | None = None) -> bool:
    """True when a JSONL metrics WAL is present. Leftover zarr is ignored."""
    return has_metrics_wal(run_dir, fs=fs)


def _is_number(value: JSONValue) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_tags(tags: JSONValue) -> dict[str, JSONValue] | None:
    if tags is None:
        return None
    if not isinstance(tags, dict):
        raise ValueError("metric tags must be a dict")
    json.dumps(tags)
    return tags


def _validate_step(step: JSONValue) -> int | float | None:
    if step is None:
        return None
    if not _is_number(step):
        raise ValueError("metric step must be a finite number")
    assert isinstance(step, (int, float))
    return step


def _validate_key(key: JSONValue) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("metric key must be a non-empty string")
    return key


def validate_record(record: MetricRecord) -> MetricRecord:
    event_type = record.get("t")
    if event_type not in _VALID_TYPES:
        raise ValueError(f"unknown metric type: {event_type!r}")

    record["k"] = _validate_key(record.get("k"))
    if "s" in record:
        record["s"] = _validate_step(record["s"])
    if "tags" in record:
        record["tags"] = _validate_tags(record["tags"])

    value = record.get("v")
    if event_type == "scalar":
        if not _is_number(value):
            raise ValueError("scalar metric value must be a finite number")
    elif event_type == "histogram":
        if not isinstance(value, dict):
            raise ValueError("histogram metric value must be an object")
        bins = value.get("bins")
        counts = value.get("counts")
        if not isinstance(bins, list) or not all(_is_number(item) for item in bins):
            raise ValueError("histogram bins must be a number array")
        if not isinstance(counts, list) or not all(_is_number(item) for item in counts):
            raise ValueError("histogram counts must be a number array")
    elif event_type == "text":
        if not isinstance(value, str):
            raise ValueError("text metric value must be a string")
    elif event_type == "image_ref":
        if not isinstance(value, dict) or not isinstance(value.get("path"), str):
            raise ValueError("image_ref metric value must contain a path string")
    else:
        json.dumps(value)

    return record


def _summarize_records(records: list[MetricRecord]) -> list[dict[str, JSONValue]]:
    by_key: dict[str, dict[str, JSONValue]] = {}
    for record in records:
        key_raw = record["k"]
        if not isinstance(key_raw, str):
            continue
        summary = by_key.setdefault(
            key_raw,
            {
                "key": key_raw,
                "type": record["t"],
                "count": 0,
                "latestStep": None,
                "latestTimestamp": None,
                "latestValue": None,
            },
        )
        count = summary.get("count", 0)
        summary["count"] = (count if isinstance(count, int) else 0) + 1
        summary["type"] = record["t"]
        summary["latestStep"] = record.get("s")
        summary["latestTimestamp"] = record.get("w")
        if record["t"] == "scalar":
            summary["latestValue"] = record.get("v")
    return sorted(by_key.values(), key=lambda item: str(item.get("key", "")))


def _records_from_wal(
    run_dir: Path | str,
    *,
    fs: FileSystem,
    metric_type: str | None = None,
    key: str | None = None,
    since_line: int = 0,
    limit: int = 5000,
) -> MetricReadResult:
    wal = discover_mlp_jsonl(run_dir, fs=fs)
    if wal is None:
        return MetricReadResult()

    try:
        text = fs.read_text(wal, encoding="utf-8")
    except OSError:
        return MetricReadResult()

    records: list[MetricRecord] = []
    parse_errors = 0
    next_line = 0

    for line_no, line in enumerate(text.splitlines()):
        next_line = line_no + 1
        if line_no < since_line:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        try:
            record = validate_record(json.loads(stripped))
        except (json.JSONDecodeError, ValueError, TypeError):
            parse_errors += 1
            continue

        if metric_type is not None and record["t"] != metric_type:
            continue
        if key is not None and record["k"] != key:
            continue

        records.append(record)
        if len(records) >= limit:
            break

    return MetricReadResult(
        records=records,
        next_line=next_line,
        series=_summarize_records(records),
        parse_errors=parse_errors,
    )


def read_run_metrics(
    run_dir: Path | str,
    *,
    fs: FileSystem | None = None,
    metric_type: str | None = None,
    key: str | None = None,
    since_line: int = 0,
    limit: int = 5000,
) -> MetricReadResult:
    """Read metrics for the UI / API from the JSONL WAL.

    Pass *fs* (``workspace.fs``) so remote roots use the same code path as
    local ones. Leftover zarr / index files are not read.
    """
    fs = fs or _default_fs()
    return _records_from_wal(
        run_dir,
        fs=fs,
        metric_type=metric_type,
        key=key,
        since_line=since_line,
        limit=limit,
    )


def _file_store_append(run_dir: Path) -> _Append:
    store = FileStore(run_dir)

    def append(name: str | Path, line: str) -> object:
        return store.append(Path(ARTIFACTS.name) / name, line)

    return append


class MetricsWriter:
    """Append metrics to ``artifacts/metrics.mlp.jsonl`` via :class:`FileStore`.

    The versioned tier on purpose: the metrics WAL is small and is the
    record of what the run measured, so it belongs in the history.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        append: _Append | None = None,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._lock = threading.Lock()
        self._append = append if append is not None else _file_store_append(self._run_dir)

    @property
    def path(self) -> Path:
        """Where this writer appends. Readable as a format like any other, so
        a caller that also *reads* the run must exclude it from its sources."""
        return self._run_dir / ARTIFACTS.name / METRICS_JSONL_NAME

    def scalar(
        self,
        key: str,
        value: int | float,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self.log(
            {"t": "scalar", "k": key, "s": step, "w": _format_wall_time(wall_time), "v": value},
            tags=tags,
        )

    def histogram(
        self,
        key: str,
        bins: list[int | float],
        counts: list[int | float],
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self.log(
            cast(
                "MetricRecord",
                {
                    "t": "histogram",
                    "k": key,
                    "s": step,
                    "w": _format_wall_time(wall_time),
                    "v": {"bins": bins, "counts": counts},
                },
            ),
            tags=tags,
        )

    def text(
        self,
        key: str,
        text: str,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self.log(
            {"t": "text", "k": key, "s": step, "w": _format_wall_time(wall_time), "v": text},
            tags=tags,
        )

    def image_ref(
        self,
        key: str,
        path: str | Path,
        step: int | float | None = None,
        *,
        caption: str | None = None,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self.log(
            {
                "t": "image_ref",
                "k": key,
                "s": step,
                "w": _format_wall_time(wall_time),
                "v": {"path": str(path), "caption": caption},
            },
            tags=tags,
        )

    def json(
        self,
        key: str,
        value: JSONValue,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord:
        return self.log(
            {"t": "json", "k": key, "s": step, "w": _format_wall_time(wall_time), "v": value},
            tags=tags,
        )

    def log(
        self, record: MetricRecord, *, tags: dict[str, JSONValue] | None = None
    ) -> MetricRecord:
        payload: MetricRecord = {key: value for key, value in record.items() if value is not None}
        payload.setdefault("w", datetime.now().isoformat())
        if tags is not None:
            payload["tags"] = tags

        payload = validate_record(payload)
        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        with self._lock:
            self._append(mlp_jsonl_name(), line)

        return payload

    def log_many(
        self, records: Iterable[MetricRecord], *, tags: dict[str, JSONValue] | None = None
    ) -> int:
        """Append many records through :class:`FileStore`.

        Same per-record validation as :meth:`log`. Streams the input so memory
        stays flat.
        """
        count = 0
        with self._lock:
            for record in records:
                payload: MetricRecord = {
                    key: value for key, value in record.items() if value is not None
                }
                payload.setdefault("w", datetime.now().isoformat())
                if tags is not None:
                    payload["tags"] = tags
                payload = validate_record(payload)
                line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                self._append(mlp_jsonl_name(), line)
                count += 1
        return count

    def flush(self) -> None:
        """No-op: JSONL is the persist surface; there is no dense store."""


def _format_wall_time(wall_time: str | datetime | None) -> str:
    if isinstance(wall_time, datetime):
        return wall_time.isoformat()
    if isinstance(wall_time, str):
        return wall_time
    return datetime.now().isoformat()


__all__ = [
    "METRICS_INDEX_NAME",
    "METRICS_JSONL_NAME",
    "METRICS_STEM",
    "METRICS_ZARR_NAME",
    "MetricReadResult",
    "MetricRecord",
    "MetricsWriter",
    "discover_mlp_jsonl",
    "has_metrics",
    "has_metrics_wal",
    "is_mlp_jsonl",
    "is_mlp_zarr",
    "read_run_metrics",
]
