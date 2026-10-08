"""Tests for sidecar-backed dataset preview.

Host owns discovery + frame cap. The molpy plugin owns the reader interface
and the XYZ encoding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.plugins.molpy.preview import FrameReader
from molexp.server.preview import (
    NoReaderInSidecarError,
    PreviewReaderError,
    PreviewSidecarNotFoundError,
    frames_to_extxyz,
    load_preview,
    preview_frames,
    resolve_sidecar,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "fake_sidecar.py"

_NO_READER_SRC = "VALUE = 42\n"
_NOT_CALLABLE_SRC = "READER = 42\n"
_NOT_A_READER_SRC = "READER = str\n"
_BROKEN_SRC = "raise RuntimeError('sidecar boom')\n"
# A dataset molpy reads, under an extension molab does not know: the sidecar
# names molpy's per-format reader and nothing else.
_PER_FORMAT_SRC = "import molpy as mp\n\nREADER = mp.io.xyz.XyzReader\n"
_TWO_XYZ_FRAMES = (
    "2\nProperties=species:S:1:pos:R:3\nC 0 0 0\nO 1 0 0\n"
    "2\nProperties=species:S:1:pos:R:3\nC 0 0 0\nO 2 0 0\n"
)


def _make_sidecar_dataset(
    dir_path: Path,
    *,
    stem: str = "qm9",
    ext: str = ".bin",
    content: str = "fake dataset content",
    sidecar_src: str | None = None,
) -> Path:
    dataset = dir_path / f"{stem}{ext}"
    dataset.write_text(content, encoding="utf-8")
    sidecar = dir_path / f"{stem}.py"
    sidecar.write_text(
        _FIXTURE.read_text(encoding="utf-8") if sidecar_src is None else sidecar_src,
        encoding="utf-8",
    )
    return dataset


class TestSidecarPreview:
    def test_resolve_does_not_import_the_sidecar(self, tmp_path, monkeypatch):
        sentinel = tmp_path / "import.sentinel"
        monkeypatch.setenv("MOLEXP_TEST_IMPORT_SENTINEL", str(sentinel))

        dataset = _make_sidecar_dataset(tmp_path)
        info = resolve_sidecar(dataset)

        assert info is not None
        assert info.sidecar_path == tmp_path / "qm9.py"
        assert not sentinel.exists(), "discovery must not execute the sidecar module body"

    def test_load_runs_body_but_not_main_guard(self, tmp_path, monkeypatch):
        import_sentinel = tmp_path / "import.sentinel"
        main_sentinel = tmp_path / "main.sentinel"
        monkeypatch.setenv("MOLEXP_TEST_IMPORT_SENTINEL", str(import_sentinel))
        monkeypatch.setenv("MOLEXP_TEST_MAIN_SENTINEL", str(main_sentinel))

        dataset = _make_sidecar_dataset(tmp_path)
        reader = load_preview(dataset)

        assert isinstance(reader, FrameReader)
        assert import_sentinel.exists(), "explicit load must execute the module body"
        assert not main_sentinel.exists(), "explicit load must not run the __main__ guard"

    def test_a_sidecar_can_name_a_molpy_per_format_reader(self, tmp_path):
        dataset = _make_sidecar_dataset(
            tmp_path, content=_TWO_XYZ_FRAMES, sidecar_src=_PER_FORMAT_SRC
        )
        frames = preview_frames(dataset)

        assert len(frames) == 2
        assert list(frames[1]["atoms"]["x"]) == [0.0, 2.0]

    def test_load_without_reader_raises_no_reader(self, tmp_path):
        dataset = _make_sidecar_dataset(tmp_path, sidecar_src=_NO_READER_SRC)
        with pytest.raises(NoReaderInSidecarError):
            load_preview(dataset)

    @pytest.mark.parametrize("sidecar_src", [_NOT_CALLABLE_SRC, _NOT_A_READER_SRC])
    def test_load_rejects_what_is_not_a_reader(self, tmp_path, sidecar_src):
        dataset = _make_sidecar_dataset(tmp_path, sidecar_src=sidecar_src)
        with pytest.raises(PreviewReaderError):
            load_preview(dataset)

    def test_load_broken_sidecar_raises_reader_error(self, tmp_path):
        dataset = _make_sidecar_dataset(tmp_path, sidecar_src=_BROKEN_SRC)
        with pytest.raises(PreviewReaderError):
            load_preview(dataset)

    def test_load_missing_sidecar_raises_not_found(self, tmp_path):
        dataset = tmp_path / "plain.bin"
        dataset.write_bytes(b"x")
        with pytest.raises(PreviewSidecarNotFoundError):
            load_preview(dataset)

    def test_preview_frames_caps_at_host_limit(self, tmp_path):
        dataset = _make_sidecar_dataset(tmp_path)
        assert len(preview_frames(dataset, limit=3)) == 3

    def test_preview_frames_stops_at_the_last_frame(self, tmp_path):
        dataset = _make_sidecar_dataset(tmp_path)
        assert len(preview_frames(dataset, limit=50)) == 5

    def test_frames_to_extxyz_uses_molpy_writer(self, tmp_path):
        dataset = _make_sidecar_dataset(tmp_path)
        xyz = frames_to_extxyz(preview_frames(dataset, limit=2)).decode()
        assert xyz.count("Properties=") == 2
        assert "C" in xyz
        assert "O" in xyz
