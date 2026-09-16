"""``/runs/{id}/file/text`` serves a bounded window and refuses path escapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.fs.window import MAX_TEXT_WINDOW_BYTES


def _write(run, rel: str, text: str) -> Path:
    target = Path(str(run.run_dir)) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/file/text"


class TestSmallFilesAreUnchanged:
    def test_small_file_comes_back_whole(self, client, run, url):
        _write(run, "notes.txt", "hello\nworld\n")
        body = client.get(url, params={"path": "notes.txt"}).json()
        assert body["content"] == "hello\nworld\n"
        assert body["size"] == len("hello\nworld\n")
        assert body["truncated"] is False
        assert body["offset"] == 0
        assert body["end"] == body["size"]

    def test_missing_file_is_404(self, client, run, url):
        assert client.get(url, params={"path": "nope.txt"}).status_code == 404


class TestWindowing:
    def test_head_is_the_default(self, client, run, url):
        _write(run, "big.txt", "".join(f"{i:06d}\n" for i in range(100_000)))
        body = client.get(url, params={"path": "big.txt", "max_bytes": 1000}).json()
        assert body["truncated"] is True
        assert body["offset"] == 0
        assert body["content"].startswith("000000\n")

    def test_tail_mode_returns_the_end(self, client, run, url):
        _write(run, "big.txt", "".join(f"{i:06d}\n" for i in range(100_000)))
        body = client.get(url, params={"path": "big.txt", "max_bytes": 1000, "mode": "tail"}).json()
        assert body["truncated"] is True
        assert body["content"].rstrip("\n").endswith("099999")

    def test_since_offset_pages_forward(self, client, run, url):
        _write(run, "big.txt", "".join(f"{i:06d}\n" for i in range(100_000)))
        first = client.get(url, params={"path": "big.txt", "max_bytes": 1000}).json()
        second = client.get(
            url,
            params={"path": "big.txt", "max_bytes": 1000, "since_offset": first["end"]},
        ).json()
        assert second["offset"] == first["end"]
        # Contiguous, non-overlapping pages.
        assert not second["content"].startswith(first["content"][:7])

    def test_file_larger_than_ceiling_is_served_not_refused(self, client, run, url):
        """The old behaviour was a hard 413; a window is strictly more useful."""
        _write(run, "huge.txt", "z" * (MAX_TEXT_WINDOW_BYTES + 5000))
        resp = client.get(url, params={"path": "huge.txt"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["truncated"] is True
        assert body["size"] == MAX_TEXT_WINDOW_BYTES + 5000
        assert len(body["content"].encode()) <= MAX_TEXT_WINDOW_BYTES


class TestContainment:
    @pytest.mark.parametrize("escape", ["../../etc/passwd", "../run.json"])
    def test_path_escaping_the_run_dir_is_refused(self, client, run, url, escape):
        assert client.get(url, params={"path": escape}).status_code == 400

    def test_nested_path_inside_the_run_is_allowed(self, client, run, url):
        _write(run, "artifacts/deep/inner.txt", "ok\n")
        body = client.get(url, params={"path": "artifacts/deep/inner.txt"}).json()
        assert body["content"] == "ok\n"


class TestNonText:
    def test_binary_file_read_whole_is_415(self, client, run, url):
        target = Path(str(run.run_dir)) / "blob.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xfe\x00\x01binary")
        assert client.get(url, params={"path": "blob.bin"}).status_code == 415

    def test_partial_window_splitting_a_character_still_renders(self, client, run, url):
        """A window edge may split a multi-byte character; that is not a 415.

        Only a *whole* file that fails to decode is genuinely not text.
        """
        _write(run, "cjk.txt", "中文内容" * 2000)
        resp = client.get(url, params={"path": "cjk.txt", "max_bytes": 101})
        assert resp.status_code == 200
        assert resp.json()["truncated"] is True
