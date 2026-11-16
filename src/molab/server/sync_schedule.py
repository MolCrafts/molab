"""In-process schedule for remote sync rules.

The loop lives only as long as this ``molab serve`` process. On-open rules
run once after the remote root is linked. Interval rules run when they are
due. A mirror never stacks two rsyncs: if a transfer is already running,
that tick is skipped.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from mollog import get_logger

from molab.workspace.sync_rules import (
    SyncBusyError,
    SyncFailedError,
    SyncFilesystem,
    SyncRule,
    SyncRulesError,
    execute_rule,
    interval_due,
    load_rules,
)

logger = get_logger(__name__)

_POLL_SECONDS = 30.0
_registry_lock = threading.Lock()
_schedules: dict[str, SyncSchedule] = {}


class SyncSchedule:
    """One loop for the rules stored under a mirror root."""

    def __init__(
        self,
        fs: SyncFilesystem,
        workspace_root: str,
        *,
        poll_seconds: float = _POLL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fs = fs
        self._root = str(workspace_root)
        self._poll_seconds = poll_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._opened: set[str] = set()
        self._stop = threading.Event()
        self._started = False
        self._thread: threading.Thread | None = None

    @property
    def alive(self) -> bool:
        """True after start, until stop, while the thread is still running."""
        thread = self._thread
        return bool(
            self._started and not self._stop.is_set() and thread is not None and thread.is_alive()
        )

    @property
    def stopped(self) -> bool:
        """True after :meth:`stop` has been asked for."""
        return self._stop.is_set()

    def skip_on_open(self, rule_id: str) -> None:
        """Mark an on-open rule as already run. Tests use this for a fresh loop."""
        self._opened.add(rule_id)

    def start(self) -> None:
        """Start the loop if it is not already running."""
        if self._started and not self._stop.is_set():
            return
        self._stop.clear()
        self._started = True
        self._thread = threading.Thread(
            target=self._loop,
            name="molab-sync-rules",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the loop to exit and wait briefly for it."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def tick(self) -> list[str]:
        """Run every due rule once. Returns the ids that were attempted.

        ``SyncBusyError`` skips the rest of this tick so a transfer already
        in flight is not joined by another one.
        """
        try:
            rules = load_rules(self._fs.mirror_root)
        except SyncRulesError as exc:
            logger.warning(f"sync rules were not read: {exc}")
            return []
        now = self._clock()
        started: list[str] = []
        for rule in rules:
            if not self._due(rule, now):
                continue
            try:
                execute_rule(self._fs, self._root, rule.id, dry_run=False)
            except SyncBusyError:
                return started
            except KeyError:
                continue
            except SyncFailedError as exc:
                logger.warning(f"sync rule {rule.id} failed: {exc}")
            if rule.when == "on-open":
                self._opened.add(rule.id)
            started.append(rule.id)
        return started

    def _due(self, rule: SyncRule, now: datetime) -> bool:
        if rule.when == "manual":
            return False
        if rule.when == "on-open":
            return rule.id not in self._opened
        if rule.when == "interval":
            return interval_due(rule, now)
        return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("sync schedule tick failed")
            if self._stop.wait(self._poll_seconds):
                return


def ensure_sync_schedule(fs: SyncFilesystem, workspace_root: str) -> SyncSchedule:
    """Start the loop for this mirror once per process."""
    key = str(fs.mirror_root)
    with _registry_lock:
        current = _schedules.get(key)
        if current is not None and current._started and not current._stop.is_set():
            return current
        schedule = SyncSchedule(fs, workspace_root)
        _schedules[key] = schedule
        schedule.start()
        return schedule


def stop_sync_schedules() -> None:
    """Stop every loop. Called when the serve process shuts down."""
    with _registry_lock:
        schedules = list(_schedules.values())
        _schedules.clear()
    for schedule in schedules:
        schedule.stop()
