"""Layer-0 append-only SQLite seq-log primitive.

Extracted from ``molexp.harness.store`` so both ``harness.store`` (audit event log)
and ``molexp.workspace.events`` (the workspace event spine) cite **one**
implementation instead of copying a store (integration.md §2.1 / invariant #1).
Stdlib-only — imports no ``molexp`` business layer — so it is citable from any
layer, exactly like :mod:`molexp.atomicio` / :mod:`molexp.ids`.

Two pieces:

- :func:`open_wal_connection` — a WAL SQLite connection plus a **path-keyed shared
  lock** (two opens on the same resolved path return the *same* lock, so several
  stores sharing one DB file serialize their writes through it).
- :class:`SeqEventStore` — an append-only, per-scope monotonic-``seq`` event table
  over a *shared* connection (it does **not** own the connection, so an events
  store and, say, a lineage store can share one file + lock).

Thread-safety mirrors the original harness contract: the connection is opened with
``check_same_thread=False`` and every use goes through the shared lock, so blocking
writes offloaded onto ``asyncio.to_thread`` workers stay correct.
"""

from __future__ import annotations

import sqlite3
import threading
from os import PathLike
from pathlib import Path
from typing import Literal

__all__ = ["SeqConflictError", "SeqEventStore", "open_wal_connection"]

# Path-keyed registry of per-DB-file locks: two stores opening the same file
# must serialize through the SAME lock, but they construct independent
# connections — so the lock cannot live on the connection.
_locks: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    """Return the shared lock for *path* (one :class:`threading.Lock` per DB file)."""
    key = str(path.resolve())
    with _registry_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


class SeqConflictError(RuntimeError):
    """Raised on a duplicate ``(scope, seq)`` insert into a :class:`SeqEventStore`."""


def open_wal_connection(
    path: str | PathLike[str], *, journal_mode: Literal["WAL", "DELETE"] = "WAL"
) -> tuple[sqlite3.Connection, threading.Lock]:
    """Open (or create) a SQLite database and return it with its shared lock.

    Creates the parent directory if needed; enables ``foreign_keys``; opens
    with ``check_same_thread=False``. Creates **no tables** — callers own
    their schemas (see :class:`SeqEventStore`).

    Args:
        path: The SQLite database file path.
        journal_mode: ``"WAL"`` (default) or ``"DELETE"``. WAL is faster and
            allows concurrent readers, but it needs a shared-memory ``-shm``
            file that NFS and Lustre do not support safely — on those mounts
            it corrupts or hangs, so the rollback journal (``DELETE``), whose
            POSIX locking those filesystems do honour, is the right choice.
            A longer ``busy_timeout`` compensates for the coarser locking.

    Returns:
        A ``(connection, lock)`` pair. The lock is the per-file lock from the
        module registry and MUST guard every use of the connection.
    """
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        resolved,
        isolation_level=None,  # autocommit; callers BEGIN explicitly
        check_same_thread=False,  # connection is serialized by the shared lock
    )
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=" + ("15000" if journal_mode == "DELETE" else "5000"))
    conn.execute("PRAGMA foreign_keys=ON")
    return conn, _lock_for(resolved)


