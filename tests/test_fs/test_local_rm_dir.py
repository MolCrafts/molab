"""``LocalFS.rm`` on a directory without ``recursive`` is ``rmdir``, as on ``RemoteFS``."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.fs import LocalFS


def test_an_empty_directory_is_removed(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    LocalFS().rm(tmp_path / "d")
    assert not (tmp_path / "d").exists()


def test_a_directory_with_content_is_refused(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f").write_text("x")
    with pytest.raises(OSError):
        LocalFS().rm(tmp_path / "d")
    assert (tmp_path / "d" / "f").exists()
