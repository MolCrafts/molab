"""``WorkspaceReadModel`` — the process-level holder of the derived read views.

:mod:`molexp.workspace.read_model` knows how to *build* a snapshot;
this knows **when**. It keeps the current runs / assets / knowledge snapshots
for one workspace, decides cheaply whether they are still valid, and refreshes
them on a background ticker so a request serves the last good snapshot instead
of blocking on a rescan (stale-while-revalidate).

How staleness is decided
========================
Three signals, cheapest first:

1. **The event spine's ``max_seq``** — one SQL query. Any run verb, asset
   registration or knowledge write *in any process* bumps it, and the events
   after the cursor say which views to rebuild.
2. **Container ``stat``s** — catches an addition/removal that emitted no
   event (an older writer, a hand-edited tree).
3. **A periodic full sweep** (``full_sweep_interval``) — the backstop for a
   write that neither emitted nor moved a container mtime, e.g. an in-place
   ``_ops/run.json`` rewrite by a process that predates the spine. One sweep
   is ``2N`` stats and zero reads when nothing changed.

Remote workspaces are **pinned**: a ``CachedRemoteFileSystem`` answers reads
from its local mirror until it is explicitly refreshed, so re-statting over
SSH would be pure cost with no new information. There the snapshot is valid
until ``fs.generation`` moves (the cache was invalidated/reindexed) or
:meth:`WorkspaceReadModel.invalidate` is called.

Law check: every snapshot is in-memory, derived, and rebuilt by rescanning the
authoritative files. Nothing here is persisted.

Runtime container, so a plain class (threads, locks, live snapshots) — not a
pydantic model; only :class:`RefreshPolicy` is frozen data.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from mollog import get_logger
from pydantic import BaseModel

from molexp.workspace.assets.scan import AssetScanSnapshot, build_asset_snapshot
from molexp.workspace.read_model import (
    KnowledgeSnapshot,
    RunsSnapshot,
    build_knowledge_snapshot,
    build_runs_snapshot,
    runs_snapshot_is_stale,
)

from .workspace_notify import ChangeKind, WorkspaceChange, notify_workspace_changed

if TYPE_CHECKING:
    from molexp._typing import JSONValue
    from molexp.workspace import Workspace

_logger = get_logger(__name__)

__all__ = ["RefreshPolicy", "ViewKind", "WorkspaceReadModel"]

ViewKind = Literal["runs", "assets", "knowledge", "all"]

# Spine event types that dirty each view.
_EVENT_VIEW: dict[str, ViewKind] = {
    "run.created": "runs",
    "run.started": "runs",
    "run.failed": "runs",
    "run.completed": "runs",
    "run.cancelled": "runs",
    "experiment.created": "runs",
    "workflow.created": "runs",
    "asset.added": "assets",
    "knowledge.created": "knowledge",
}


class RefreshPolicy(BaseModel, frozen=True):
    """When a view is considered stale and how eagerly it is rebuilt.

    Attributes:
        mode: ``"local"`` re-validates by ``stat``; ``"pinned"`` (a cached
            remote filesystem) trusts the snapshot until the cache generation
            moves or something invalidates explicitly.
        runs_max_age / assets_max_age / knowledge_max_age: Serve-without-probe
            windows, in seconds.
        full_sweep_interval: Upper bound between two full ``stat`` sweeps.
        hot_window: How long after the last read/subscriber the ticker keeps
            refreshing; an idle workspace costs nothing.
        tick_interval: Background ticker period.
    """

    mode: Literal["local", "pinned"] = "local"
    runs_max_age: float = 1.0
    assets_max_age: float = 5.0
    knowledge_max_age: float = 15.0
    full_sweep_interval: float = 15.0
    hot_window: float = 60.0
    tick_interval: float = 2.0


def _policy_for(workspace: Workspace) -> RefreshPolicy:
    """Pinned for a cached-remote filesystem, stat-validated otherwise."""
    from molexp.workspace.fs_cached import CachedRemoteFileSystem

    if isinstance(workspace.fs, CachedRemoteFileSystem):
        return RefreshPolicy(mode="pinned")
    return RefreshPolicy()


class WorkspaceReadModel:
    """Holds and refreshes one workspace's derived read views."""

    def __init__(self, workspace: Workspace, *, policy: RefreshPolicy | None = None) -> None:
        self._workspace = workspace
        self._policy = policy if policy is not None else _policy_for(workspace)
        self._root = str(workspace.resolve())
        self._lock = threading.RLock()  # serializes refreshes, not reads
        self._runs: RunsSnapshot | None = None
        self._assets: AssetScanSnapshot | None = None
        self._knowledge: KnowledgeSnapshot | None = None
        self._dirty: set[ViewKind] = set()
        self._last_seq = 0
        self._last_full_sweep = 0.0
        self._last_touch = time.monotonic()
        self._generation = self._fs_generation()
        self._ticker: threading.Thread | None = None
        self._stop = threading.Event()
        # run_dir → (file stat key, next unread line, folded {key: latest})
        self._metrics_cache: dict[str, tuple[tuple[int, float], int, dict[str, JSONValue]]] = {}

    # ── accessors ─────────────────────────────────────────────────────────

    @property
    def policy(self) -> RefreshPolicy:
        return self._policy

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def touch(self) -> None:
        """Mark the workspace as being watched (keeps the ticker hot)."""
        self._last_touch = time.monotonic()

    def runs(self) -> RunsSnapshot:
        """The runs view — builds on first call, then serves the snapshot.

        Two kinds of staleness, deliberately handled differently:

        * **Explicitly invalidated** (:meth:`invalidate`, i.e. a mutation this
          server just performed): rebuilt **now**, because the caller knows
          the snapshot is wrong and a UI that writes then refetches must not
          be shown the pre-write state.
        * **Merely aged** (a poll past ``runs_max_age``): the current snapshot
          is returned and a refresh is scheduled, so a poll's latency stays
          snapshot-lookup time.
        """
        self.touch()
        snap = self._runs
        if snap is None or "runs" in self._dirty:
            return self._refresh_runs()
        if self._should_probe(snap.built_at, self._policy.runs_max_age, "runs"):
            self._schedule("runs")
        return snap

    def assets(self) -> AssetScanSnapshot:
        """The asset view (see :meth:`runs` for the staleness contract)."""
        self.touch()
        snap = self._assets
        if snap is None or "assets" in self._dirty:
            return self._refresh_assets()
        if self._should_probe(snap.built_at, self._policy.assets_max_age, "assets"):
            self._schedule("assets")
        return snap

    def knowledge(self) -> KnowledgeSnapshot:
        """The knowledge view (see :meth:`runs` for the staleness contract)."""
        self.touch()
        snap = self._knowledge
        if snap is None or "knowledge" in self._dirty:
            return self._refresh_knowledge()
        if self._should_probe(snap.built_at, self._policy.knowledge_max_age, "knowledge"):
            self._schedule("knowledge")
        return snap

    def versions(self) -> dict[str, int]:
        """Current view versions — what an ETag and the SSE hello frame carry."""
        return {
            "runs": self._runs.version if self._runs else 0,
            "assets": self._assets.version if self._assets else 0,
            "knowledge": self._knowledge.version if self._knowledge else 0,
        }

    # ── invalidation ──────────────────────────────────────────────────────

    def invalidate(self, kind: ViewKind = "all", *, ref: str | None = None) -> None:  # noqa: ARG002
        """Mark a view dirty so the next read rebuilds it.

        *ref* is accepted for call-site expressiveness (and future per-run
        targeting); today a dirty view is rebuilt incrementally anyway, so
        only the runs whose files moved are re-read.
        """
        with self._lock:
            if kind == "all":
                self._dirty |= {"runs", "assets", "knowledge"}
            else:
                self._dirty.add(kind)

    def refresh(self, kind: ViewKind = "all", *, block: bool = True) -> None:
        """Rebuild *kind* now (``block``) or schedule it on the ticker."""
        if not block:
            self._schedule(kind)
            return
        if kind in {"runs", "all"}:
            self._refresh_runs()
        if kind in {"assets", "all"}:
            self._refresh_assets()
        if kind in {"knowledge", "all"}:
            self._refresh_knowledge()

    # ── refresh internals ─────────────────────────────────────────────────

    def _fs_generation(self) -> int:
        return int(getattr(self._workspace.fs, "generation", 0) or 0)

    def _should_probe(self, built_at: float, max_age: float, kind: ViewKind) -> bool:
        """Whether a read should schedule a background refresh."""
        if kind in self._dirty:
            return True
        if self._policy.mode == "pinned":
            return self._fs_generation() != self._generation
        return (time.monotonic() - built_at) >= max_age

    def _drain_spine(self) -> set[ViewKind]:
        """Read new spine events; return the views they dirty (and publish them).

        This is what makes a change made by *another process* (a CLI
        ``molexp run``) reach a browser tab attached to this server.
        """
        from molexp.workspace.events import WORKSPACE_EVENTS_DB, read_workspace_events

        if self._policy.mode == "pinned":
            return set()
        if not (Path(self._root) / WORKSPACE_EVENTS_DB).exists():
            return set()
        try:
            events = read_workspace_events(self._root, after_seq=self._last_seq)
        except Exception:  # a locked/rotating DB must not break a refresh
            return set()
        dirty: set[ViewKind] = set()
        for event in events:
            self._last_seq = max(self._last_seq, event.seq)
            view = _EVENT_VIEW.get(str(event.type))
            if view is not None:
                dirty.add(view)
        return dirty

    def _refresh_runs(self) -> RunsSnapshot:
        with self._lock:
            previous = self._runs
            dirty = self._drain_spine()
            self._dirty |= dirty
            forced = "runs" in self._dirty
            now = time.monotonic()
            if (
                previous is not None
                and not forced
                and self._policy.mode == "local"
                and (now - self._last_full_sweep) < self._policy.full_sweep_interval
                and not runs_snapshot_is_stale(self._workspace, previous)
            ):
                return previous
            if previous is not None and self._policy.mode == "pinned" and not forced:
                gen = self._fs_generation()
                if gen == self._generation:
                    return previous
                self._generation = gen
            snapshot = build_runs_snapshot(
                self._workspace, previous=previous, last_seq=self._last_seq
            )
            self._runs = snapshot
            self._last_full_sweep = now
            self._dirty.discard("runs")
            if previous is not None and snapshot.version != previous.version:
                self._publish("run")
            return snapshot

    def _refresh_assets(self) -> AssetScanSnapshot:
        with self._lock:
            previous = self._assets
            self._dirty |= self._drain_spine()
            forced = "assets" in self._dirty
            if (
                previous is not None
                and self._policy.mode == "pinned"
                and not forced
                and self._fs_generation() == self._generation
            ):
                return previous
            snapshot = build_asset_snapshot(
                self._workspace.resolve(), fs=self._workspace.fs, previous=previous
            )
            self._assets = snapshot
            self._dirty.discard("assets")
            if previous is not None and snapshot.version != previous.version:
                self._publish("asset")
            return snapshot

    def _refresh_knowledge(self) -> KnowledgeSnapshot:
        with self._lock:
            previous = self._knowledge
            self._dirty |= self._drain_spine()
            forced = "knowledge" in self._dirty
            if (
                previous is not None
                and self._policy.mode == "pinned"
                and not forced
                and self._fs_generation() == self._generation
            ):
                return previous
            snapshot = build_knowledge_snapshot(self._workspace, previous=previous)
            self._knowledge = snapshot
            self._dirty.discard("knowledge")
            if previous is not None and snapshot.version != previous.version:
                self._publish("knowledge")
            return snapshot

    def _publish(self, kind: ChangeKind) -> None:
        """Announce a sweep-detected change (one a route never emitted)."""
        notify_workspace_changed(
            WorkspaceChange(
                root=self._root,
                kind=kind,
                seq=self._last_seq or None,
                versions=self.versions(),
            )
        )

    # ── background ticker ─────────────────────────────────────────────────

    def _schedule(self, kind: ViewKind) -> None:
        """Ask the ticker to refresh *kind*; start it if it is not running."""
        with self._lock:
            if kind == "all":
                self._dirty |= {"runs", "assets", "knowledge"}
            else:
                self._dirty.add(kind)
        self.start()

    def start(self) -> None:
        """Start the background refresher (idempotent, daemon)."""
        with self._lock:
            if self._ticker is not None and self._ticker.is_alive():
                return
            self._stop.clear()
            self._ticker = threading.Thread(
                target=self._tick_loop,
                name=f"molexp-readmodel-{Path(self._root).name}",
                daemon=True,
            )
            self._ticker.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        """Stop the refresher and join it (server shutdown / tests)."""
        self._stop.set()
        ticker = self._ticker
        if ticker is not None and ticker.is_alive():
            ticker.join(timeout=timeout)
        self._ticker = None

    def _tick_loop(self) -> None:
        while not self._stop.wait(self._policy.tick_interval):
            if (time.monotonic() - self._last_touch) > self._policy.hot_window:
                # Nobody is watching: go quiet rather than sweep forever.
                break
            try:
                pending = set(self._dirty)
                if pending or self._runs is not None:
                    self.refresh("runs", block=True)
                if "assets" in pending and self._assets is not None:
                    self.refresh("assets", block=True)
                if "knowledge" in pending and self._knowledge is not None:
                    self.refresh("knowledge", block=True)
            except Exception:  # a refresher must never kill its thread
                _logger.debug("read-model refresh failed", exc_info=True)
        with self._lock:
            self._ticker = None

    # ── metrics memo (experiment comparison) ──────────────────────────────

    def metrics_summary(self, run_dir: Path | str) -> dict[str, JSONValue]:
        """``{metric key: latest value}`` for one run, read incrementally.

        The comparison endpoint used to re-parse every run's whole
        ``metrics.jsonl`` (up to 50 000 records each) on every request. Here
        the fold is memoized against the file's ``(size, mtime)`` and only the
        lines appended since the last read are parsed.
        """
        from molexp.workspace.metrics import read_run_metrics

        path = Path(run_dir) / "metrics" / "metrics.jsonl"
        try:
            st = path.stat()
            key: tuple[int, float] | None = (st.st_size, st.st_mtime)
        except OSError:
            key = None
        if key is None:
            return {}
        with self._lock:
            cached = self._metrics_cache.get(str(run_dir))
        if cached is not None and cached[0] == key:
            return dict(cached[2])
        since = cached[1] if cached is not None else 0
        latest: dict[str, JSONValue] = dict(cached[2]) if cached is not None else {}
        try:
            result = read_run_metrics(Path(run_dir), since_line=since, limit=50000)
        except (FileNotFoundError, OSError, ValueError):
            return latest
        for series in result.series:
            key_raw = series.get("key")
            value = series.get("latestValue")
            if isinstance(key_raw, str) and key_raw and value is not None:
                latest[key_raw] = value
        with self._lock:
            self._metrics_cache[str(run_dir)] = (key, result.next_line, latest)
            # Bounded: a workspace with 10k runs must not pin 10k folds.
            if len(self._metrics_cache) > _METRICS_CACHE_MAX:
                for stale in list(self._metrics_cache)[: len(self._metrics_cache) // 2]:
                    self._metrics_cache.pop(stale, None)
        return dict(latest)


_METRICS_CACHE_MAX = 4096
