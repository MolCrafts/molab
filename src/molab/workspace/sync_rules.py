"""Per-path sync rules for one remote mirror.

Rules live in ``<mirror_root>/sync-rules.json``, beside the file mirror.
They are an operator preference for this machine, not workspace git.
The form speaks in workspace language; :func:`transfer_plan` is the only
place those choices become rsync include, exclude, and delete arguments.
"""

from __future__ import annotations

import json
import posixpath
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from molab.atomicio import atomic_write_json
from molab.ids import generate_uuid7

RULES_FILENAME = "sync-rules.json"
MIN_INTERVAL_MINUTES = 5
DEFAULT_INTERVAL_MINUTES = 15
_MAX_INTERVAL_MINUTES = 24 * 60 * 366
_OUTPUT_LIMIT = 240
_PREVIEW_LIMIT = 64_000

_KINDS = ("file", "directory")
_DIRECTIONS = ("pull", "push")
_CONTENTS = ("everything", "records", "code", "skip-bulk", "types")
_EXTRAS = ("keep", "remove")
_WHENS = ("manual", "on-open", "interval")
_TYPE_ORDER = ("py", "json", "md", "images", "logs")
_DESCEND = "*/"
_RECORDS = ("*.json", "*.md", "*.txt", "*.yaml", "*.yml")
_CODE = ("*.py", "workflow.ir.json")
_BULK = (
    "out/",
    "checkpoints/",
    "*.dcd",
    "*.xtc",
    "*.trr",
    "*.nc",
    "*.h5",
    "*.hdf5",
    "*.lammpstrj",
    "*.dump",
)
_TYPE_GLOBS: dict[str, tuple[str, ...]] = {
    "py": ("*.py",),
    "json": ("*.json",),
    "md": ("*.md",),
    "images": ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg"),
    "logs": ("*.log", "*.out", "*.err"),
}

_locks_guard = threading.Lock()
_file_locks: dict[str, threading.Lock] = {}
_held_guard = threading.Lock()
_held: set[str] = set()


class SyncRulesError(Exception):
    """The rules file on disk cannot be read."""


class SyncBusyError(Exception):
    """A transfer for this mirror is already running."""


class SyncFailedError(Exception):
    """The transfer ran and failed. A real run records that on the rule."""


@dataclass(frozen=True)
class SyncRule:
    """One saved sync for a path relative to the opened root."""

    id: str
    path: str
    kind: str
    direction: str
    content: str
    types: tuple[str, ...]
    extra_files: str
    when: str
    interval_minutes: int
    last_run_at: str | None = None
    last_status: str | None = None
    last_output: str | None = None


@dataclass(frozen=True)
class TransferPlan:
    """rsync arguments for one rule. The UI never sees this."""

    include: tuple[str, ...]
    exclude: tuple[str, ...]
    delete: bool
    recursive: bool


@dataclass(frozen=True)
class SyncRun:
    """Result of one preview or one real transfer."""

    rule: SyncRule
    output: str
    dry_run: bool


class SyncFilesystem(Protocol):
    """Cached remote filesystem a rule runs against."""

    @property
    def mirror_root(self) -> Path: ...

    def rsync(
        self,
        remote_root: str,
        *,
        direction: str,
        include: Sequence[str] = ...,
        exclude: Sequence[str] = ...,
        delete: bool = ...,
        dry_run: bool = ...,
        recursive: bool = ...,
    ) -> object: ...


def rules_path(mirror_root: Path | str) -> Path:
    """Path of the rules file for this mirror."""
    return Path(mirror_root) / RULES_FILENAME


def load_rules(mirror_root: Path | str) -> list[SyncRule]:
    """Return the saved rules. A missing file is an empty list."""
    with _locked(mirror_root):
        return _read(mirror_root)


def upsert_rule(
    mirror_root: Path | str,
    *,
    path: str,
    kind: str,
    direction: str = "pull",
    content: str = "everything",
    types: tuple[str, ...] | list[str] = (),
    extra_files: str = "keep",
    when: str = "manual",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
) -> SyncRule:
    """Insert or replace the single rule for *path*. Last-run fields stay."""
    draft = make_rule(
        path=path,
        kind=kind,
        direction=direction,
        content=content,
        types=types,
        extra_files=extra_files,
        when=when,
        interval_minutes=interval_minutes,
    )
    with _locked(mirror_root):
        rules = _read(mirror_root)
        kept: SyncRule | None = None
        rest: list[SyncRule] = []
        for rule in rules:
            if rule.path == draft.path:
                kept = rule
            else:
                rest.append(rule)
        saved = (
            draft
            if kept is None
            else replace(
                draft,
                id=kept.id,
                last_run_at=kept.last_run_at,
                last_status=kept.last_status,
                last_output=kept.last_output,
            )
        )
        _write(mirror_root, [*rest, saved])
        return saved


