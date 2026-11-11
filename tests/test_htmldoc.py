"""The HTML document codec: exact write shape, byte round-trip, tolerant read."""

from __future__ import annotations

from molab import htmldoc


def test_dump_writes_the_documented_shape() -> None:
    text = htmldoc.dump({"class": "Note", "name": "A & B"}, "<p>x</p>", title="A & B")
    assert text == (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>A &amp; B</title>\n"
        '<script type="application/json" id="molab-record">\n'
        "{\n"
        '  "class": "Note",\n'
        '  "name": "A & B"\n'
        "}\n"
        "</script>\n"
        "</head>\n"
        "<body>\n"
        "<p>x</p>\n"
        "</body>\n"
        "</html>\n"
    )


def test_round_trip_is_byte_identical() -> None:
    body = (
        "<molab-markdown>\n# Title\n\nSee [a](b.md).\n</molab-markdown>\n"
        '<molab-chart run="molab:asset/1"></molab-chart>\n'
    )
    meta = {"class": "Note", "name": "n", "tags": ["x", "y"], "index": {"k": 1}, "b": 2}
    text = htmldoc.dump(meta, body, title="n")
    got_meta, got_body = htmldoc.split(text)
    assert got_body == body
    assert list(got_meta) == ["class", "name", "tags", "b", "index"]
    assert htmldoc.dump(got_meta, got_body, title="n") == text


def test_empty_and_unterminated_bodies_round_trip() -> None:
    for body in ("", "\n", "x", "x\n\n"):
        text = htmldoc.dump({"class": "Note"}, body, title="")
        assert htmldoc.split(text) == ({"class": "Note"}, body)


def test_script_closers_in_values_are_escaped() -> None:
    meta = {"name": "</script><!-- x"}
    text = htmldoc.dump(meta, "b")
    assert "</script><!--" not in text.split("</script>", 1)[0]
    assert htmldoc.split(text) == (meta, "b")


def test_missing_record_reads_as_empty() -> None:
    assert htmldoc.split("<html><body>\nhi\n</body></html>") == ({}, "hi")


def test_broken_or_non_object_record_reads_as_empty() -> None:
    broken = '<script type="application/json" id="molab-record">{nope</script><body>\nx\n</body>'
    listed = "<script type='application/json' id='molab-record'>[1]</script><body>\nx\n</body>"
    assert htmldoc.split(broken) == ({}, "x")
    assert htmldoc.split(listed) == ({}, "x")


def test_no_body_element() -> None:
    assert htmldoc.split("<p>just a fragment</p>") == ({}, "<p>just a fragment</p>")
    text = '<head><script id="molab-record" type="application/json">{"a": 1}</script></head>rest'
    assert htmldoc.split(text) == ({"a": 1}, "rest")


def test_plain_text_drops_tags_and_attributes() -> None:
    body = (
        "<molab-markdown>\n# Glass &amp; ice\n</molab-markdown>\n"
        '<molab-chart series="density"></molab-chart>\n<!-- hidden -->\n'
    )
    text = htmldoc.plain_text(body)
    assert text == "# Glass & ice"
    assert "molab" not in text
    assert "density" not in text


def test_the_codec_is_stdlib_only() -> None:
    """Layer 0: ``molab.htmldoc`` imports nothing beyond the standard library."""
    import ast
    import sys
    from pathlib import Path

    source = Path(htmldoc.__file__).read_text(encoding="utf-8")
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names), roots - set(sys.stdlib_module_names)
