"""Workspace surface added for agent paths: ``folder_at``, ``index_section``, adopt ``source=``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.index_projection import sync_index
from tests.support.records import read_index_block


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path / "lab")
    workspace.materialize()
    workspace.add_project("alpha").add_experiment("sweep").add_run(params={"t": 1})
    return workspace


class TestFolderAt:
    def test_each_level_directory_resolves_to_its_folder(self, ws: Workspace) -> None:
        exp = ws.get_project("alpha").get_experiment("sweep")
        run = exp.list_runs()[0]

        assert ws.folder_at(ws.resolve()) is ws
        for folder in (ws.get_project("alpha"), exp, run):
            found = ws.folder_at(folder.resolve())
            assert type(found) is type(folder)
            assert found is not None and found.id == folder.id

    def test_a_non_level_directory_is_none(self, ws: Workspace, tmp_path: Path) -> None:
        exp = Path(str(ws.get_project("alpha").get_experiment("sweep").resolve()))
        run = next(exp.glob("runs/*"))
        (exp / "scratch").mkdir()
        for path in (exp / "runs", run / "executions", exp / "scratch", tmp_path, exp / "nope"):
            assert ws.folder_at(path) is None

    def test_a_symlinked_spelling_of_the_root_still_matches(
        self, ws: Workspace, tmp_path: Path
    ) -> None:
        link = tmp_path / "link"
        link.symlink_to(str(ws.resolve()))
        found = ws.folder_at(link / "projects" / "alpha")
        assert found is not None and found.id == ws.get_project("alpha").id


class TestIndexSection:
    def test_a_section_reads_back_and_survives_a_refresh(self, ws: Workspace) -> None:
        project = ws.get_project("alpha")
        assert project.index_section("notes") is None

        project.set_index_section("notes", [{"path": "a.md"}])
        sync_index(ws)

        assert project.index_section("notes") == [{"path": "a.md"}]
        assert read_index_block(project.resolve())["notes"] == [{"path": "a.md"}]

    def test_a_reserved_or_malformed_key_is_refused(self, ws: Workspace) -> None:
        with pytest.raises(ValueError, match="reserved"):
            ws.index_section("children")
        with pytest.raises(ValueError, match="must match"):
            ws.index_section("Bad-Key")


class TestAdoptSource:
    def test_source_files_move_into_source(self, ws: Workspace, tmp_path: Path) -> None:
        run = ws.get_project("alpha").get_experiment("sweep").list_runs()[0]
        job = tmp_path / "job"
        job.mkdir()
        (job / "md.py").write_text("print('md')\n")
        (job / "traj.dat").write_text("x")
        now = datetime.now(UTC)

        execution = run.adopt_execution(
            started_at=now,
            finished_at=now,
            products={"md": str(job / "traj.dat")},
            source=[str(job / "md.py")],
        )

        attempt = Path(str(run.resolve())) / "executions" / execution.id
        assert (attempt / "source" / "md.py").read_text() == "print('md')\n"
        assert not (job / "md.py").exists()
        assert "source/md.py" in {ref.rel_path for ref in execution.evidence}
        assert ws.validate().ok, ws.validate().violations