def delete_rule(mirror_root: Path | str, rule_id: str) -> None:
    """Remove one rule. Missing ids raise ``KeyError``."""
    with _locked(mirror_root):
        rules = _read(mirror_root)
        kept = [rule for rule in rules if rule.id != rule_id]
        if len(kept) == len(rules):
            raise KeyError(rule_id)
        _write(mirror_root, kept)


def get_rule(mirror_root: Path | str, rule_id: str) -> SyncRule:
    """Return one rule. Missing ids raise ``KeyError``."""
    for rule in load_rules(mirror_root):
        if rule.id == rule_id:
            return rule
    raise KeyError(rule_id)


def make_rule(
    *,
    path: str,
    kind: str,
    direction: str,
    content: str,
    types: tuple[str, ...] | list[str],
    extra_files: str,
    when: str,
    interval_minutes: int,
    id: str | None = None,
    last_run_at: str | None = None,
    last_status: str | None = None,
    last_output: str | None = None,
) -> SyncRule:
    """Validate one rule. A file syncs that file only."""
    kind = _choice(kind, _KINDS, "kind")
    direction = _choice(direction, _DIRECTIONS, "direction")
    content = _choice(content, _CONTENTS, "content")
    extra_files = _choice(extra_files, _EXTRAS, "extra files")
    when = _choice(when, _WHENS, "when")
    relative = normalize_relative(path)
    if kind == "file":
        content = "everything"
        chosen: tuple[str, ...] = ()
        extra_files = "keep"
    elif content == "types":
        chosen = _canonical_types(types)
        if not chosen:
            raise ValueError("select at least one file type")
    else:
        chosen = ()
    minutes = _interval_minutes(interval_minutes, when=when)
    return SyncRule(
        id=id or generate_uuid7(),
        path=relative,
        kind=kind,
        direction=direction,
        content=content,
        types=chosen,
        extra_files=extra_files,
        when=when,
        interval_minutes=minutes,
        last_run_at=last_run_at,
        last_status=last_status,
        last_output=last_output,
    )


def transfer_plan(rule: SyncRule) -> TransferPlan:
    """Translate one rule into rsync arguments.

    A file is one non-recursive copy. A folder preset that names types
    includes ``*/`` first so rsync can walk into directories, then excludes
    everything else. Remove maps to ``--delete`` for folders only.
    """
    if rule.kind == "file":
        return TransferPlan((), (), False, False)
    delete = rule.extra_files == "remove"
    if rule.content == "everything":
        return TransferPlan((), (), delete, True)
    if rule.content == "records":
        return TransferPlan((_DESCEND, *_RECORDS), ("*",), delete, True)
    if rule.content == "code":
        return TransferPlan((_DESCEND, *_CODE), ("*",), delete, True)
    if rule.content == "skip-bulk":
        return TransferPlan((), _BULK, delete, True)
    if rule.content == "types":
        globs = _globs(rule.types)
        if not globs:
            raise ValueError("select at least one file type")
        return TransferPlan((_DESCEND, *globs), ("*",), delete, True)
    raise ValueError(f"content must be one of: {', '.join(_CONTENTS)}")


def relativize(root: str, path: str) -> str:
    """Return *path* relative to *root*.

    *path* may already be relative. An absolute path must stay inside
    *root*. ``..`` segments, backslashes, and NUL bytes are rejected.
    """
    _reject_unsafe(path)
    raw = path.strip()
    if raw.startswith("/"):
        return _relative_absolute(root, raw)
    return normalize_relative(raw)


def normalize_relative(path: str) -> str:
    """Collapse a workspace-relative path. ``''`` and ``'.'`` are the root."""
    _reject_unsafe(path)
    raw = path.strip()
    if raw in {"", "."}:
        return ""
    if raw.startswith("/"):
        raise ValueError("path must be relative to the workspace root")
    parts = PurePosixPath(raw).parts
    if any(part == ".." for part in parts):
        raise ValueError("path escapes the workspace root")
    cleaned = [part for part in parts if part not in {"", "."}]
    return "/".join(cleaned)


def resolve_under_root(root: str, relative: str) -> str:
    """Join *relative* onto *root* and refuse a result outside *root*."""
    rel = normalize_relative(relative)
    root_norm = _root_norm(root)
    if not rel:
        return root_norm
    joined = _posix_norm(posixpath.join(root_norm, rel))
    if not _is_under(joined, root_norm):
        raise ValueError("path escapes the workspace root")
    return joined


