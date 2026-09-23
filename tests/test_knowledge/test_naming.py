"""Class-named knowledge heads: ``Note`` → ``note.json``, never ``meta.json``."""

from __future__ import annotations

import molab.knowledge
from molab.knowledge.naming import PLAN_BOOK_NAME, knowledge_filename


class TestPlanBookName:
    """The plan-book layout name belongs to the layer that owns the layout."""

    def test_the_name_is_the_frozen_slug(self) -> None:
        assert PLAN_BOOK_NAME == "plan-book"

    def test_the_package_re_exports_the_same_object(self) -> None:
        assert molab.knowledge.PLAN_BOOK_NAME is PLAN_BOOK_NAME


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
