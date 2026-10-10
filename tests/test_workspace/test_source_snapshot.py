"""Per-execution source capture — entrypoint + first-party local-import closure."""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from molab.ids import compute_content_hash


def _write(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


# --- arch-own-02b: manifest first, then a verified copy per execution -------

_NOW = datetime(2026, 6, 17, 13, 0, tzinfo=UTC)


def _closure_fixture(tmp_path: Path) -> Path:
    """``src/entry.py`` importing first-party ``helper`` and stdlib ``json``."""
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "entry.py", "import helper\nimport json\n")
    _write(src / "helper.py", "VALUE = 1\n")
    return src


def _listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=30
    )
    return done.stdout.strip()


class TestSourceManifest:
    def test_names_the_entrypoint_first_then_the_closure(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.entrypoint == "entry.py"
        assert [f.name for f in m.files] == ["entry.py", "helper.py"]

    def test_closure_is_transitive_and_excludes_non_local_imports(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = tmp_path / "src"
        src.mkdir()
        _write(src / "helper.py", "VALUE = 1\n")
        _write(src / "deep.py", "import helper\nX = helper.VALUE\n")
        _write(src / "entry.py", "import deep\nfrom os import path\nimport numpy as _np\n")

        m = source_manifest(src / "entry.py", now=_NOW)

        # entry + transitive first-party (deep -> helper); stdlib (os) and
        # third-party (numpy) have no sibling .py and are excluded.
        assert {f.name for f in m.files} == {"entry.py", "deep.py", "helper.py"}

    def test_locator_is_the_resolved_entrypoint(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.locator == str((src / "entry.py").resolve())

    def test_digests_are_of_the_originals(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        for f in m.files:
            assert f.sha256.startswith("sha256:")
            assert f.sha256 == compute_content_hash(src / f.name)

    def test_captured_at_is_the_injected_now(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.captured_at == _NOW

    def test_outside_a_repository_vcs_state_is_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace.source_snapshot import source_manifest

        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.vcs_commit is None
        assert m.vcs_dirty is None

    @pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
    def test_inside_a_repository_records_commit_and_dirty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace.source_snapshot import source_manifest

        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        src = _closure_fixture(tmp_path)
        _git(src, "init", "-q")
        _git(src, "config", "user.name", "molab-test")
        _git(src, "config", "user.email", "molab-test@example.invalid")
        _git(src, "config", "commit.gpgsign", "false")
        _git(src, "add", "entry.py", "helper.py")
        _git(src, "commit", "-q", "-m", "init")
        head = _git(src, "rev-parse", "HEAD")

        clean = source_manifest(src / "entry.py", now=_NOW)

        assert re.fullmatch(r"[0-9a-f]{40}", head)
        assert clean.vcs_commit == head
        assert clean.vcs_dirty is False

        _write(src / "helper.py", "VALUE = 2\n")
        dirty = source_manifest(src / "entry.py", now=_NOW)

        assert dirty.vcs_commit == head
        assert dirty.vcs_dirty is True

    def test_missing_git_binary_yields_unknown_vcs_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)

        def no_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("git")

        monkeypatch.setattr(subprocess, "run", no_git)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.vcs_commit is None
        assert m.vcs_dirty is None

    def test_missing_entrypoint_raises_file_not_found(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import source_manifest

        with pytest.raises(FileNotFoundError):
            source_manifest(tmp_path / "absent.py", now=_NOW)

    def test_writes_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from molab.workspace.source_snapshot import source_manifest

        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        src = _closure_fixture(tmp_path)
        before = _listing(tmp_path)

        source_manifest(src / "entry.py", now=_NOW)

        assert _listing(tmp_path) == before

    def test_unreadable_closure_file_raises_source_capture_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        from molab.workspace.source_snapshot import SourceCaptureError, source_manifest

        if os.geteuid() == 0:
            pytest.skip("root reads chmod-000 files")
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        src = _closure_fixture(tmp_path)
        helper = src / "helper.py"
        helper.chmod(0)
        try:
            with pytest.raises(SourceCaptureError, match=r"helper\.py"):
                source_manifest(src / "entry.py", now=_NOW)
        finally:
            helper.chmod(0o644)

    @pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
    def test_inherited_git_dir_does_not_redirect_the_query(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace.source_snapshot import source_manifest

        other = tmp_path / "other"
        other.mkdir()
        _git(other, "init", "-q")
        _git(other, "config", "user.name", "molab-test")
        _git(other, "config", "user.email", "molab-test@example.invalid")
        _git(other, "config", "commit.gpgsign", "false")
        _write(other / "x.txt", "x\n")
        _git(other, "add", "x.txt")
        _git(other, "commit", "-q", "-m", "init")
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(other))
        monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
        src = _closure_fixture(tmp_path)

        m = source_manifest(src / "entry.py", now=_NOW)

        assert m.vcs_commit is None
        assert m.vcs_dirty is None

    def test_git_query_is_non_interactive_and_skips_fsmonitor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace.source_snapshot import source_manifest

        src = _closure_fixture(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        monkeypatch.setenv("GIT_DIR", "/nonexistent")
        calls: list[tuple[list[str], dict[str, object]]] = []

        def spy(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 128, "", "")

        monkeypatch.setattr(subprocess, "run", spy)

        source_manifest(src / "entry.py", now=_NOW)

        assert calls
        for argv, kwargs in calls:
            assert "core.fsmonitor=false" in argv
            assert kwargs["stdin"] is subprocess.DEVNULL
            env = kwargs["env"]
            assert isinstance(env, dict)
            assert "GIT_DIR" not in env
            assert env["GIT_CEILING_DIRECTORIES"] == str(tmp_path)


class TestCopySources:
    def test_copies_are_byte_identical_under_source(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import copy_sources, source_manifest

        src = _closure_fixture(tmp_path)
        execution_dir = tmp_path / "e01"
        m = source_manifest(src / "entry.py", now=_NOW)

        copy_sources(m, execution_dir)

        for name in ("entry.py", "helper.py"):
            assert (execution_dir / "source" / name).read_bytes() == (src / name).read_bytes()

    def test_original_edited_after_the_manifest_raises(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import (
            SourceCaptureError,
            copy_sources,
            source_manifest,
        )

        src = _closure_fixture(tmp_path)
        m = source_manifest(src / "entry.py", now=_NOW)
        _write(src / "helper.py", "VALUE = 22\n")

        with pytest.raises(SourceCaptureError):
            copy_sources(m, tmp_path / "e01")

    def test_original_deleted_after_the_manifest_raises(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import (
            SourceCaptureError,
            copy_sources,
            source_manifest,
        )

        src = _closure_fixture(tmp_path)
        m = source_manifest(src / "entry.py", now=_NOW)
        (src / "helper.py").unlink()

        with pytest.raises(SourceCaptureError):
            copy_sources(m, tmp_path / "e01")

    def test_second_call_overwrites_with_the_same_bytes(self, tmp_path: Path) -> None:
        from molab.workspace.source_snapshot import copy_sources, source_manifest

        src = _closure_fixture(tmp_path)
        execution_dir = tmp_path / "e01"
        m = source_manifest(src / "entry.py", now=_NOW)

        copy_sources(m, execution_dir)
        first = {p.name: p.read_bytes() for p in (execution_dir / "source").iterdir()}
        copy_sources(m, execution_dir)
        second = {p.name: p.read_bytes() for p in (execution_dir / "source").iterdir()}

        assert second == first
        assert set(first) == {"entry.py", "helper.py"}
