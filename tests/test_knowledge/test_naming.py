"""Knowledge filenames are markdown files under knowledges/."""

from molab.knowledge.naming import KNOWLEDGE_CONTAINER, as_knowledge_file, is_knowledge_file


class TestKnowledgeFileNames:
    def test_markdown_suffixes_are_knowledge_files(self) -> None:
        assert is_knowledge_file("note.md")
        assert is_knowledge_file("note.MDX")
        assert not is_knowledge_file("note.json")

    def test_a_suffixless_path_gains_md(self) -> None:
        assert as_knowledge_file("knowledges/idea") == "knowledges/idea.md"
        assert as_knowledge_file("knowledges/idea.md") == "knowledges/idea.md"

    def test_the_container_name_is_knowledges(self) -> None:
        assert KNOWLEDGE_CONTAINER == "knowledges"
