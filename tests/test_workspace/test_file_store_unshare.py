"""Appending inside a hard-linked archive must not reach back into its source.

``molab migrate`` builds an archive by hard-linking bulk payload, which makes
it cheap but means a migrated file and its original are the *same* file. An
appender that does not break the link first writes through into the source
tree — which is how an ingest run silently grew a 242-byte file in the archive
into 72 MB in both places.
"""

from __future__ import annotations

import os
from pathlib import Path

from molab.workspace.file_store import FileStore


class TestAppendUnsharesHardLinks:
    def test_append_leaves_the_hard_linked_original_untouched(self, tmp_path: Path) -> None:
        source = tmp_path / "source.jsonl"
        source.write_text("original\n", encoding="utf-8")
        archive = tmp_path / "archive"
        archive.mkdir()
        os.link(source, archive / "source.jsonl")
        assert source.stat().st_nlink == 2

        FileStore(archive).append("source.jsonl", "appended")

        assert source.read_text(encoding="utf-8") == "original\n"
        assert (archive / "source.jsonl").read_text(encoding="utf-8") == "original\nappended\n"
        assert source.stat().st_nlink == 1

    def test_bulk_append_unshares_once_and_keeps_every_line(self, tmp_path: Path) -> None:
        source = tmp_path / "metrics.jsonl"
        source.write_text("first\n", encoding="utf-8")
        archive = tmp_path / "archive"
        archive.mkdir()
        os.link(source, archive / "metrics.jsonl")

        FileStore(archive).append_many("metrics.jsonl", [f"row-{i}" for i in range(3)])

        assert source.read_text(encoding="utf-8") == "first\n"
        assert (archive / "metrics.jsonl").read_text(encoding="utf-8") == (
            "first\nrow-0\nrow-1\nrow-2\n"
        )

    def test_an_unlinked_file_is_appended_in_place(self, tmp_path: Path) -> None:
        """The guard costs nothing when there is no link to break."""
        store = FileStore(tmp_path)
        store.append("solo.jsonl", "a")
        inode = (tmp_path / "solo.jsonl").stat().st_ino
        store.append("solo.jsonl", "b")
        assert (tmp_path / "solo.jsonl").stat().st_ino == inode
        assert (tmp_path / "solo.jsonl").read_text(encoding="utf-8") == "a\nb\n"
