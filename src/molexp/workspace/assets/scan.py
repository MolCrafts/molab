"""Manifest-scanning asset query layer — replaces the derived SQLite catalog.

The authoritative source for assets is each scope's ``assets.json``
(:class:`~molexp.workspace.assets.manifest.AssetManifest`). This module answers
the cross-cutting asset queries that the old ``AssetCatalog`` served — but by
scanning those manifests directly, so there is no second on-disk index to keep
in sync (the One-source-of-truth law: every index is derived; here we drop the
index entirely rather than rebuild it).

Each :class:`~molexp.workspace.assets.base.Asset` carries its own
:class:`~molexp.workspace.assets.base.AssetScope`, so filtering is done on the
asset itself. The walk is **scope-aware**: because the on-disk layout is fixed
(``projects/<p>/experiments/<e>/runs/run-<r>``, the layout naming law), a scoped
query starts at that scope's directory (:func:`scope_dir_for`) and, unless
``recursive``, reads exactly one manifest — it never walks the whole workspace
to answer a question about one run. An unscoped query is still a full walk.
Results are ordered deterministically by ``(created_at, asset_id)``.

Every read is a *try-read*: optional files (``assets.json``,
``assets/<id>/asset.json``) are opened directly and an unreadable one is
treated as absent, so no ``exists`` / ``is_dir`` probe precedes a read. The
container listings (``projects/`` / ``experiments/`` / ``runs/``, and each
scope's optional ``assets/``) go through ``scandir``, which reports both that
the container exists and which of its entries are directories — so a missing
container and a loose file alongside real scope dirs both cost nothing extra.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from os import PathLike
from typing import TYPE_CHECKING, Literal

from ..fs_local import LocalFileSystem
from ..utils import generate_asset_id
from ._adapter import parse_asset
from .base import Asset, AssetScope, Producer
from .manifest import MANIFEST_FILENAME, AssetManifest

if TYPE_CHECKING:
    from ..fs import FileSystem

_SCOPE_KIND_RANK: dict[str, int] = {
    "workspace": 0,
    "project": 1,
    "experiment": 2,
    "run": 3,
}

_ScopeKind = Literal["workspace", "project", "experiment", "run"]

# Child container per scope kind — the layout naming law
# (``Workspace → Project → Experiment → Run``; container = child kind pluralized).
_CHILD_CONTAINER: dict[str, tuple[str, _ScopeKind]] = {
    "workspace": ("projects", "project"),
    "project": ("experiments", "experiment"),
    "experiment": ("runs", "run"),
}

_DATA_ASSET_DIR = "assets"
_DATA_ASSET_RECORD = "asset.json"
_RUN_DIR_PREFIX = "run-"


def _fs_or_local(fs: FileSystem | None) -> FileSystem:
    return fs if fs is not None else LocalFileSystem()


def _safe_segment(segment: str) -> bool:
    """True when *segment* is a single well-formed directory name."""
    return (
        bool(segment) and segment not in {".", ".."} and "/" not in segment and "\\" not in segment
    )


def scope_dir_for(
    root: str | PathLike[str],
    scope: AssetScope,
    fs: FileSystem | None = None,
) -> str | None:
    """Return the on-disk directory of *scope* by pure layout math.

    Mirrors the server's ``resolve_scope_dir`` (which navigates the folder
    tree and re-reads entity JSON at every level) without any I/O:
    ``projects/<p>`` / ``projects/<p>/experiments/<e>`` /
    ``…/runs/run-<r>`` — the ``run-`` prefix is part of the layout contract.
    Extra trailing ids are ignored, as the server resolver ignores them.

    Returns ``None`` for a malformed scope (too few ids, or an id that is not
    a single path segment) so a caller can answer "no such scope" without
    ever composing a path that escapes the workspace.
    """
    fs = _fs_or_local(fs)
    base = str(root)
    if scope.kind == "workspace":
        return base
    ids = scope.ids
    needed = _SCOPE_KIND_RANK.get(scope.kind)
    if needed is None or len(ids) < needed or not all(_safe_segment(s) for s in ids[:needed]):
        return None
    path = fs.join(base, "projects", ids[0])
    if scope.kind == "project":
        return path
    path = fs.join(path, "experiments", ids[1])
    if scope.kind == "experiment":
        return path
    return fs.join(path, "runs", f"{_RUN_DIR_PREFIX}{ids[2]}")


def _iter_scope_dirs(
    fs: FileSystem,
    start: str,
    kind: _ScopeKind,
    *,
    recursive: bool,
) -> Iterator[str]:
    """Yield *start* and, when *recursive*, every scope directory beneath it.

    Descent follows the layout law only (``projects/`` → ``experiments/`` →
    ``runs/``); order is sorted per container so the result is deterministic
    and independent of filesystem walk order. One ``scandir`` per container is
    the only call: it reports both that the container exists and which of its
    entries are directories, so neither the container nor its entries needs a
    separate ``is_dir`` probe.
    """
    yield start
    if not recursive:
        return
    container = _CHILD_CONTAINER.get(kind)
    if container is None:
        return
    container_name, child_kind = container
    container_dir = fs.join(start, container_name)
    try:
        entries = fs.scandir(container_dir, with_stat=False)
    except Exception:  # absent container, or not a directory — nothing below
        return
    for entry in sorted(entries, key=lambda e: e.name):
        if not entry.is_dir:
            continue
        yield from _iter_scope_dirs(
            fs,
            fs.join(container_dir, entry.name),
            child_kind,
            recursive=True,
        )


def _try_read_json(fs: FileSystem, path: str) -> object | None:
    """Read + parse a JSON document, or ``None`` when absent / unreadable.

    Catches broadly on purpose: this is an *optional* file, and remote
    transports surface "no such file" / "not a directory" as their own
    (non-``OSError``) error types.
    """
    try:
        return json.loads(fs.read_text(path))
    except Exception:  # optional file: absent, unreadable, or malformed
        return None


def _try_listdir_dirs(fs: FileSystem, path: str) -> list[str]:
    """Sorted names of *path*'s subdirectories — ``[]`` when *path* is absent.

    One ``scandir``: the listing already says which entries are directories, so
    a loose file alongside the asset dirs costs no probe and no failed read.
    """
    try:
        return sorted(e.name for e in fs.scandir(path, with_stat=False) if e.is_dir)
    except Exception:  # see _try_read_json
        return []


def _load_manifest_assets(fs: FileSystem, scope_dir: str) -> Iterator[Asset]:
    """Yield the assets recorded in ``<scope_dir>/assets.json`` (one read)."""
    data = _try_read_json(fs, fs.join(scope_dir, MANIFEST_FILENAME))
    raw_assets = data.get("assets", {}) if isinstance(data, dict) else {}
    if not isinstance(raw_assets, dict):
        return
    for entry in raw_assets.values():
        if not isinstance(entry, dict):
            continue
        try:
            yield parse_asset(entry)
        except (ValueError, TypeError, KeyError):
            continue


def _load_data_assets(fs: FileSystem, scope_dir: str) -> Iterator[Asset]:
    """Yield ``DataAsset``s stored as ``<scope_dir>/assets/<id>/asset.json``.

    User-imported ``DataAsset``s are written one-per-directory by
    :class:`~molexp.workspace.assets.data.DataAssetLibrary` rather than into the
    scope's ``assets.json`` manifest, so they are an authoritative source the
    scanner must read alongside the manifest.
    """
    data_dir = fs.join(scope_dir, _DATA_ASSET_DIR)
    for asset_name in _try_listdir_dirs(fs, data_dir):
        record = _try_read_json(fs, fs.join(data_dir, asset_name, _DATA_ASSET_RECORD))
        if not isinstance(record, dict):
            continue
        try:
            yield parse_asset(record)
        except (ValueError, TypeError, KeyError):
            continue


def _collect_assets(
    root: str | PathLike[str],
    fs: FileSystem | None,
    *,
    scope: AssetScope | None = None,
    recursive: bool = True,
) -> list[Asset]:
    """Load every asset under *scope* (default: the whole workspace).

    Two authoritative sources per scope directory: the ``assets.json``
    manifest (run-produced artifacts / logs / checkpoints) and the per-asset
    ``assets/<id>/asset.json`` files (user-imported ``DataAsset``s).
    Deduplicated by ``asset_id`` (manifest wins). A malformed *scope* has no
    directory and therefore no assets.
    """
    fs = _fs_or_local(fs)
    kind: _ScopeKind
    if scope is None:
        # No scope = the whole workspace; ``recursive`` only narrows a scoped walk.
        start, kind, recursive = str(root), "workspace", True
    else:
        resolved = scope_dir_for(root, scope, fs)
        if resolved is None:
            return []
        start, kind = resolved, scope.kind
    out: list[Asset] = []
    seen: set[str] = set()
    for scope_dir in _iter_scope_dirs(fs, start, kind, recursive=recursive):
        for asset in _load_manifest_assets(fs, scope_dir):
            if asset.asset_id not in seen:
                seen.add(asset.asset_id)
                out.append(asset)
        for asset in _load_data_assets(fs, scope_dir):
            if asset.asset_id not in seen:
                seen.add(asset.asset_id)
                out.append(asset)
    return out


def _sorted(assets: Sequence[Asset]) -> list[Asset]:
    return sorted(assets, key=lambda a: (a.created_at, a.asset_id))


def _kind_value(kind: str | type[Asset] | None) -> str | None:
    """Normalize a ``kind`` filter (str or Asset subclass) to its string value."""
    if kind is None:
        return None
    if isinstance(kind, str):
        return kind
    try:
        return kind.model_fields["kind"].default  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return None


def _scope_matches(asset_scope: AssetScope, scope: AssetScope, recursive: bool) -> bool:
    """Mirror ``AssetCatalog`` scope filtering (exact, or recursive prefix)."""
    if not recursive:
        return asset_scope.kind == scope.kind and asset_scope.ids == scope.ids
    arank = _SCOPE_KIND_RANK.get(asset_scope.kind)
    srank = _SCOPE_KIND_RANK.get(scope.kind, 0)
    if arank is None or arank < srank:
        return False
    n = len(scope.ids)
    return asset_scope.ids[:n] == scope.ids


def scan_assets(
    root: str | PathLike[str],
    *,
    kind: str | type[Asset] | None = None,
    scope: AssetScope | None = None,
    producer_run: str | None = None,
    producer_task: str | None = None,
    tag: tuple[str, str] | None = None,
    limit: int | None = None,
    recursive: bool = False,
    fs: FileSystem | None = None,
) -> list[Asset]:
    """Query assets from the manifests, mirroring ``AssetCatalog.query_assets``.

    With a ``scope`` the walk starts at that scope's directory
    (:func:`scope_dir_for`): ``recursive=False`` reads exactly one manifest,
    ``recursive=True`` walks only that subtree (any sub-scope whose ids extend
    the given scope's ids). Without a ``scope`` every manifest in the
    workspace is read. Results are ordered by ``(created_at, asset_id)``.

    Pass *fs* (e.g. a remote :class:`~molexp.workspace.fs_remote.RemoteFileSystem`)
    to scan without assuming a local path exists for *root*.
    """
    kind_str = _kind_value(kind)
    out: list[Asset] = []
    collected = _collect_assets(root, fs, scope=scope, recursive=recursive)
    for asset in _sorted(collected):
        if kind_str is not None and getattr(asset, "kind", None) != kind_str:
            continue
        if scope is not None and not _scope_matches(asset.scope, scope, recursive):
            continue
        producer = asset.producer
        if producer_run and (producer is None or producer.run_id != producer_run):
            continue
        if producer_task and (producer is None or producer.task_id != producer_task):
            continue
        if tag is not None:
            tk, tv = tag
            if asset.tags.get(tk) != tv:
                continue
        out.append(asset)
        if limit is not None and len(out) >= limit:
            break
    return out


def get_asset(
    root: str | PathLike[str],
    asset_id: str,
    *,
    fs: FileSystem | None = None,
    assets: Sequence[Asset] | None = None,
) -> Asset | None:
    """Return the asset with ``asset_id`` from any scope, else ``None``.

    An id alone does not say which scope owns it, so this is a full walk —
    unless the caller already holds the assets (*assets*), in which case no
    I/O happens at all. Callers answering several id lookups should scan
    once and pass the list.
    """
    pool = _collect_assets(root, fs) if assets is None else assets
    for asset in pool:
        if asset.asset_id == asset_id:
            return asset
    return None


def find_by_content_hash(
    root: str | PathLike[str],
    content_hash: str,
    *,
    fs: FileSystem | None = None,
    assets: Sequence[Asset] | None = None,
) -> Asset | None:
    """Return the earliest asset whose ``content_hash`` matches, else ``None``.

    Content-addressed lookup used by the workflow cache's re-registration path:
    a match means the bytes are present somewhere in the workspace. Pass
    *assets* to search an already-scanned list without touching disk.
    """
    if not content_hash:
        return None
    pool = _collect_assets(root, fs) if assets is None else assets
    for asset in _sorted(pool):
        if asset.content_hash == content_hash:
            return asset
    return None


def reregister_artifact(
    root: str | PathLike[str],
    scope_dir: str | PathLike[str],
    *,
    name: str | None,
    content_hash: str,
    target_scope: AssetScope,
    producer_task: str | None = None,
    inputs: tuple[str, ...] = (),
) -> Asset | None:
    """Idempotently re-register a content-addressed artifact into ``target_scope``.

    Looks the artifact up by ``content_hash`` across the workspace; if found,
    writes a fresh artifact row into ``scope_dir``'s manifest pointing at the
    SAME path + ``content_hash`` (no recompute, no byte recopy). Returns the new
    asset, or ``None`` when the bytes are absent (fresh workspace) so the caller
    can skip gracefully. Idempotent on ``(name, content_hash)`` within the scope.
    """
    source = find_by_content_hash(root, content_hash)
    if source is None:
        return None
    manifest = AssetManifest(scope_dir)
    for existing in manifest.load().values():
        if (
            getattr(existing, "kind", None) == "artifact"
            and existing.content_hash == content_hash
            and existing.scope == target_scope
            and existing.name == name
        ):
            return existing
    now = datetime.now()
    clone = source.model_copy(
        update={
            "asset_id": generate_asset_id(),
            "name": name,
            "scope": target_scope,
            "created_at": now,
            "updated_at": now,
            "producer": Producer(
                run_id=target_scope.ids[-1] if target_scope.ids else None,
                task_id=producer_task,
                inputs=inputs,
            ),
        }
    )
    manifest.register(clone)
    return clone


# ── Snapshot (in-memory, stat-validated) ────────────────────────────────────
#
# A full scan is O(scope dirs) manifest reads. That is the right cost to pay
# once, and the wrong cost to pay per request: the server answers many asset
# questions ("this id", "this content hash", "this scope's rows", "this
# lineage") between two writes. :class:`AssetScanSnapshot` holds one scan plus
# the indexes those questions need, and :func:`build_asset_snapshot` reuses it
# while every manifest's ``(size, mtime)`` is unchanged.
#
# Law check: in-memory only. Nothing is persisted — this is NOT the retired
# derived asset index; the per-scope ``assets.json`` files remain the sole
# truth and a restart rebuilds by scanning them.

#: A manifest's change-detection key — ``(size, mtime)``, ``None`` when absent.
type StatKey = tuple[int, float] | None


def _stat_key(fs: FileSystem, path: str) -> StatKey:
    try:
        st = fs.stat(path)
    except Exception:  # absent, unreadable, or a transport hiccup
        return None
    return (st.size, st.mtime)


class AssetScanSnapshot:
    """One workspace-wide asset scan plus the indexes queries are answered from.

    Attributes:
        version: Bumped whenever a rebuild produced a different asset set.
        assets: Every asset, ordered by ``(created_at, asset_id)``.
        by_id: ``asset_id`` → asset.
        by_hash: ``content_hash`` → the **earliest** asset carrying it (same
            tie-break as :func:`find_by_content_hash`).
        by_scope_dir: scope directory → that scope's assets.
        children_of: ``asset_id`` → ids of the assets consuming it (the
            inverted ``Producer.inputs`` edge, for descendant traversal).
    """

    __slots__ = (
        "_manifest_keys",
        "assets",
        "built_at",
        "by_hash",
        "by_id",
        "by_scope_dir",
        "children_of",
        "version",
    )

    def __init__(
        self,
        *,
        version: int,
        assets: tuple[Asset, ...],
        by_scope_dir: dict[str, tuple[Asset, ...]] | None = None,
        manifest_keys: dict[str, tuple[StatKey, StatKey]] | None = None,
        built_at: float | None = None,
    ) -> None:
        import time

        self.version = version
        self.assets = assets
        self.by_id: dict[str, Asset] = {a.asset_id: a for a in assets}
        by_hash: dict[str, Asset] = {}
        for asset in assets:  # ``assets`` is already (created_at, asset_id)-sorted
            if asset.content_hash and asset.content_hash not in by_hash:
                by_hash[asset.content_hash] = asset
        self.by_hash = by_hash
        children: dict[str, list[str]] = {}
        for asset in assets:
            if asset.producer is None:
                continue
            for inp in asset.producer.inputs:
                children.setdefault(inp, []).append(asset.asset_id)
        self.children_of: dict[str, tuple[str, ...]] = {k: tuple(v) for k, v in children.items()}
        self.by_scope_dir = by_scope_dir or {}
        self._manifest_keys = manifest_keys or {}
        self.built_at = built_at if built_at is not None else time.monotonic()

    def __len__(self) -> int:
        return len(self.assets)

    def in_scope(self, scope: AssetScope, *, recursive: bool = False) -> list[Asset]:
        """This snapshot's assets matching *scope* — pure, no I/O."""
        return [a for a in self.assets if _scope_matches(a.scope, scope, recursive)]


def _scope_keys(fs: FileSystem, root: str) -> dict[str, tuple[StatKey, StatKey]]:
    """``scope_dir → (assets.json key, assets/ dir key)`` for every scope dir."""
    return {
        scope_dir: (
            _stat_key(fs, fs.join(scope_dir, MANIFEST_FILENAME)),
            _stat_key(fs, fs.join(scope_dir, _DATA_ASSET_DIR)),
        )
        for scope_dir in _iter_scope_dirs(fs, root, "workspace", recursive=True)
    }


def build_asset_snapshot(
    root: str | PathLike[str],
    *,
    fs: FileSystem | None = None,
    previous: AssetScanSnapshot | None = None,
) -> AssetScanSnapshot:
    """Scan every manifest into an :class:`AssetScanSnapshot`, reusing *previous*.

    The probe is one ``stat`` per scope directory's ``assets.json`` and its
    ``assets/`` dir; when every key matches *previous* the snapshot is handed
    back unchanged (no manifest is opened). Otherwise the scan is redone in
    full — manifests are small and a partial rebuild would have to re-derive
    the cross-scope lineage index anyway.
    """
    fs = _fs_or_local(fs)
    base = str(root)
    keys = _scope_keys(fs, base)
    if previous is not None and previous._manifest_keys == keys:
        return previous

    assets = tuple(_sorted(_collect_assets(base, fs)))
    by_scope_dir: dict[str, list[Asset]] = {}
    for asset in assets:
        scope_dir = scope_dir_for(base, asset.scope, fs)
        if scope_dir is not None:
            by_scope_dir.setdefault(scope_dir, []).append(asset)

    version = (previous.version if previous is not None else 0) + 1
    if previous is not None and [a.asset_id for a in previous.assets] == [
        a.asset_id for a in assets
    ]:
        version = previous.version
    return AssetScanSnapshot(
        version=version,
        assets=assets,
        by_scope_dir={k: tuple(v) for k, v in by_scope_dir.items()},
        manifest_keys=keys,
    )