def interval_due(rule: SyncRule, now: datetime) -> bool:
    """True when an interval rule should run at *now*."""
    if rule.when != "interval":
        return False
    if rule.interval_minutes < MIN_INTERVAL_MINUTES:
        return False
    if rule.last_run_at is None:
        return True
    try:
        last = datetime.fromisoformat(rule.last_run_at)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    moment = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return moment - last >= timedelta(minutes=rule.interval_minutes)


def execute_rule(
    fs: SyncFilesystem, workspace_root: str, rule_id: str, *, dry_run: bool
) -> SyncRun:
    """Run one saved rule. A dry run does not write last-run fields.

    One mirror runs one transfer at a time. A second caller gets
    :class:`SyncBusyError` instead of a stacked rsync.
    """
    with exclusive_transfer(fs.mirror_root):
        rule = get_rule(fs.mirror_root, rule_id)
        plan = transfer_plan(rule)
        remote = resolve_under_root(workspace_root, rule.path)
        try:
            payload = fs.rsync(
                remote,
                direction=rule.direction,
                include=plan.include,
                exclude=plan.exclude,
                delete=plan.delete,
                dry_run=dry_run,
                recursive=plan.recursive,
            )
        except Exception as exc:
            message = one_line(str(exc)) or "Sync failed."
            if not dry_run:
                _record_failure(fs.mirror_root, rule_id, message)
            raise SyncFailedError(message) from exc
        full = _output_text(payload)
        if dry_run:
            return SyncRun(rule=rule, output=_cap(full) or "Nothing to copy.", dry_run=True)
        summary = one_line(full) or "Copied."
        saved = record_result(fs.mirror_root, rule_id, status="ok", output=summary)
        return SyncRun(rule=saved, output=_cap(full) or summary, dry_run=False)


def record_result(
    mirror_root: Path | str,
    rule_id: str,
    *,
    status: str,
    output: str,
) -> SyncRule:
    """Write last-run fields. Other fields of the rule stay as saved."""
    if status not in {"ok", "error", "skipped"}:
        raise ValueError("status must be ok, error, or skipped")
    stamped = datetime.now(UTC).isoformat()
    line = one_line(output)
    with _locked(mirror_root):
        rules = _read(mirror_root)
        found: SyncRule | None = None
        updated: list[SyncRule] = []
        for rule in rules:
            if rule.id == rule_id:
                found = replace(
                    rule,
                    last_run_at=stamped,
                    last_status=status,
                    last_output=line,
                )
                updated.append(found)
            else:
                updated.append(rule)
        if found is None:
            raise KeyError(rule_id)
        _write(mirror_root, updated)
        return found


def one_line(text: str, *, limit: int = _OUTPUT_LIMIT) -> str:
    """First non-empty line, truncated."""
    line = ""
    for part in str(text).splitlines():
        stripped = part.strip()
        if stripped:
            line = stripped
            break
    if len(line) > limit:
        return line[: limit - 1] + "…"
    return line


@contextmanager
def exclusive_transfer(mirror_root: Path | str) -> Generator[None]:
    """Hold the single in-flight transfer for this mirror."""
    key = _mirror_key(mirror_root)
    with _held_guard:
        if key in _held:
            raise SyncBusyError("A sync for this workspace is already running.")
        _held.add(key)
    try:
        yield
    finally:
        with _held_guard:
            _held.discard(key)


def _record_failure(mirror_root: Path | str, rule_id: str, message: str) -> None:
    try:
        record_result(mirror_root, rule_id, status="error", output=message)
    except KeyError:
        return


def _output_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    raw = payload.get("output", "")
    return raw if isinstance(raw, str) else str(raw)


def _cap(text: str) -> str:
    if len(text) <= _PREVIEW_LIMIT:
        return text
    return text[:_PREVIEW_LIMIT] + "\n…"


def _choice(value: str, allowed: tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(allowed)}")
    return value


