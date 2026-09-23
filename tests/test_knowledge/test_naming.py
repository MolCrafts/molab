"""Class-named knowledge heads: ``Note`` → ``note.json``, never ``meta.json``."""

from __future__ import annotations

from molab.knowledge.naming import knowledge_filename


class TestKnowledgeFilename:
    """``knowledge_filename(cls)`` is the singular snake_case class json."""

    def test_note(self) -> None:
        from molab.knowledge import Note

        assert knowledge_filename(Note) == "note.json"

    def test_literature(self) -> None:
        from molab.knowledge import Literature

        assert knowledge_filename(Literature) == "literature.json"

    def test_report(self) -> None:
        from molab.knowledge import Report

        assert knowledge_filename(Report) == "report.json"

    def test_finding(self) -> None:
        from molab.knowledge import Finding

        assert knowledge_filename(Finding) == "finding.json"

    def test_plan(self) -> None:
        from molab.knowledge import Plan

        assert knowledge_filename(Plan) == "plan.json"

    def test_observation(self) -> None:
        from molab.knowledge import Observation

        assert knowledge_filename(Observation) == "observation.json"
