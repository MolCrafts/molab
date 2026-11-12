"""A class declares its structured fields; nothing else is a document field.

Each knowledge class names its own fields in ``FIELDS`` (``None``: none). A
write that carries a key the class does not declare is refused before
anything lands, a hand-written file that carries one is reported by
``molab validate``, and a subclass's fields extend its parent's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from molab.knowledge import Finding, Hypothesis, Literature, Note, Report, SourceRef
from molab.knowledge.concepts import HypothesisFields
from molab.knowledge.fields import replace_fields
from molab.knowledge.validate import validate_knowledge
from molab.knowledge.write import write_knowledge


def _sourced(lab: Any, of: type, name: str, fields: dict[str, object] | None = None) -> Any:
    project = lab.get_project("p")
    return write_knowledge(
        project,
        name=name,
        of=of,
        sources=[SourceRef.of(project)],
        created_by="t",
        text=f"# {name}\n",
        fields=fields or {},
    )


def _container(lab: Any) -> Path:
    return Path(str(lab.get_project("p").resolve())) / "knowledges"


class TestAWriteCarriesOnlyDeclaredFields:
    def test_a_class_without_fields_refuses_any_key(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="foo"):
            _sourced(lab, Finding, "Tg result", {"foo": 1})
        assert not _container(lab).exists()

    def test_an_unknown_key_beside_a_declared_one_is_refused(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="confidence"):
            _sourced(lab, Hypothesis, "Tg rises", {"verdict": "open", "confidence": 0.9})
        assert not _container(lab).exists()

    def test_status_is_a_note_field_and_no_other_class_s(self, lab: Any) -> None:
        note = write_knowledge(
            lab.get_project("p"),
            name="Idea",
            of=Note,
            created_by="t",
            text="x",
            fields={"status": "done"},
        )
        assert Note(note.path).status() == "done"
        with pytest.raises(ValueError, match="status"):
            _sourced(lab, Report, "Summary", {"status": "done"})

    def test_a_rewrite_merges_declared_fields(self, lab: Any) -> None:
        doc = _sourced(lab, Hypothesis, "Tg rises")
        doc.write(fields={"verdict": "supported"})
        assert Hypothesis(doc.path).verdict() == "supported"
        with pytest.raises(ValueError, match="moon"):
            doc.write(fields={"moon": "full"})
        assert "moon" not in doc.frontmatter()

    def test_frontmatter_in_the_text_is_held_to_the_same_rule(self, lab: Any) -> None:
        doc = _sourced(lab, Finding, "Tg result")
        with pytest.raises(ValueError, match="verdict"):
            doc.write("---\nverdict: open\n---\n# Tg result\n")
        assert "verdict" not in doc.frontmatter()

    def test_the_literature_fields_are_its_bibliography(self, lab: Any) -> None:
        doc = write_knowledge(
            lab.get_project("p"),
            name="Smith 2024",
            of=Literature,
            created_by="t",
            text="",
            fields={"title": "Glass", "authors": ["Smith"], "year": 2024},
        )
        fields = Literature(doc.path).fields()
        assert (fields.title, fields.authors, fields.year) == ("Glass", ("Smith",), 2024)
        with pytest.raises(ValueError, match="verdict"):
            doc.write(fields={"verdict": "open"})


class TestReplacingTheFields:
    def test_replace_drops_an_omitted_key_and_keeps_the_common_ones(self, lab: Any) -> None:
        doc = write_knowledge(
            lab.get_project("p"),
            name="Smith 2024",
            of=Literature,
            created_by="t",
            text="",
            fields={"title": "Glass", "year": 2024},
        )
        doc.write(tags=["tg"])
        replace_fields(doc, {"title": "Glass II"})
        meta = Literature(doc.path).frontmatter()
        assert (meta.get("title"), meta.get("year"), meta["tags"]) == ("Glass II", None, ["tg"])

    def test_replace_clears_a_stray_key_on_a_class_without_fields(self, lab: Any) -> None:
        folder = _container(lab)
        folder.mkdir(parents=True)
        path = folder / "legacy.md"
        path.write_text("---\nclass: Finding\nname: Legacy\nkind: x\n---\n# L\n", encoding="utf-8")
        doc = Finding(path)
        replace_fields(doc, {})
        assert "kind" not in Finding(path).frontmatter()
        with pytest.raises(ValueError, match="kind"):
            replace_fields(doc, {"kind": "x"})


class TestValidateReportsAStrayKey:
    def test_each_undeclared_key_is_an_error(self, lab: Any) -> None:
        root = Path(str(lab.root)) / "knowledges"
        root.mkdir(parents=True, exist_ok=True)
        (root / "a.md").write_text("---\nclass: Report\nname: A\nstatus: draft\n---\n# A\n")
        (root / "b.md").write_text("---\nclass: Note\nname: B\nstatus: draft\n---\n# B\n")
        issues = [
            (issue["path"], issue["severity"])
            for issue in validate_knowledge(lab, errors_only=True)
            if issue["rule"] == "knowledge.fields"
        ]
        assert issues == [("knowledges/a.md", "error")]


class TestFieldsComposeAlongTheClassTree:
    def test_a_subclass_extends_its_parent_s_fields(self, lab: Any) -> None:
        class GradedFields(HypothesisFields):
            model_config = ConfigDict(frozen=True, extra="forbid")

            grade: int = 0

        class Graded(Hypothesis):
            FIELDS: ClassVar[type[BaseModel] | None] = GradedFields

        doc = _sourced(lab, Graded, "Tg graded", {"verdict": "refuted", "grade": 2})
        reread = Graded(doc.path)
        assert (reread.verdict(), reread.fields().grade) == ("refuted", 2)
        with pytest.raises(ValueError, match="verdict"):
            _sourced(lab, Graded, "Tg bad", {"verdict": "maybe"})