def _interval_minutes(value: object, *, when: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("interval must be a whole number of minutes")
    if value > _MAX_INTERVAL_MINUTES:
        raise ValueError("interval is too long")
    if when == "interval" and value < MIN_INTERVAL_MINUTES:
        raise ValueError(f"interval must be at least {MIN_INTERVAL_MINUTES} minutes")
    if value < MIN_INTERVAL_MINUTES:
        return DEFAULT_INTERVAL_MINUTES
    return value


def _canonical_types(types: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    unknown = [item for item in types if item not in _TYPE_GLOBS]
    if unknown:
        raise ValueError(f"unknown file type: {unknown[0]}")
    selected = set(types)
    return tuple(key for key in _TYPE_ORDER if key in selected)


def _globs(types: tuple[str, ...]) -> tuple[str, ...]:
    globs: list[str] = []
    for key in _TYPE_ORDER:
        if key in types:
            globs.extend(_TYPE_GLOBS[key])
    return tuple(globs)


def _reject_unsafe(path: str) -> None:
    if not isinstance(path, str):
        raise ValueError("path must be a string")
    if any(char in path for char in "\\\n\r\x00"):
        raise ValueError("path must be a workspace-relative POSIX path")


def _posix_norm(path: str) -> str:
    norm = posixpath.normpath(path)
    if norm.startswith("//"):
        norm = "/" + norm.lstrip("/")
    return norm


def _root_norm(root: str) -> str:
    text = str(root).strip()
    if not text:
        raise ValueError("workspace root is missing")
    norm = _posix_norm(text)
    if norm in {"", "."}:
        raise ValueError("workspace root is missing")
    return norm


def _relative_absolute(root: str, path: str) -> str:
    if any(part == ".." for part in PurePosixPath(path).parts):
        raise ValueError("path escapes the workspace root")
    root_norm = _root_norm(root)
    candidate = _posix_norm(path.strip())
    if candidate == root_norm:
        return ""
    if _is_under(candidate, root_norm):
        prefix = "/" if root_norm == "/" else root_norm.rstrip("/") + "/"
        return candidate[len(prefix) :]
    raise ValueError("path escapes the workspace root")


def _is_under(path: str, root: str) -> bool:
    if path == root:
        return True
    prefix = "/" if root == "/" else root.rstrip("/") + "/"
    return path.startswith(prefix)


def _mirror_key(mirror_root: Path | str) -> str:
    return str(Path(mirror_root))


@contextmanager
def _locked(mirror_root: Path | str) -> Generator[None]:
    key = _mirror_key(mirror_root)
    with _locks_guard:
        lock = _file_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _file_locks[key] = lock
    with lock:
        yield


def _read(mirror_root: Path | str) -> list[SyncRule]:
    path = rules_path(mirror_root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyncRulesError(f"could not read sync rules: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise SyncRulesError("sync rules file is not a rules list")
    rules: list[SyncRule] = []
    for item in raw["rules"]:
        rules.append(_rule_from_json(item))
    return rules


def _write(mirror_root: Path | str, rules: list[SyncRule]) -> None:
    atomic_write_json(rules_path(mirror_root), {"rules": [_rule_to_json(rule) for rule in rules]})


def _rule_to_json(rule: SyncRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "path": rule.path,
        "kind": rule.kind,
        "direction": rule.direction,
        "content": rule.content,
        "types": list(rule.types),
        "extraFiles": rule.extra_files,
        "when": rule.when,
        "intervalMinutes": rule.interval_minutes,
        "lastRunAt": rule.last_run_at,
        "lastStatus": rule.last_status,
        "lastOutput": rule.last_output,
    }


def _rule_from_json(item: object) -> SyncRule:
    fields = _object_fields(item)
    try:
        return make_rule(
            id=_required_str(fields, "id"),
            path=_required_str(fields, "path"),
            kind=_required_str(fields, "kind"),
            direction=_required_str(fields, "direction"),
            content=_required_str(fields, "content"),
            types=_string_tuple(fields.get("types")),
            extra_files=_text_or(fields.get("extraFiles"), "keep"),
            when=_required_str(fields, "when"),
            interval_minutes=_stored_interval(fields.get("intervalMinutes")),
            last_run_at=_optional_text(fields.get("lastRunAt")),
            last_status=_optional_text(fields.get("lastStatus")),
            last_output=_optional_text(fields.get("lastOutput")),
        )
    except (ValueError, TypeError) as exc:
        raise SyncRulesError(str(exc)) from exc


def _object_fields(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        raise SyncRulesError("sync rule is not an object")
    fields: dict[str, object] = {}
    for key, value in item.items():
        if not isinstance(key, str):
            raise SyncRulesError("sync rule is not an object")
        fields[key] = value
    return fields


def _required_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        if key == "path" and value == "":
            return ""
        raise SyncRulesError(f"sync rule is missing {key}")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise SyncRulesError("sync rule field must be text")


def _text_or(value: object, default: str) -> str:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value
    raise SyncRulesError("sync rule field must be text")


def _stored_interval(value: object) -> int:
    if value is None:
        return DEFAULT_INTERVAL_MINUTES
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyncRulesError("interval must be a whole number of minutes")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise SyncRulesError("sync rule types must be a list")
    names: list[str] = []
    for part in value:
        if not isinstance(part, str):
            raise SyncRulesError("sync rule types must be text")
        names.append(part)
    return tuple(names)
