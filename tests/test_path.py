"""Tests for :class:`molab.Path` — cross-host POSIX path primitive."""

from __future__ import annotations

import pickle

import pytest

from molab import Path


class TestPathArithmetic:
    """The ergonomic win over ``str`` — ``/``, ``.parent``, ``.name``, etc."""

    def test_truediv_with_str(self) -> None:
        p = Path("/scratch") / "user"
        assert isinstance(p, Path)
        assert str(p) == "/scratch/user"

    def test_parent(self) -> None:
        assert Path("/a/b/c").parent == Path("/a/b")
        assert isinstance(Path("/a/b/c").parent, Path)


class TestPickle:
    """Persistence — subclassed PurePath must survive a pickle round-trip."""

    def test_pickle_roundtrip(self) -> None:
        original = Path("/scratch/user/run_0")
        restored = pickle.loads(pickle.dumps(original))
        assert restored == original
        assert isinstance(restored, Path)


class TestLocalIO:
    """I/O methods delegate to :class:`pathlib.Path` for the local filesystem."""

    def test_mkdir_and_iterdir(self, tmp_path) -> None:
        root = Path(str(tmp_path / "tree"))
        root.mkdir(parents=True)
        (root / "a").write_text("a")
        (root / "b").write_text("b")
        names = sorted(child.name for child in root.iterdir())
        assert names == ["a", "b"]
        for child in root.iterdir():
            assert isinstance(child, Path)


class TestSlots:
    """``__slots__ = ()`` prevents accidental attribute attachment."""

    def test_cannot_set_arbitrary_attr(self) -> None:
        p = Path("/a")
        with pytest.raises(AttributeError):
            p.arbitrary_attr = "boom"  # type: ignore[attr-defined]
