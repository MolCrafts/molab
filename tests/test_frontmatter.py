"""``molab.frontmatter`` — the one YAML-frontmatter parser and dumper.

A record round-trips: every JSON value a model writes comes back as the same
value, including strings YAML 1.1 would otherwise read as a bool, an octal int
or a timestamp. Broken YAML reads as no frontmatter.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

import pytest

from molab import frontmatter
from molab.fs import FileSystem, LocalFS
from tests.support.counting_fs import CountingFileSystem

_TRICKY: dict[str, object] = {
    "type": "workspace.run",
    "params": {
        "switch": "on",
        "answer": "no",
        "yes_bool": True,
        "code": "0123",
        "nested": {"flag": "off", "list": ["y", "n", "~", "null", ""]},
    },
    "small": 1e-3,
    "huge": 1e20,
    "tenth": 0.1,
    "infinite": math.inf,
    "negative_infinite": -math.inf,
    "created_at": "2026-10-04T12:00:00",
    "date_only": "2026-10-04",
    "zulu": "2026-10-04T12:00:00.123456Z",
    "float_like": "1e-3",
    "int_like": "42",
    "unicode": "温度 Å — ✓",
    "empty_list": [],
    "empty_map": {},
    "none": None,
    "colon": "a: b",
    "hash": "# not a comment",
    "multiline": "line one\nline two\n",
}


class TestRoundTrip:
    def test_every_json_value_comes_back_unchanged(self) -> None:
        text = frontmatter.dump(_TRICKY, "# body\n")

        meta, body = frontmatter.split(text)

        assert meta == _TRICKY
        assert body == "# body\n"

    @pytest.mark.parametrize("value", ["on", "no", "yes", "off", "0123", "2026-10-04T12:00:00"])
    def test_a_string_yaml_11_would_retype_is_quoted(self, value: str) -> None:
        text = frontmatter.dump({"v": value}, "")

        assert f"v: '{value}'" in text
        assert frontmatter.split(text)[0] == {"v": value}

    def test_floats_keep_their_value(self) -> None:
        meta, _ = frontmatter.split(frontmatter.dump({"a": 1e-3, "b": 1e20, "c": 0.1}, ""))

        assert meta == {"a": 1e-3, "b": 1e20, "c": 0.1}
        assert all(isinstance(value, float) for value in meta.values())

    def test_an_unquoted_timestamp_reads_as_a_string(self) -> None:
        meta, _ = frontmatter.split("---\ncreated_at: 2026-10-04T12:00:00\n---\n")

        assert meta == {"created_at": "2026-10-04T12:00:00"}

    def test_the_index_key_is_written_last(self) -> None:
        text = frontmatter.dump({"index": {"children": []}, "type": "t", "id": "x"}, "")

        assert list(frontmatter.split(text)[0]) == ["type", "id", "index"]
        assert text.index("index:") > text.index("id: x")

    def test_the_top_level_is_block_style(self) -> None:
        text = frontmatter.dump({"type": "t", "id": "x"}, "")

        assert text == "---\ntype: t\nid: x\n---\n"

    def test_a_shared_object_is_not_written_as_an_anchor(self) -> None:
        shared = {"seed": 1}
        text = frontmatter.dump({"a": shared, "b": shared}, "")

        assert "&" not in text
        assert "*" not in text

    def test_the_body_is_kept_byte_for_byte(self) -> None:
        body = "\n\n# Title\n\n---\nnot a fence for the head\n"
        meta, back = frontmatter.split(frontmatter.dump({"type": "t"}, body))

        assert meta == {"type": "t"}
        assert back == body

    def test_empty_meta_writes_no_fence(self) -> None:
        assert frontmatter.dump({}, "# just a body\n") == "# just a body\n"


class TestTolerance:
    def test_no_fence_is_all_body(self) -> None:
        assert frontmatter.split("# a note\n") == ({}, "# a note\n")

    @pytest.mark.parametrize(
        "text",
        [
            "---\nkey: [unterminated\n---\nbody\n",
            "---\n: : :\n  - bad\n---\nbody\n",
            "---\n- a list\n- not a map\n---\nbody\n",
            "---\nkey: value\nno closing fence\n",
        ],
    )
    def test_broken_yaml_reads_as_no_frontmatter(self, text: str) -> None:
        assert frontmatter.split(text) == ({}, text)

    def test_an_empty_head_is_empty_meta(self) -> None:
        assert frontmatter.split("---\n---\nbody\n") == ({}, "body\n")


class TestReadHead:
    def test_reads_the_head_without_the_body(self, tmp_path: Path) -> None:
        path = tmp_path / "index.md"
        path.write_text(frontmatter.dump({"type": "t", "id": "x"}, "x" * 200_000))
        fs = CountingFileSystem(LocalFS())

        assert frontmatter.read_head(cast("FileSystem", fs), path) == {"type": "t", "id": "x"}
        assert fs.opens() == 0
        assert fs.bytes_read < 10_000

    def test_a_head_larger_than_one_window_is_read_whole(self, tmp_path: Path) -> None:
        path = tmp_path / "index.md"
        rows = [{"name": f"run-{i}", "path": f"runs/run-{i}/index.md"} for i in range(500)]
        path.write_text(frontmatter.dump({"type": "t", "index": {"children": rows}}, "body"))

        head = frontmatter.read_head(LocalFS(), path)

        assert head is not None
        index = cast("dict[str, list[object]]", head["index"])
        assert len(index["children"]) == 500

    def test_missing_unfenced_and_unterminated_files_have_no_head(self, tmp_path: Path) -> None:
        fs = LocalFS()
        (tmp_path / "plain.md").write_text("# no head\n")
        (tmp_path / "open.md").write_text("---\ntype: t\n")

        assert frontmatter.read_head(fs, tmp_path / "missing.md") is None
        assert frontmatter.read_head(fs, tmp_path / "plain.md") is None
        assert frontmatter.read_head(fs, tmp_path / "open.md") is None

    def test_broken_yaml_is_an_empty_head(self, tmp_path: Path) -> None:
        path = tmp_path / "index.md"
        path.write_text("---\nkey: [unterminated\n---\nbody\n")

        assert frontmatter.read_head(LocalFS(), path) == {}