class SeqEventStore:
    """Append-only, per-scope monotonic-``seq`` event table over a shared connection.

    The table shape is fixed (``id`` / ``{scope_column}`` / ``seq`` / ``type`` /
    ``actor`` / ``created_at`` / ``payload_json`` / ``{refs_column}``) with a
    ``UNIQUE({scope_column}, seq)`` index; ``scope_column`` and ``refs_column`` are
    trusted, code-supplied identifiers so a caller can match an existing on-disk
    schema (the harness event log passes ``refs_column="artifact_ids_json"``).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        lock: threading.Lock,
        *,
        table: str,
        scope_column: str,
        refs_column: str = "refs_json",
    ) -> None:
        self._conn = conn
        self._lock = lock
        self._table = table
        self._scope = scope_column
        self._refs = refs_column

    def ensure_schema(self) -> None:
        """Create the table + unique index if absent (idempotent)."""
        with self._lock:
            self._conn.executescript(
                f"CREATE TABLE IF NOT EXISTS {self._table} ("
                "    id TEXT PRIMARY KEY,"
                f"    {self._scope} TEXT NOT NULL,"
                "    seq INTEGER NOT NULL,"
                "    type TEXT NOT NULL,"
                "    actor TEXT NOT NULL,"
                "    created_at TEXT NOT NULL,"
                "    payload_json TEXT NOT NULL,"
                f"    {self._refs} TEXT NOT NULL"
                ");"
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{self._table}_scope_seq "
                f"ON {self._table}({self._scope}, seq);"
                # Covers the ``type=?`` predicate of :meth:`list_rows` (a UI poll
                # for "the last N events of one type" must not scan the scope).
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_scope_type_seq "
                f"ON {self._table}({self._scope}, type, seq);"
            )

    def append(
        self,
        *,
        event_id: str,
        scope_id: str,
        type: str,
        actor: str,
        created_at_iso: str,
        payload_json: str,
        refs_json: str,
        seq: int | None = None,
    ) -> int:
        """Append one row, assigning the next per-scope ``seq`` (or an explicit one).

        Holds the shared lock across the whole ``BEGIN → MAX(seq)+1 → INSERT →
        COMMIT`` read-modify-write so concurrent appends cannot assign the same
        ``(scope, seq)``. A duplicate raises :class:`SeqConflictError`.

        Returns:
            The assigned ``seq``.
        """
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                if seq is None:
                    row = self._conn.execute(
                        f"SELECT COALESCE(MAX(seq), 0) + 1 FROM {self._table} "
                        f"WHERE {self._scope} = ?",
                        (scope_id,),
                    ).fetchone()
                    assigned = int(row[0])
                else:
                    assigned = seq
                self._conn.execute(
                    f"INSERT INTO {self._table} "
                    f"(id, {self._scope}, seq, type, actor, created_at, payload_json, {self._refs}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        scope_id,
                        assigned,
                        type,
                        actor,
                        created_at_iso,
                        payload_json,
                        refs_json,
                    ),
                )
                self._conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._conn.execute("ROLLBACK")
                raise SeqConflictError(
                    f"duplicate (scope={scope_id!r}, seq={seq}) in {self._table}"
                ) from exc
        return assigned

    def list_rows(
        self,
        scope_id: str,
        *,
        type: str | None = None,
        ref: str | None = None,
        newest_first: bool = False,
        limit: int | None = None,
        after_seq: int | None = None,
    ) -> list[tuple]:
        """Return a scope's rows ``(id, scope, seq, type, actor, created_at, payload_json, refs)``.

        Every filter is pushed into SQL so a ``limit=10`` poll over a 100k-row
        timeline materializes ten rows, not all of them. The positional
        no-filter call (``list_rows(scope_id)``) keeps its original contract:
        every row, ordered by ``seq`` ascending.

        Args:
            scope_id: The scope whose rows to return.
            type: Keep only rows of this ``type``.
            ref: Keep only rows whose refs column (a JSON array of ids)
                **contains** exactly this id — ``json_each`` membership, so
                ``"ab"`` never matches ``"abc"``.
            newest_first: ``ORDER BY seq DESC``.
            limit: SQL ``LIMIT`` applied after ordering.
            after_seq: Keep only rows with ``seq > after_seq`` — the change
                cursor a poller passes to fetch only what it has not seen.
        """
        sql = (
            f"SELECT id, {self._scope}, seq, type, actor, created_at, payload_json, "
            f"{self._refs} FROM {self._table} WHERE {self._scope} = ?"
        )
        params: list[object] = [scope_id]
        if type is not None:
            sql += " AND type = ?"
            params.append(type)
        if ref is not None:
            sql += (
                f" AND EXISTS (SELECT 1 FROM json_each({self._table}.{self._refs}) "
                "WHERE json_each.value = ?)"
            )
            params.append(ref)
        if after_seq is not None:
            sql += " AND seq > ?"
            params.append(after_seq)
        sql += " ORDER BY seq DESC" if newest_first else " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def max_seq(self, scope_id: str) -> int:
        """Return the highest ``seq`` in *scope_id* (``0`` when the scope is empty).

        One indexed ``MAX`` — the cheap change cursor a poller compares
        against its last-seen value before deciding whether to re-read.
        """
        with self._lock:
            row = self._conn.execute(
                f"SELECT COALESCE(MAX(seq), 0) FROM {self._table} WHERE {self._scope} = ?",
                (scope_id,),
            ).fetchone()
        return int(row[0])
