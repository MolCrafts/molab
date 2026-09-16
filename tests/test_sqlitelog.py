"""Layer-0 append-only SQLite seq-log primitive (workspace-event-01-sqlitelog, P0.3).

RED-first: ``molexp.sqlitelog`` does not exist yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.sqlitelog import SeqConflictError, SeqEventStore, open_wal_connection


def _store(tmp_path: Path) -> SeqEventStore:
    conn, lock = open_wal_connection(tmp_path / "db.sqlite")
    store = SeqEventStore(
        conn, lock, table="events", scope_column="run_id", refs_column="refs_json"
    )
    store.ensure_schema()
    return store


def _append(store: SeqEventStore, scope_id: str, i: int, seq: int | None = None) -> int:
    return store.append(
        event_id=f"e-{scope_id}-{i}",
        scope_id=scope_id,
        type="x",
        actor="test",
        created_at_iso="2026-07-01T00:00:00+00:00",
        payload_json="{}",
        refs_json="[]",
        seq=seq,
    )


def test_open_wal_connection(tmp_path: Path) -> None:
    conn, lock = open_wal_connection(tmp_path / "db.sqlite")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    _conn2, lock2 = open_wal_connection(tmp_path / "db.sqlite")
    assert lock2 is lock  # same resolved path → same lock instance


def test_append_and_list_monotonic_seq(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert [_append(store, "r1", i) for i in range(3)] == [1, 2, 3]
    assert _append(store, "r2", 0) == 1  # independent seq per scope
    rows = store.list_rows("r1")
    assert [row[2] for row in rows] == [1, 2, 3]  # seq column, ordered
    assert store.list_rows("r1")[0][0] == "e-r1-0"  # id column
    assert len(store.list_rows("r2")) == 1


def test_duplicate_seq_conflict(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _append(store, "r1", 0, seq=5)
    with pytest.raises(SeqConflictError):
        _append(store, "r1", 1, seq=5)


# ── SQL-side filtering (P1-1e): predicates, ordering, limit, cursor ─────────


def _append_typed(store: SeqEventStore, scope_id: str, i: int, *, type: str, refs_json: str) -> int:
    return store.append(
        event_id=f"e-{scope_id}-{i}",
        scope_id=scope_id,
        type=type,
        actor="test",
        created_at_iso="2026-07-01T00:00:00+00:00",
        payload_json="{}",
        refs_json=refs_json,
    )


class TestListRowsFilters:
    """Every ``list_rows`` filter is evaluated in SQL, never post-hoc in Python."""

    def test_positional_call_keeps_original_contract(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(3):
            _append(store, "r1", i)
        assert [row[2] for row in store.list_rows("r1")] == [1, 2, 3]

    def test_type_filter(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _append_typed(store, "s", 0, type="a", refs_json="[]")
        _append_typed(store, "s", 1, type="b", refs_json="[]")
        _append_typed(store, "s", 2, type="a", refs_json="[]")
        assert [row[2] for row in store.list_rows("s", type="a")] == [1, 3]

    def test_ref_filter_is_exact_json_membership(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        _append_typed(store, "s", 0, type="x", refs_json='["ab"]')
        _append_typed(store, "s", 1, type="x", refs_json='["abc"]')
        _append_typed(store, "s", 2, type="x", refs_json='["zz", "ab"]')
        # "ab" must not match "abc" (a LIKE would), and membership anywhere in the array counts.
        assert [row[2] for row in store.list_rows("s", ref="ab")] == [1, 3]
        assert [row[2] for row in store.list_rows("s", ref="abc")] == [2]
        assert store.list_rows("s", ref="a") == []

    def test_newest_first_and_limit(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(5):
            _append(store, "s", i)
        assert [row[2] for row in store.list_rows("s", newest_first=True, limit=2)] == [5, 4]
        assert [row[2] for row in store.list_rows("s", limit=2)] == [1, 2]

    def test_after_seq_cursor(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(5):
            _append(store, "s", i)
        assert [row[2] for row in store.list_rows("s", after_seq=3)] == [4, 5]
        assert store.list_rows("s", after_seq=5) == []

    def test_filters_combine(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(6):
            _append_typed(
                store, "s", i, type="a" if i % 2 else "b", refs_json='["k"]' if i < 4 else "[]"
            )
        rows = store.list_rows("s", type="a", ref="k", newest_first=True, limit=1, after_seq=1)
        assert [row[2] for row in rows] == [4]

    def test_limit_bounds_rows_fetched(self, tmp_path: Path) -> None:
        """The LIMIT is in the statement — the driver hands back only *limit* rows."""
        store = _store(tmp_path)
        for i in range(50):
            _append(store, "s", i)
        assert len(store.list_rows("s", limit=7)) == 7


class TestMaxSeq:
    def test_empty_scope_is_zero(self, tmp_path: Path) -> None:
        assert _store(tmp_path).max_seq("nope") == 0

    def test_tracks_appends(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        for i in range(3):
            _append(store, "s", i)
        assert store.max_seq("s") == 3
        assert store.max_seq("other") == 0


def test_ensure_schema_adds_scope_type_seq_index(tmp_path: Path) -> None:
    store = _store(tmp_path)
    names = {row[1] for row in store._conn.execute("PRAGMA index_list(events)").fetchall()}
    assert "idx_events_scope_type_seq" in names
    store.ensure_schema()  # idempotent


class TestJournalMode:
    """WAL is the default; NFS/Lustre need the rollback journal instead."""

    def test_default_is_wal(self, tmp_path: Path) -> None:
        conn, _lock = open_wal_connection(tmp_path / "a.sqlite")
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode.lower() == "wal"

    def test_delete_mode_is_honoured(self, tmp_path: Path) -> None:
        # WAL's -shm shared-memory file is unsafe on NFS/Lustre, so those
        # mounts must be able to opt into the rollback journal.
        conn, _lock = open_wal_connection(tmp_path / "b.sqlite", journal_mode="DELETE")
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode.lower() == "delete"

    def test_delete_mode_gets_a_longer_busy_timeout(self, tmp_path: Path) -> None:
        # Coarser locking means more contention, so waits must be tolerated.
        wal, _ = open_wal_connection(tmp_path / "c.sqlite")
        delete, _ = open_wal_connection(tmp_path / "d.sqlite", journal_mode="DELETE")
        try:
            wal_timeout = wal.execute("PRAGMA busy_timeout").fetchone()[0]
            delete_timeout = delete.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            wal.close()
            delete.close()
        assert delete_timeout > wal_timeout

    def test_store_works_under_delete_mode(self, tmp_path: Path) -> None:
        conn, lock = open_wal_connection(tmp_path / "e.sqlite", journal_mode="DELETE")
        try:
            store = SeqEventStore(conn, lock, table="events", scope_column="scope")
            store.ensure_schema()
            seq = store.append(
                event_id="e1",
                scope_id="s1",
                type="run.created",
                actor="test",
                created_at_iso="2026-01-01T00:00:00",
                payload_json="{}",
                refs_json="[]",
            )
            assert seq == 1
            assert len(store.list_rows("s1")) == 1
        finally:
            conn.close()
