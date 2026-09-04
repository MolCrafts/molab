"""RemoteFileSystem.join must preserve absolute remote roots."""

from __future__ import annotations

from molexp.workspace.fs_remote import RemoteFileSystem


class TestRemoteFileSystemJoin:
    def test_join_preserves_absolute_root(self) -> None:
        assert (
            RemoteFileSystem.join("/home/jicli594/work/pinet-quant-raw", "workspace.json")
            == "/home/jicli594/work/pinet-quant-raw/workspace.json"
        )
