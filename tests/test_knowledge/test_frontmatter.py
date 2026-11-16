from molab.knowledge.frontmatter import dump_frontmatter, split_frontmatter


def test_roundtrip_finding_sources() -> None:
    meta = {
        "class": "Finding",
        "name": "tg",
        "sources": [{"kind": "file", "ref": "a.csv"}, {"kind": "run", "ref": "r1"}],
        "tags": ["peo", "tg"],
    }
    text = dump_frontmatter(meta, "# Title\n\nbody\n")
    got, body = split_frontmatter(text)
    assert got["class"] == "Finding"
    assert got["tags"] == ["peo", "tg"]
    assert got["sources"][0]["ref"] == "a.csv"
    assert body.startswith("# Title")


def test_no_fence_is_all_body() -> None:
    meta, body = split_frontmatter("# just a note\n")
    assert meta == {}
    assert body.startswith("# just")
