"""Experiment ``scratch/`` (D90): never a child, gitignored, flagged, emptied by age."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.history import GitHistory, default_gitignore, managed_ignore_rules
from molab.workspace.naming import SCRATCH_CONTAINER
from molab.workspace.scratch import apply_scratch_clean, newest_mtime, plan_scratch_clean
from tests.support.records import read_index_block


def _experiment(tmp_path: Path):
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    exp = ws.add_project("alpha").add_experiment("sweep")
    exp.add_run(params={"t": 1})
    return ws, exp


def _age(path: Path, days: float) -> None:
    stamp = time.time() - days * 86400
    for item in [path, *path.rglob("*")] if path.is_dir() else [path]:
        os.utime(item, (stamp, stamp))


class TestScratchTier:
    def test_scratch_is_never_a_child(self, tmp_path: Path) -> None:
        from molab.workspace.folder import Folder

        _ws, exp = _experiment(tmp_path)
        scratch = Path(exp.resolve()) / SCRATCH_CONTAINER
        scratch.mkdir()
        (scratch / "index.md").write_text("---\ntype: workspace.run\n---\n")

        assert [run._name for run in exp.list_runs()] == ["t=1"]
        # The generic scan of the experiment directory skips scratch/ even when
        # something in it looks like a record.
        assert all(child._name != SCRATCH_CONTAINER for child in Folder.children(exp))

    def test_the_experiment_index_flags_scratch(self, tmp_path: Path) -> None:
        _ws, exp = _experiment(tmp_path)
        assert read_index_block(exp.resolve())["scratch"] is False

        (Path(exp.resolve()) / SCRATCH_CONTAINER).mkdir()
        from molab.workspace.index_projection import refresh_index

        refresh_index(exp, parent=False)
        assert read_index_block(exp.resolve())["scratch"] is True

    def test_the_default_ignore_rules_cover_scratch(self) -> None:
        assert "**/experiments/*/scratch/" in default_gitignore().splitlines()
        assert "**/experiments/*/scratch/" in managed_ignore_rules()


class TestEnsureIgnoreRules:
    def test_an_absent_file_is_written_whole(self, tmp_path: Path) -> None:
        added = GitHistory(tmp_path).ensure_ignore_rules()
        assert (tmp_path / ".gitignore").read_text() == default_gitignore()
        assert added == managed_ignore_rules()

    def test_missing_rules_are_appended_and_the_rest_kept(self, tmp_path: Path) -> None:
        ignore = tmp_path / ".gitignore"
        ignore.write_text("# mine\n.molab/\nmy-big-dir/")

        added = GitHistory(tmp_path).ensure_ignore_rules()

        text = ignore.read_text()
        assert text.startswith("# mine\n.molab/\nmy-big-dir/\n")
        assert ".molab/" not in added
        assert "**/experiments/*/scratch/" in added
        assert set(managed_ignore_rules()) <= {line.strip() for line in text.splitlines()}
        assert GitHistory(tmp_path).ensure_ignore_rules() == ()
        assert ignore.read_text() == text


class TestScratchClean:
    def test_newest_mtime_looks_inside_a_directory(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        (deep / "f").write_text("x")
        _age(tmp_path / "a", 30)
        (deep / "g").write_text("fresh")
        os.utime(tmp_path / "a", (time.time() - 30 * 86400,) * 2)

        from molab.workspace.fs_local import LocalFS

        assert newest_mtime(LocalFS(), str(tmp_path / "a")) > time.time() - 60

    def test_newest_mtime_stops_at_the_first_newer_entry(self, tmp_path: Path) -> None:
        from molab.workspace.fs_local import LocalFS

        class Counting(LocalFS):
            calls = 0

            def ls(self, path: str, **kw: bool) -> list:  # type: ignore[override]
                Counting.calls += 1
                return LocalFS.ls(path, **kw)

        for name in ("x", "y", "z"):
            (tmp_path / "a" / name / "deep").mkdir(parents=True)
        cutoff = time.time() - 60
        assert newest_mtime(Counting(), str(tmp_path / "a"), stop_at=cutoff) >= cutoff
        assert Counting.calls == 0  # the entry itself is already newer

        _age(tmp_path / "a", 30)
        assert newest_mtime(Counting(), str(tmp_path / "a"), stop_at=cutoff) < cutoff
        assert Counting.calls == 7  # a stale entry is still walked in full

    def test_plan_selects_old_top_level_entries_and_writes_nothing(self, tmp_path: Path) -> None:
        ws, exp = _experiment(tmp_path)
        scratch = Path(exp.resolve()) / SCRATCH_CONTAINER
        (scratch / "old-dir").mkdir(parents=True)
        (scratch / "old-dir" / "x.dat").write_text("x")
        (scratch / "old.py").write_text("x")
        (scratch / "new.py").write_text("x")
        _age(scratch / "old-dir", 10)
        _age(scratch / "old.py", 10)
        before = sorted(p.name for p in scratch.iterdir())

        plan = plan_scratch_clean(ws, older_than=timedelta(days=7))

        assert sorted(e.path.rsplit("/", 1)[-1] for e in plan.entries) == ["old-dir", "old.py"]
        assert {e.experiment for e in plan.entries} == {"projects/alpha/experiments/sweep"}
        assert sorted(p.name for p in scratch.iterdir()) == before

    def test_apply_removes_exactly_the_plan_and_skips_a_touched_entry(self, tmp_path: Path) -> None:
        ws, exp = _experiment(tmp_path)
        scratch = Path(exp.resolve()) / SCRATCH_CONTAINER
        scratch.mkdir()
        for name in ("a.py", "b.py", "keep.py"):
            (scratch / name).write_text("x")
        _age(scratch / "a.py", 10)
        _age(scratch / "b.py", 10)
        plan = plan_scratch_clean(ws, older_than=timedelta(days=7))
        (scratch / "b.py").write_text("touched after planning")

        removed = apply_scratch_clean(ws, plan)

        assert removed == 1
        assert sorted(p.name for p in scratch.iterdir()) == ["b.py", "keep.py"]
        assert plan.cutoff < datetime.now(UTC)

    def test_a_plan_can_be_limited_to_some_experiments(self, tmp_path: Path) -> None:
        ws, exp = _experiment(tmp_path)
        other = ws.get_project("alpha").add_experiment("other")
        for target in (exp, other):
            (Path(target.resolve()) / SCRATCH_CONTAINER).mkdir()
            (Path(target.resolve()) / SCRATCH_CONTAINER / "x").write_text("x")
            _age(Path(target.resolve()) / SCRATCH_CONTAINER / "x", 10)

        plan = plan_scratch_clean(ws, older_than=timedelta(days=1), experiments=[other])

        assert [e.experiment for e in plan.entries] == ["projects/alpha/experiments/other"]
