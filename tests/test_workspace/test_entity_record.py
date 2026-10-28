"""``molab.workspace.entity_record`` — the single read/write path of a Folder's record.

A Folder's ``index.md`` holds three zones (canonical frontmatter, the derived
``index:`` block, the narrative body). A write replaces the zones it is given
and keeps the others; concurrent writers of different zones never lose one
another's work; a directory that still holds a JSON record is refused.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import cast

import pytest

from molab._typing import JSONValue
from molab.fs import LocalFileSystem
from molab.workspace import Workspace
from molab.workspace.entity_record import (
    KEEP,
    UnmigratedLayoutError,
    read_body,
    read_record,
    read_type,
    write_record,
)
from molab.workspace.errors import UnmigratedLayoutError as ExportedError

_FS = LocalFileSystem()
_CANONICAL: dict[str, JSONValue] = {"type": "workspace.project", "id": "p1", "name": "alpha"}


class TestZones:
    def test_each_zone_is_written_without_touching_the_others(self, tmp_path: Path) -> None:
        write_record(_FS, tmp_path, canonical=_CANONICAL, body="# Alpha\n")
        write_record(_FS, tmp_path, index={"children": [{"name": "e"}]})
        write_record(_FS, tmp_path, body="# Alpha, revised\n")
        write_record(_FS, tmp_path, canonical={**_CANONICAL, "name": "alpha-2"})

        record = read_record(_FS, tmp_path)

        assert record is not None
        assert record.canonical == {**_CANONICAL, "name": "alpha-2"}
        assert record.index == {"children": [{"name": "e"}]}
        assert record.body == "# Alpha, revised\n"

    def test_keep_is_the_default_for_every_zone(self, tmp_path: Path) -> None:
        write_record(_FS, tmp_path, canonical=_CANONICAL, index={"parent": "../../index.md"})
        before = (tmp_path / "index.md").read_bytes()

        write_record(_FS, tmp_path, canonical=KEEP, index=KEEP, body=KEEP)

        assert (tmp_path / "index.md").read_bytes() == before

    def test_an_unchanged_write_leaves_the_file_alone(self, tmp_path: Path) -> None:
        write_record(_FS, tmp_path, canonical=_CANONICAL)
        path = tmp_path / "index.md"
        mtime = path.stat().st_mtime_ns

        write_record(_FS, tmp_path, canonical=dict(_CANONICAL))

        assert path.stat().st_mtime_ns == mtime

    def test_a_plain_narrative_is_all_body_and_no_record(self, tmp_path: Path) -> None:
        (tmp_path / "index.md").write_text("# Hand-written\n\nnotes\n", encoding="utf-8")

        assert read_record(_FS, tmp_path) is None
        assert read_type(_FS, tmp_path) is None
        assert read_body(_FS, tmp_path) == "# Hand-written\n\nnotes\n"

        write_record(_FS, tmp_path, canonical=_CANONICAL)

        record = read_record(_FS, tmp_path)
        assert record is not None
        assert record.body == "# Hand-written\n\nnotes\n"

    def test_a_record_without_type_is_no_record(self, tmp_path: Path) -> None:
        write_record(_FS, tmp_path, canonical={"id": "x"})

        assert read_record(_FS, tmp_path) is None

    def test_read_type_reads_only_the_head(self, tmp_path: Path) -> None:
        write_record(_FS, tmp_path, canonical=_CANONICAL, body="x" * 100_000)

        assert read_type(_FS, tmp_path) == "workspace.project"

    def test_a_missing_directory_has_no_record(self, tmp_path: Path) -> None:
        assert read_record(_FS, tmp_path / "nope") is None
        assert read_body(_FS, tmp_path / "nope") == ""


def _write_body(root: str, directory: str, worker: int, rounds: int) -> None:
    fs = LocalFileSystem()
    for i in range(rounds):
        write_record(fs, directory, body=f"# body {worker}-{i}\n", lock_root=root)


def _write_index(root: str, directory: str, worker: int, rounds: int) -> None:
    fs = LocalFileSystem()
    for i in range(rounds):
        write_record(fs, directory, index={"children": [{"n": f"{worker}-{i}"}]}, lock_root=root)


class TestConcurrency:
    def test_concurrent_writers_never_lose_the_body(self, tmp_path: Path) -> None:
        """Index refreshes racing narrative edits keep a body and a record every time."""
        directory = tmp_path / "projects" / "alpha"
        write_record(_FS, directory, canonical=_CANONICAL, body="# start\n", lock_root=tmp_path)
        ctx = multiprocessing.get_context("fork")
        rounds = 40
        procs = [
            ctx.Process(target=_write_body, args=(str(tmp_path), str(directory), 0, rounds)),
            ctx.Process(target=_write_index, args=(str(tmp_path), str(directory), 1, rounds)),
            ctx.Process(target=_write_index, args=(str(tmp_path), str(directory), 2, rounds)),
        ]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(timeout=60)
            assert proc.exitcode == 0

        record = read_record(_FS, directory)
        assert record is not None
        assert record.canonical == _CANONICAL
        assert record.body == f"# body 0-{rounds - 1}\n"
        children = cast("list[dict[str, str]]", record.index["children"])
        assert children[0]["n"] in {f"1-{rounds - 1}", f"2-{rounds - 1}"}
        assert (tmp_path / ".molab" / "locks").is_dir()


class TestUnmigratedLayout:
    @pytest.mark.parametrize(
        "legacy", ["workspace.json", "project.json", "experiment.json", "run.json", "meta.json"]
    )
    def test_a_legacy_record_without_index_md_is_refused(self, tmp_path: Path, legacy: str) -> None:
        (tmp_path / legacy).write_text('{"id": "x"}', encoding="utf-8")

        with pytest.raises(UnmigratedLayoutError) as caught:
            read_record(_FS, tmp_path)

        assert caught.value.legacy == (legacy,)
        assert "index.md" in str(caught.value)
        assert "molab migrate" not in str(caught.value)

    def test_the_error_is_the_workspace_error(self) -> None:
        assert UnmigratedLayoutError is ExportedError

    def test_a_legacy_workspace_root_refuses_to_open(self, tmp_path: Path) -> None:
        (tmp_path / "workspace.json").write_text('{"id": "lab", "name": "lab"}', encoding="utf-8")

        with pytest.raises(UnmigratedLayoutError):
            Workspace(tmp_path)

    def test_a_legacy_child_refuses_to_list(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path, name="lab")
        ws.materialize()
        legacy = tmp_path / "projects" / "old"
        legacy.mkdir(parents=True)
        (legacy / "project.json").write_text('{"id": "old", "name": "old"}', encoding="utf-8")

        with pytest.raises(UnmigratedLayoutError):
            ws.list_projects()
