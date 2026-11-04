"""Content rules for hand-written knowledge (``molab.knowledge.content_rules``).

Each document here is written straight to disk, the way a person or another
tool would, so it never passed ``write_knowledge``'s gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from molab.knowledge.validate import RULE_HINTS, validate_knowledge

PLAN = "---\nclass: Plan\nname: Plan\n---\n# Plan\n"


def _doc(lab: Any, name: str, text: str, host: str = "") -> Path:
    folder = Path(str(lab.root)) / host / "knowledges"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _issues(lab: Any) -> list[tuple[str, str, str]]:
    return [
        (i["rule"], i["path"], i["severity"])
        for i in validate_knowledge(lab, errors_only=False)
        if i["rule"] != "knowledge.section_drift"
    ]


def _roadmap(experiment: str = "e") -> str:
    return (
        "---\nclass: Roadmap\nname: Roadmap\nstages:\n"
        f"  - id: s1\n    title: one\n    experiment: {experiment}\n"
        "---\n- [@derived_from plan.md](plan.md)\n"
    )


class TestContentRules:
    def test_a_consistent_campaign_is_clean(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", _roadmap())
        _doc(
            lab,
            "todo",
            "---\nclass: Todo\nname: Todo\nitems:\n  - id: t1\n    title: do\n    stage: s1\n"
            "---\n- [@derived_from plan.md](plan.md)\n",
        )
        assert _issues(lab) == []

    def test_a_malformed_record_is_an_error(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "todo", "---\nclass: Todo\nname: Todo\n---\n- [@derived_from plan.md](plan.md)\n")
        assert ("knowledge.record", "knowledges/todo.md", "error") in _issues(lab)

    def test_an_invalid_delegation_is_an_error(self, lab: Any) -> None:
        _doc(lab, "work", "---\nclass: Delegation\nname: Work\ngoal: g\n---\n")
        assert ("knowledge.record", "knowledges/work.md", "error") in _issues(lab)

    def test_a_todo_naming_an_unknown_stage_breaks_the_campaign(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", _roadmap())
        _doc(
            lab,
            "todo",
            "---\nclass: Todo\nname: Todo\nitems:\n  - id: t1\n    title: do\n    stage: nope\n"
            "---\n- [@derived_from plan.md](plan.md)\n",
        )
        assert ("knowledge.campaign", "knowledges/plan.md", "error") in _issues(lab)

    def test_planning_without_a_plan_link_is_uncited(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", _roadmap().replace("- [@derived_from plan.md](plan.md)\n", ""))
        assert ("knowledge.uncited_planning", "knowledges/roadmap.md", "warning") in _issues(lab)

    def test_a_stage_naming_a_missing_experiment_warns(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", _roadmap("ghost"))
        assert ("knowledge.stage_experiment", "knowledges/roadmap.md", "warning") in _issues(lab)

    def test_a_link_outside_the_workspace_or_missing_warns(self, lab: Any) -> None:
        _doc(
            lab,
            "note",
            "---\nclass: Note\nname: Note\n---\n[@derived_from brief](../../Downloads/brief.pdf)\n"
            "[@cites gone](gone.pdf)\n[@cites web](https://example.org/x)\n",
        )
        found = [i for i in validate_knowledge(lab) if i["rule"] == "knowledge.local_source"]
        assert len(found) == 2
        assert any("outside the workspace" in i["detail"] for i in found)
        assert any("does not exist" in i["detail"] for i in found)

    def test_literature_without_bibliographic_fields_warns(self, lab: Any) -> None:
        _doc(lab, "paper", "---\nclass: Literature\nname: Paper\n---\nAbbott 2014, DOI 10.1/x.\n")
        _doc(
            lab,
            "good",
            "---\nclass: Literature\nname: Good\ntitle: T\nauthors: [A]\nyear: 2014\n"
            "doi: 10.1/x\n---\n",
        )
        issues = _issues(lab)
        assert ("knowledge.literature_metadata", "knowledges/paper.md", "warning") in issues
        assert not any(path == "knowledges/good.md" for _rule, path, _sev in issues)

    def test_errors_only_skips_warnings(self, lab: Any) -> None:
        _doc(lab, "paper", "---\nclass: Literature\nname: Paper\n---\n")
        _doc(lab, "work", "---\nclass: Delegation\nname: Work\n---\n")
        rules = {i["rule"] for i in validate_knowledge(lab, errors_only=True)}
        assert rules == {"knowledge.record"}

    def test_every_content_rule_has_a_hint(self) -> None:
        for rule in (
            "knowledge.record",
            "knowledge.campaign",
            "knowledge.uncited_planning",
            "knowledge.stage_experiment",
            "knowledge.local_source",
            "knowledge.literature_metadata",
        ):
            assert rule in RULE_HINTS


class TestCampaignPaths:
    def test_a_relative_plan_path_finds_its_campaign(self, lab: Any, monkeypatch: Any) -> None:
        from molab.knowledge import Plan, campaign_of

        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", _roadmap())
        monkeypatch.chdir(str(lab.root))
        assert len(campaign_of(Plan("knowledges/plan.md")).roadmaps) == 1
        assert len(campaign_of(Plan(str(Path(str(lab.root)) / "knowledges/plan.md"))).roadmaps) == 1


class TestLinksInCode:
    def test_smiles_in_code_is_not_a_link(self, lab: Any) -> None:
        _doc(
            lab,
            "fragments",
            "---\nclass: Note\nname: Fragments\n---\n"
            "SMILES `C[N+](C)(C)CCCBr` and\n\n```\n[OH-](x)\n```\n\n[@cites real](missing.md)\n",
        )
        found = [i for i in validate_knowledge(lab) if i["rule"] == "knowledge.local_source"]
        assert len(found) == 1
        assert "missing.md" in found[0]["detail"]
