"""``/api/workspace/file`` windows instead of refusing; ``/file/blob`` streams.

The old behaviour was a hard 413 above 2 MB, which meant opening a large log
showed nothing at all. A window is strictly more useful and costs less memory
than the whole-file read the route did below the limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.server.routes.workspace import MAX_BLOB_BYTES, MAX_TEXT_BYTES

# A 1x1 PNG — enough for the image sniffers the blob route allows through.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def ws_file(workspace):
    def _write(rel: str, text: str) -> Path:
        target = Path(str(workspace.root)) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    return _write


class TestTextWindow:
    def test_small_file_is_whole_and_untruncated(self, client, ws_file):
        ws_file("notes.md", "hello\n")
        body = client.get("/api/workspace/file", params={"path": "notes.md"}).json()
        assert body["content"] == "hello\n"
        assert body["truncated"] is False
        assert body["totalBytes"] == 6
        assert body["offset"] == 0 and body["end"] == 6

    def test_large_file_is_windowed_not_refused(self, client, ws_file):
        ws_file("huge.log", "".join(f"{i:06d}\n" for i in range(600_000)))
        resp = client.get("/api/workspace/file", params={"path": "huge.log"})
        assert resp.status_code == 200  # was 413
        body = resp.json()
        assert body["truncated"] is True
        assert body["totalBytes"] > MAX_TEXT_BYTES
        assert len(body["content"].encode()) <= MAX_TEXT_BYTES

    def test_tail_mode_returns_the_end(self, client, ws_file):
        ws_file("huge.log", "".join(f"{i:06d}\n" for i in range(600_000)))
        body = client.get(
            "/api/workspace/file",
            params={"path": "huge.log", "mode": "tail", "max_bytes": 1000},
        ).json()
        assert body["content"].rstrip("\n").endswith("599999")

    def test_since_offset_pages_forward(self, client, ws_file):
        ws_file("huge.log", "".join(f"{i:06d}\n" for i in range(600_000)))
        first = client.get(
            "/api/workspace/file", params={"path": "huge.log", "max_bytes": 1000}
        ).json()
        second = client.get(
            "/api/workspace/file",
            params={"path": "huge.log", "max_bytes": 1000, "since_offset": first["end"]},
        ).json()
        assert second["offset"] == first["end"]

    def test_missing_file_is_404(self, client):
        assert client.get("/api/workspace/file", params={"path": "nope"}).status_code == 404


class TestBlob:
    def test_image_is_served(self, client, workspace):
        target = Path(str(workspace.root)) / "pic.png"
        target.write_bytes(_PNG)
        resp = client.get("/api/workspace/file/blob", params={"path": "pic.png"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")
        assert resp.content == _PNG

    def test_non_image_is_refused(self, client, workspace):
        (Path(str(workspace.root)) / "data.bin").write_bytes(b"\x00\x01")
        resp = client.get("/api/workspace/file/blob", params={"path": "data.bin"})
        assert resp.status_code == 400

    def test_oversized_image_is_413(self, client, workspace, monkeypatch):
        # Patch the ceiling rather than writing 64 MB to disk.
        monkeypatch.setattr("molexp.server.routes.workspace.MAX_BLOB_BYTES", 32)
        target = Path(str(workspace.root)) / "big.png"
        target.write_bytes(_PNG)
        assert MAX_BLOB_BYTES > 32  # the real ceiling is untouched
        resp = client.get("/api/workspace/file/blob", params={"path": "big.png"})
        assert resp.status_code == 413


class TestFileTreeEntryCap:
    def test_wide_directory_is_capped_and_counted(self, client, workspace):
        wide = Path(str(workspace.root)) / "frames"
        wide.mkdir(parents=True, exist_ok=True)
        for i in range(60):
            (wide / f"f{i:03d}.dat").write_text("x", encoding="utf-8")

        body = client.get("/api/workspace/files", params={"path": "", "max_entries": 10}).json()
        frames = next(c for c in body["children"] if c["name"] == "frames")
        assert len(frames["children"]) == 10
        assert frames["entryCount"] == 60
        assert frames["truncated"] is True

    def test_depth_boundary_is_marked_without_listing(self, client, workspace):
        deep = Path(str(workspace.root)) / "a" / "b" / "c"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "leaf.txt").write_text("x", encoding="utf-8")

        body = client.get("/api/workspace/files", params={"path": "", "max_depth": 1}).json()
        a_dir = next(c for c in body["children"] if c["name"] == "a")
        assert a_dir["children"] == []
        assert a_dir["truncated"] is True
        # Deliberately unknown: counting would cost one round-trip per boundary
        # directory on a remote workspace.
        assert a_dir.get("entryCount") is None
