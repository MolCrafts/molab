"""``molab.texdoc``: a LaTeX file with its record in a leading comment block."""

from __future__ import annotations

from molab import texdoc

BODY = "\\documentclass{article}\n\\begin{document}\n50\\% of it.\n\\end{document}\n"


def test_round_trips_record_and_body() -> None:
    meta = {"class": "Manuscript", "name": "NaCl NEMD", "tags": ["md", "50%"]}
    text = texdoc.dump(meta, BODY)
    assert texdoc.split(text) == (meta, BODY)


def test_every_record_line_is_a_tex_comment() -> None:
    text = texdoc.dump({"class": "Manuscript", "name": "a\nb"}, BODY)
    head = text[: text.index("\\documentclass")]
    assert head
    assert all(line.startswith("%") for line in head.splitlines())


def test_a_file_without_a_record_is_all_body() -> None:
    assert texdoc.split(BODY) == ({}, BODY)


def test_a_broken_record_reads_as_empty_and_keeps_the_body() -> None:
    text = f"{texdoc.BEGIN}\n%% {{not json\n{texdoc.END}\n{BODY}"
    assert texdoc.split(text) == ({}, BODY)


def test_an_unterminated_record_is_not_a_record() -> None:
    text = f"{texdoc.BEGIN}\n%% {{}}\n{BODY}"
    assert texdoc.split(text) == ({}, text)


def test_link_text_keeps_only_whole_line_comments() -> None:
    body = "see [a](b) here\n% - [@cites x](y)\n  % [@derived_from z](w)\ntext % [c](d)\n"
    masked = texdoc.link_text(body)
    assert len(masked) == len(body)
    assert "[a](b)" not in masked
    assert "[c](d)" not in masked
    assert "% - [@cites x](y)" in masked
    assert "% [@derived_from z](w)" in masked


def test_cite_keys_in_order_once_ignoring_comments() -> None:
    body = (
        "A \\cite{b2020, a2019} B \\citep[p.~3]{c2021} C \\citet*{a2019}\n"
        "% \\cite{commented}\n"
        "D \\nocite{*} E 100\\% \\citeauthor{d2022} % \\cite{trailing}\n"
    )
    assert texdoc.cite_keys(body) == ("b2020", "a2019", "c2021", "d2022")


def test_rename_cite_key_rewrites_whole_keys_in_live_cites_only() -> None:
    body = (
        "A \\cite{b2020, a2019} B \\citep[p.~3]{a2019b,a2019}\n"
        "% \\cite{a2019} stays commented\n"
        "the word a2019 in prose stays \\cite{a2019} % \\cite{a2019}\n"
    )
    assert texdoc.rename_cite_key(body, "a2019", "z2019") == (
        "A \\cite{b2020, z2019} B \\citep[p.~3]{a2019b,z2019}\n"
        "% \\cite{a2019} stays commented\n"
        "the word a2019 in prose stays \\cite{z2019} % \\cite{a2019}\n"
    )
