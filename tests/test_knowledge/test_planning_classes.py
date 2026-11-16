"""Decision, Todo, Roadmap and Milestone: each class keeps its own fields.

A Roadmap, Todo or Milestone cites the Plan it belongs to. The one rule that
crosses documents is ``knowledge.stage``: a stage a Todo item or a Milestone
names is on a Roadmap that cites the same Plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge.validate import validate_knowledge

PLAN = "---\nclass: Plan\nname: Plan\n---\n# Plan\n"
OTHER_PLAN = "---\nclass: Plan\nname: Other\n---\n# Other\n"
CITES_PLAN = "- [@derived_from plan.md](plan.md)\n"
ROADMAP = (
    "---\nclass: Roadmap\nname: Roadmap\nstages:\n"
    "  - id: build\n    title: Build\n    experiment: e\n"
    "  - id: measure\n    title: Measure\n    depends_on: [build]\n"
    f"---\n{CITES_PLAN}"
)


def _doc(lab: Any, name: str, text: str) -> Path:
    folder = Path(str(lab.root)) / "knowledges"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _errors(lab: Any) -> set[tuple[str, str]]:
    return {
        (issue["rule"], issue["path"])
        for issue in validate_knowledge(lab, errors_only=True)
        if issue["severity"] == "error"
    }


def _todo(stage: str, *, cites: str = CITES_PLAN) -> str:
    return (
        "---\nclass: Todo\nname: Todo\nitems:\n"
        f"  - id: a\n    title: A\n    status: done\n    stage: {stage}\n"
        f"---\n{cites}"
    )


def _milestone(stage: str | None, *, cites: str = CITES_PLAN) -> str:
    line = f"stage: {stage}\n" if stage is not None else ""
    return f"---\nclass: Milestone\nname: Done\ncriterion: Boxes equilibrated\n{line}---\n{cites}"


class TestFields:
    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("decision", "---\nclass: Decision\nname: D\nstatus: open\n---\nWhy.\n"),
            ("decision-made", "---\nclass: Decision\nname: D2\n---\nWhy.\n"),
            ("roadmap", ROADMAP),
            ("todo", _todo("build")),
            ("milestone", _milestone("measure")),
            ("checkpoint", _milestone(None)),
        ],
    )
    def test_a_document_on_its_own_fields_is_clean(self, lab: Any, name: str, text: str) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, name, text)
        assert _errors(lab) == set()

    @pytest.mark.parametrize(
        "text",
        [
            "---\nclass: Decision\nname: D\nstatus: pending\n---\n",
            "---\nclass: Decision\nname: D\nstages: []\n---\n",
            "---\nclass: Todo\nname: T\nitems:\n  - id: a\n    title: A\n"
            "  - id: a\n    title: Again\n---\n",
            "---\nclass: Todo\nname: T\nitems:\n  - id: a\n    title: A\n    status: later\n---\n",
            "---\nclass: Todo\nname: T\nitems:\n  - id: a\n---\n",
            "---\nclass: Roadmap\nname: R\nstages:\n  - id: a\n    title: A\n"
            "  - id: a\n    title: Again\n---\n",
            "---\nclass: Roadmap\nname: R\nstages:\n  - id: a\n    title: A\n"
            "    depends_on: [gone]\n---\n",
            "---\nclass: Roadmap\nname: R\nstages:\n  - id: a\n    title: A\n"
            "    depends_on: [b]\n  - id: b\n    title: B\n    depends_on: [a]\n---\n",
            "---\nclass: Milestone\nname: M\nstage: a\n---\n",
            "---\nclass: Milestone\nname: M\ncriterion: C\nstatus: done\n---\n",
            "---\nclass: Milestone\nname: M\ncriterion: C\nitems: []\n---\n",
        ],
    )
    def test_fields_the_class_refuses_are_an_error(self, lab: Any, text: str) -> None:
        _doc(lab, "doc", text)
        assert ("knowledge.fields", "knowledges/doc.md") in _errors(lab)

    def test_an_absent_field_reads_as_its_default(self, lab: Any) -> None:
        from molab.knowledge.concepts import _open_document

        decision = _open_document(_doc(lab, "d", "---\nclass: Decision\nname: D\n---\n"))
        milestone = _open_document(
            _doc(lab, "m", "---\nclass: Milestone\nname: M\ncriterion: C\n---\n")
        )
        todo = _open_document(
            _doc(lab, "t", "---\nclass: Todo\nname: T\nitems:\n  - id: a\n    title: A\n---\n")
        )
        assert decision.fields().status == "made"  # ty: ignore[possibly-missing-attribute]
        assert milestone.fields().status == "open"  # ty: ignore[possibly-missing-attribute]
        assert milestone.fields().stage is None  # ty: ignore[possibly-missing-attribute]
        assert [item.status for item in todo.fields().items] == ["open"]  # ty: ignore[possibly-missing-attribute]

    def test_a_write_with_refused_fields_lands_nothing(self, lab: Any) -> None:
        from molab.knowledge.concepts import _product
        from molab.knowledge.write import normalize_sources, write_knowledge

        klass = _product("Roadmap")
        with pytest.raises(ValueError, match=r"knowledge\.fields"):
            write_knowledge(
                lab,
                name="Roadmap",
                of=klass,
                sources=normalize_sources([], default_host=lab, of=klass),
                created_by="t",
                text="Order.\n",
                fields={"stages": [{"id": "a", "title": "A", "depends_on": ["a"]}]},
            )
        assert not list((Path(str(lab.root)) / "knowledges").glob("roadmap.*"))


class TestStage:
    def test_a_todo_stage_missing_from_the_roadmap_is_an_error(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "todo", _todo("deliver"))
        assert ("knowledge.stage", "knowledges/todo.md") in _errors(lab)

    def test_a_milestone_stage_missing_from_the_roadmap_is_an_error(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "done", _milestone("deliver"))
        assert ("knowledge.stage", "knowledges/done.md") in _errors(lab)

    def test_a_stage_on_another_plans_roadmap_does_not_count(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "other", OTHER_PLAN)
        _doc(lab, "roadmap", ROADMAP.replace("(plan.md)", "(other.md)"))
        _doc(lab, "todo", _todo("build"))
        assert ("knowledge.stage", "knowledges/todo.md") in _errors(lab)

    def test_a_plan_with_no_roadmap_has_no_stages(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "done", _milestone("build"))
        assert ("knowledge.stage", "knowledges/done.md") in _errors(lab)

    def test_a_document_citing_no_plan_names_no_campaign_stage(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "todo", _todo("deliver", cites=""))
        assert "knowledge.stage" not in {rule for rule, _path in _errors(lab)}

    def test_a_roadmap_in_another_host_still_counts(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        project = Path(str(lab.root)) / "projects" / "p" / "knowledges"
        project.mkdir(parents=True, exist_ok=True)
        (project / "roadmap.md").write_text(
            ROADMAP.replace("(plan.md)", "(../../../knowledges/plan.md)"), encoding="utf-8"
        )
        _doc(lab, "todo", _todo("measure"))
        assert "knowledge.stage" not in {rule for rule, _path in _errors(lab)}
