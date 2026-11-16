"""The rules that hold a settled status to the documents and bytes behind it.

``molab validate`` reads more than one document for these, so none of them
refuses a write: a Milestone judged by reading rests on a Finding, a met
Milestone does not close a stage ahead of the stages it depends on, a
Hypothesis verdict rests on a Finding that supports or contradicts it, and a
Report or Finding cites refs that name something.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge.validate import validate_knowledge

PLAN = "---\nclass: Plan\nname: Plan\n---\n# Plan\n"
CITES_PLAN = "- [@derived_from plan.md](plan.md)\n"
ROADMAP = (
    "---\nclass: Roadmap\nname: Roadmap\nstages:\n"
    "  - id: build\n    title: Build\n"
    "  - id: measure\n    title: Measure\n    depends_on: [build]\n"
    f"---\n{CITES_PLAN}"
)
ANCHOR = "- [@derived_from run](molab:asset/01a1c48a-536f-74fc-a9f4-b066c7bc66e1)\n"


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


def _milestone(name: str, stage: str, status: str, *, links: str = "") -> str:
    return (
        f"---\nclass: Milestone\nname: {name}\ncriterion: Recorded\n"
        f"status: {status}\nstage: {stage}\n---\n{CITES_PLAN}{links}"
    )


def _finding(lab: Any, run: Any, name: str, links: str = "") -> None:
    """A Finding anchored on an asset *run* registered."""
    with run.start() as ctx:
        asset = ctx.register({"ffv": 0.288}, title=f"metrics-{name}")
    anchor = f"- [@derived_from metrics]({asset.ref})\n"
    _doc(lab, name, f"---\nclass: Finding\nname: {name}\n---\nMeasured.\n{anchor}{links}")


class TestMilestoneJudgedByReading:
    def test_a_settled_milestone_that_cites_no_finding_is_reported(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "built", _milestone("Built", "build", "met"))
        assert _errors(lab) == {("knowledge.milestone_evidence", "knowledges/built.md")}

    def test_a_link_to_a_finding_is_its_evidence(self, lab: Any, run: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _finding(lab, run, "boxes")
        link = "- [@derived_from boxes.md](boxes.md)\n"
        _doc(lab, "built", _milestone("Built", "build", "met", links=link))
        assert _errors(lab) == set()

    def test_a_finding_that_links_the_milestone_is_its_evidence(self, lab: Any, run: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "built", _milestone("Built", "build", "missed"))
        _finding(lab, run, "boxes", "- [@derived_from built.md](built.md)\n")
        assert _errors(lab) == set()

    def test_an_open_milestone_needs_none(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _doc(lab, "built", _milestone("Built", "build", "open"))
        assert _errors(lab) == set()


class TestStageOrder:
    def _lab(self, lab: Any, run: Any, *, build: str, measure: str) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _finding(lab, run, "boxes")
        link = "- [@derived_from boxes.md](boxes.md)\n"
        _doc(lab, "built", _milestone("Built", "build", build, links=link))
        _doc(lab, "measured", _milestone("Measured", "measure", measure, links=link))

    def test_a_stage_met_before_the_stage_it_depends_on_is_reported(
        self, lab: Any, run: Any
    ) -> None:
        self._lab(lab, run, build="open", measure="met")
        assert _errors(lab) == {("knowledge.stage_order", "knowledges/measured.md")}

    @pytest.mark.parametrize(("build", "measure"), [("met", "met"), ("met", "open")])
    def test_stages_met_in_order_are_clean(
        self, lab: Any, run: Any, build: str, measure: str
    ) -> None:
        self._lab(lab, run, build=build, measure=measure)
        assert _errors(lab) == set()

    def test_a_dependency_with_no_milestone_is_not_checked(self, lab: Any, run: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "roadmap", ROADMAP)
        _finding(lab, run, "boxes")
        link = "- [@derived_from boxes.md](boxes.md)\n"
        _doc(lab, "measured", _milestone("Measured", "measure", "met", links=link))
        assert _errors(lab) == set()


class TestVerdictEvidence:
    def _hypothesis(self, lab: Any, verdict: str) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "h", f"---\nclass: Hypothesis\nname: H\nverdict: {verdict}\n---\n{CITES_PLAN}")

    @pytest.mark.parametrize("verdict", ["supported", "refuted"])
    def test_a_verdict_no_finding_backs_is_reported(self, lab: Any, verdict: str) -> None:
        self._hypothesis(lab, verdict)
        assert _errors(lab) == {("knowledge.verdict_evidence", "knowledges/h.md")}

    @pytest.mark.parametrize(
        ("verdict", "role"), [("supported", "supports"), ("refuted", "contradicts")]
    )
    def test_a_finding_with_the_matching_role_backs_it(
        self, lab: Any, run: Any, verdict: str, role: str
    ) -> None:
        self._hypothesis(lab, verdict)
        _finding(lab, run, "boxes", f"- [@{role} h.md](h.md)\n")
        assert _errors(lab) == set()

    def test_a_finding_with_the_opposite_role_does_not(self, lab: Any, run: Any) -> None:
        self._hypothesis(lab, "refuted")
        _finding(lab, run, "boxes", "- [@supports h.md](h.md)\n")
        assert _errors(lab) == {("knowledge.verdict_evidence", "knowledges/h.md")}

    @pytest.mark.parametrize("verdict", ["open", "unsettled"])
    def test_an_unsettled_verdict_needs_none(self, lab: Any, verdict: str) -> None:
        self._hypothesis(lab, verdict)
        assert _errors(lab) == set()


class TestDanglingRef:
    def test_a_finding_that_cites_an_asset_that_does_not_exist_is_reported(self, lab: Any) -> None:
        _doc(lab, "f", f"---\nclass: Finding\nname: F\n---\nMeasured.\n{ANCHOR}")
        assert _errors(lab) == {("knowledge.dangling_ref", "knowledges/f.md")}

    def test_a_finding_that_cites_a_registered_asset_is_clean(self, lab: Any, run: Any) -> None:
        _finding(lab, run, "boxes")
        assert _errors(lab) == set()

    def test_a_store_that_cannot_be_listed_reports_no_dangling_ref(self, lab: Any) -> None:
        _doc(lab, "f", f"---\nclass: Finding\nname: F\n---\nMeasured.\n{ANCHOR}")
        legacy = Path(str(lab.root)) / "projects" / "p" / "assets" / "old"
        (legacy / "versions").mkdir(parents=True)
        (legacy / "asset.json").write_text("{}", encoding="utf-8")
        assert _errors(lab) == set()

    def test_many_findings_read_the_asset_stores_once(
        self, lab: Any, experiment: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace import asset_repository

        for index in range(5):
            _finding(lab, experiment.add_run(params={"seed": index + 2}), f"boxes-{index}")
        scans: list[int] = []
        scan = asset_repository.scan_asset_repositories

        def counted(workspace: Any) -> Any:
            scans.append(1)
            return scan(workspace)

        monkeypatch.setattr(asset_repository, "scan_asset_repositories", counted)

        assert _errors(lab) == set()
        assert len(scans) == 1


class TestCitedSource:
    """A Plan built from a paper keeps the paper's text where a reviewer can read it."""

    CITES_PAPER = "- [@derived_from paper.md](paper.md)\n"

    @staticmethod
    def _paper(lab: Any, extra: str = "") -> None:
        meta = f"class: Literature\nname: Paper\nauthors: [A]\nyear: 2024\ndoi: 10.1/x\n{extra}"
        _doc(lab, "paper", f"---\n{meta}---\nA paper.\n")

    @staticmethod
    def _warnings(lab: Any) -> set[tuple[str, str]]:
        return {
            (issue["rule"], issue["path"])
            for issue in validate_knowledge(lab)
            if issue["severity"] == "warning" and issue["rule"] == "knowledge.source_text"
        }

    def test_a_plan_that_cites_a_paper_with_no_text_warns(self, lab: Any) -> None:
        self._paper(lab)
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == {("knowledge.source_text", "knowledges/paper.md")}

    def test_an_imported_pdf_is_its_text(self, lab: Any, tmp_path: Path) -> None:
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.7\n")
        asset = lab.get_project("p").import_asset("paper", pdf)
        self._paper(lab, f"pdf_asset_id: {asset.id}\n")
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == set()

    def test_a_pdf_asset_that_names_nothing_warns(self, lab: Any) -> None:
        self._paper(lab, "pdf_asset_id: 01a1c48a-536f-74fc-a9f4-b066c7bc66e1\n")
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == {("knowledge.source_text", "knowledges/paper.md")}

    def test_a_pdf_asset_id_that_is_no_id_warns(self, lab: Any) -> None:
        self._paper(lab, "pdf_asset_id: molab:asset/<id>\n")
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == {("knowledge.source_text", "knowledges/paper.md")}

    def test_a_pdf_path_that_exists_is_its_text(self, lab: Any, tmp_path: Path) -> None:
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.7\n")
        self._paper(lab, f"pdf_path: {pdf}\n")
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == set()

    def test_a_pdf_path_that_is_gone_warns(self, lab: Any, tmp_path: Path) -> None:
        self._paper(lab, f"pdf_path: {tmp_path / 'gone.pdf'}\n")
        _doc(lab, "plan", PLAN + self.CITES_PAPER)
        assert self._warnings(lab) == {("knowledge.source_text", "knowledges/paper.md")}

    def test_a_paper_no_plan_cites_is_not_checked(self, lab: Any) -> None:
        self._paper(lab)
        _doc(lab, "plan", PLAN)
        assert self._warnings(lab) == set()
