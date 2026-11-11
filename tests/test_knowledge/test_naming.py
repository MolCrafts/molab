"""Knowledge filenames are markdown or HTML files under knowledges/."""

from molab.knowledge.naming import (
    KNOWLEDGE_CONTAINER,
    as_knowledge_file,
    document_format,
    is_knowledge_file,
    knowledge_stem,
)


class TestKnowledgeFileNames:
    def test_markdown_and_html_suffixes_are_knowledge_files(self) -> None:
        assert is_knowledge_file("note.md")
        assert is_knowledge_file("note.MDX")
        assert is_knowledge_file("note.html")
        assert not is_knowledge_file("note.json")
        assert not is_knowledge_file("note.htm")

    def test_a_suffixless_path_gains_the_format_suffix(self) -> None:
        assert as_knowledge_file("knowledges/idea") == "knowledges/idea.md"
        assert as_knowledge_file("knowledges/idea", "html") == "knowledges/idea.html"
        assert as_knowledge_file("knowledges/idea.md", "html") == "knowledges/idea.md"

    def test_format_and_stem_follow_the_suffix(self) -> None:
        assert document_format("k/a.html") == "html"
        assert document_format("k/a.md") == "md"
        assert knowledge_stem("a.HTML") == "a"
        assert knowledge_stem("a.mdx") == "a"
        assert knowledge_stem("figs") == "figs"

    def test_the_container_name_is_knowledges(self) -> None:
        assert KNOWLEDGE_CONTAINER == "knowledges"
