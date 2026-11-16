"""RemoteFS.join must preserve absolute remote roots."""

from __future__ import annotations

from molab.workspace.fs_remote import RemoteFS


class TestRemoteFSJoin:
    def test_join_preserves_absolute_root(self) -> None:
        assert (
            RemoteFS.join("/home/jicli594/work/pinet-quant-raw", "index.md")
            == "/home/jicli594/work/pinet-quant-raw/index.md"
        )
