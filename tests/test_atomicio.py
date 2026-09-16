"""Unit tests for the cross-layer ``molexp.atomicio`` primitive module.

``molexp.atomicio`` holds the atomic write helpers and the advisory
file lock — promoted out of ``molexp.workspace`` (okf-01-01) so the
``molexp.knowledge`` bottom layer can cite them without importing
workspace. These tests pin behavior + the layer-independence bar.
"""

from __future__ import annotations

import ast
import errno
import json
import os
import threading
import time
from pathlib import Path

import pytest

import molexp.atomicio as atomicio
from molexp.atomicio import (
    FileLockTimeoutError,
    atomic_write_json,
    atomic_write_text,
    file_lock,
)


def test_atomic_write_json_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "data.json"
    atomic_write_json(target, {"a": 1, "b": [2, 3]})
    assert json.loads(target.read_text()) == {"a": 1, "b": [2, 3]}


def test_atomic_write_text_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "note.md"
    atomic_write_text(target, "# hi\nbody\n")
    assert target.read_text() == "# hi\nbody\n"


def test_atomic_write_json_failure_leaves_original_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data.json"
    atomic_write_json(target, {"ok": True})
    original = target.read_text()

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(atomicio.json, "dump", boom)
    with pytest.raises(RuntimeError):
        atomic_write_json(target, {"ok": False})

    # Original intact, no leftover temp files in the dir.
    assert target.read_text() == original
    leftovers = [p for p in tmp_path.iterdir() if p.name != "data.json"]
    assert leftovers == []


def test_file_lock_enter_exit_without_contention(tmp_path: Path) -> None:
    lock = tmp_path / "run.json.lock"
    with file_lock(lock):
        pass  # acquired + released without error
    assert lock.exists()  # sidecar created, never deleted


def test_file_lock_times_out_when_held(tmp_path: Path) -> None:
    lock = tmp_path / "run.json.lock"
    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with file_lock(lock):
            held.set()
            release.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert held.wait(5)
        with pytest.raises(FileLockTimeoutError), file_lock(lock, timeout=0.1):
            pass
    finally:
        release.set()
        t.join(5)


def test_file_lock_degrades_to_noop_without_fcntl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(atomicio, "_HAS_FCNTL", False)
    lock = tmp_path / "run.json.lock"
    # No lock taken, but the context manager still yields cleanly.
    with file_lock(lock):
        pass


def test_source_imports_no_workspace_or_upstream_layer() -> None:
    """The primitive must not import workspace or any upstream layer.

    Asserted at the AST level on the module's own source — the
    enforceable layer-independence invariant. (A runtime ``sys.modules``
    probe is confounded because importing any ``molexp.X`` submodule runs
    the eager ``molexp/__init__.py``, which loads workspace.) This mirrors
    ``tests/test_workspace/test_import_guard.py``.
    """
    forbidden = (
        "molexp.workspace",
        "molexp.workflow",
        "molexp.agent",
        "molexp.harness",
        "molexp.server",
        "molexp.cli",
        "molexp.plugins",
        "molexp.sweep",
    )
    source = Path(atomicio.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith(forbidden)]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(forbidden):
            offenders.append(node.module)
    assert offenders == [], f"molexp.atomicio imports forbidden modules: {offenders}"


class TestLockBackends:
    """Backend selection, and the errno distinction that Lustre depends on."""

    def test_o_excl_backend_acquires_and_releases(self, tmp_path: Path) -> None:
        with file_lock(tmp_path / "a.lock", backend="o_excl"):
            assert (tmp_path / "a.lock.excl").exists()
        assert not (tmp_path / "a.lock.excl").exists()

    def test_none_backend_is_a_noop(self, tmp_path: Path) -> None:
        with file_lock(tmp_path / "b.lock", backend="none"):
            pass
        assert not (tmp_path / "b.lock").exists()

    def test_o_excl_contention_times_out(self, tmp_path: Path) -> None:
        (tmp_path / "c.lock.excl").touch()
        with (
            pytest.raises(FileLockTimeoutError),
            file_lock(tmp_path / "c.lock", backend="o_excl", timeout=0.1),
        ):
            pass

    def test_o_excl_breaks_an_abandoned_lock(self, tmp_path: Path) -> None:
        marker = tmp_path / "d.lock.excl"
        marker.touch()
        old = time.time() - 3600
        os.utime(marker, (old, old))

        with file_lock(tmp_path / "d.lock", backend="o_excl", timeout=0.1):
            pass  # A crashed holder must not wedge the workspace forever.

    def test_unsupported_flock_falls_back_without_spinning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Lustre without -o flock raises ENOSYS. Treating that as contention
        # (the old behaviour) burned the whole timeout and then reported a
        # conflict that did not exist.
        import fcntl

        def unsupported(fd, op):
            raise OSError(errno.ENOSYS, "function not implemented")

        monkeypatch.setattr(fcntl, "flock", unsupported)
        monkeypatch.setattr(atomicio, "_warned_unsupported", False)

        started = time.monotonic()
        with file_lock(tmp_path / "e.lock", timeout=5.0):
            pass
        elapsed = time.monotonic() - started

        assert elapsed < 1.0, f"fallback must be immediate, took {elapsed:.2f}s"

    def test_contended_flock_still_times_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fcntl

        def contended(fd, op):
            raise OSError(errno.EAGAIN, "resource temporarily unavailable")

        monkeypatch.setattr(fcntl, "flock", contended)

        with pytest.raises(FileLockTimeoutError), file_lock(tmp_path / "f.lock", timeout=0.1):
            pass

    def test_unexpected_errno_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fcntl

        def broken(fd, op):
            raise OSError(errno.EIO, "I/O error")

        monkeypatch.setattr(fcntl, "flock", broken)

        with pytest.raises(OSError, match="I/O error"), file_lock(tmp_path / "g.lock", timeout=0.1):
            pass

    def test_fallback_still_serializes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fcntl

        def unsupported(fd, op):
            raise OSError(errno.ENOSYS, "no")

        monkeypatch.setattr(fcntl, "flock", unsupported)
        monkeypatch.setattr(atomicio, "_warned_unsupported", False)

        with (
            file_lock(tmp_path / "h.lock", timeout=0.2),
            pytest.raises(FileLockTimeoutError),
            file_lock(tmp_path / "h.lock", timeout=0.1),
        ):
            pass
