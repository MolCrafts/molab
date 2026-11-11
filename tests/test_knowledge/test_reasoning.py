"""Hypothesis and Decision: one record field each, a closed vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Decision, Finding, Hypothesis, SourceRef
from molab.knowledge.record import has_record, record_of, replace_record
from molab.knowledge.validate import validate_knowledge
from molab.knowledge.write import write_knowledge


def _write(lab: Any, of: type, name: str, record: dict[str, object] | None = None) -> Any:
    project = lab.get_project("p")
    return write_knowledge(
        project,
        name=name,
        of=of,
        sources=[SourceRef.of(project)],
        created_by="t",
        text=f"# {name}\n",
        record=record,
    )


def _record_issues(lab: Any) -> list[tuple[str, str]]:
    return [
        (issue["path"], issue["detail"])
        for issue in validate_knowledge(lab, errors_only=True)
        if issue["rule"] == "knowledge.record"
    ]


def _by_hand(lab: Any, name: str, text: str) -> None:
    folder = Path(str(lab.root)) / "knowledges"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(text, encoding="utf-8")


class TestHypothesis:
    def test_a_new_hypothesis_is_open(self, lab: Any) -> None:
        doc = _write(lab, Hypothesis, "Tg rises")
        assert type(doc) is Hypothesis
        assert doc.frontmatter()["class"] == "Hypothesis"
        assert doc.verdict() == "open"
        assert Hypothesis(doc.path).verdict() == "open"

    @pytest.mark.parametrize("verdict", ["open", "supported", "refuted", "unsettled"])
    def test_an_explicit_verdict_round_trips(self, lab: Any, verdict: str) -> None:
        doc = _write(lab, Hypothesis, "Tg rises", {"verdict": verdict})
        assert Hypothesis(doc.path).verdict() == verdict
        assert record_of(doc)["verdict"] == verdict

    def test_an_unknown_verdict_is_refused_and_nothing_lands(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="verdict"):
            _write(lab, Hypothesis, "Tg rises", {"verdict": "maybe"})
        assert not (Path(str(lab.get_project("p").resolve())) / "knowledges").exists()

    def test_a_rewrite_cannot_store_an_unknown_verdict(self, lab: Any) -> None:
        doc = _write(lab, Hypothesis, "Tg rises")
        with pytest.raises(ValueError, match="verdict"):
            doc.write(None, {"verdict": "proven"})
        assert doc.verdict() == "open"

    def test_the_record_is_replaceable_and_validated(self, lab: Any) -> None:
        doc = _write(lab, Hypothesis, "Tg rises")
        assert has_record(doc)
        replace_record(doc, {"verdict": "supported"})
        assert doc.verdict() == "supported"
        with pytest.raises(ValueError, match="verdict"):
            replace_record(doc, {"verdict": "yes"})
        assert doc.verdict() == "supported"

    def test_validate_flags_a_hand_written_verdict(self, lab: Any) -> None:
        _by_hand(lab, "good", "---\nclass: Hypothesis\nname: Good\nverdict: refuted\n---\n# G\n")
        _by_hand(lab, "bare", "---\nclass: Hypothesis\nname: Bare\n---\n# B\n")
        _by_hand(lab, "bad", "---\nclass: Hypothesis\nname: Bad\nverdict: likely\n---\n# B\n")
        issues = _record_issues(lab)
        assert [path for path, _detail in issues] == ["knowledges/bad.md"]
        assert "likely" in issues[0][1]
        with pytest.raises(ValueError, match="verdict"):
            Hypothesis(Path(str(lab.root)) / "knowledges" / "bad.md").verdict()


class TestDecision:
    def test_a_new_decision_is_made(self, lab: Any) -> None:
        doc = _write(lab, Decision, "Use OPLS")
        assert type(doc) is Decision
        assert doc.frontmatter()["class"] == "Decision"
        assert doc.status() == "made"

    @pytest.mark.parametrize("status", ["open", "made"])
    def test_an_explicit_status_round_trips(self, lab: Any, status: str) -> None:
        doc = _write(lab, Decision, "Use OPLS", {"status": status})
        assert Decision(doc.path).status() == status
        assert record_of(doc)["status"] == status

    def test_an_unknown_status_is_refused_and_nothing_lands(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="status"):
            _write(lab, Decision, "Use OPLS", {"status": "pending"})
        assert not (Path(str(lab.get_project("p").resolve())) / "knowledges").exists()

    def test_a_rewrite_cannot_store_an_unknown_status(self, lab: Any) -> None:
        doc = _write(lab, Decision, "Use OPLS", {"status": "open"})
        with pytest.raises(ValueError, match="status"):
            doc.write(None, status="active")
        assert doc.status() == "open"

    def test_the_record_is_replaceable_and_validated(self, lab: Any) -> None:
        doc = _write(lab, Decision, "Use OPLS", {"status": "open"})
        assert has_record(doc)
        replace_record(doc, {"status": "made"})
        assert doc.status() == "made"
        with pytest.raises(ValueError, match="status"):
            replace_record(doc, {"status": "met"})
        assert doc.status() == "made"

    def test_validate_flags_a_hand_written_status(self, lab: Any) -> None:
        _by_hand(lab, "good", "---\nclass: Decision\nname: Good\nstatus: open\n---\n# G\n")
        _by_hand(lab, "bare", "---\nclass: Decision\nname: Bare\n---\n# B\n")
        _by_hand(lab, "bad", "---\nclass: Decision\nname: Bad\nstatus: active\n---\n# B\n")
        issues = _record_issues(lab)
        assert [path for path, _detail in issues] == ["knowledges/bad.md"]
        assert "active" in issues[0][1]


class TestEvidenceRoles:
    @pytest.mark.parametrize("role", ["supports", "contradicts"])
    def test_a_finding_links_a_hypothesis_with_the_role(self, lab: Any, role: str) -> None:
        project = lab.get_project("p")
        hypothesis = _write(lab, Hypothesis, "Tg rises")
        finding = write_knowledge(
            project,
            name="Tg result",
            of=Finding,
            sources=[SourceRef.of(project)],
            created_by="t",
            text="# R\n",
            cite=[(hypothesis, role)],
        )
        assert f"- [@{role} " in Path(str(finding.path)).read_text(encoding="utf-8")
        edges = [edge for edge in Finding(finding.path).links() if edge.role == role]
        assert [edge.target for edge in edges] == [str(hypothesis.path)]
        assert [(str(b.source.path), b.role) for b in hypothesis.backlinks()] == [
            (str(finding.path), role)
        ]
