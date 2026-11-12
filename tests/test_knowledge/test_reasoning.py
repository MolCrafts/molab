"""Hypothesis: one record field, a closed vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Finding, Hypothesis, SourceRef
from molab.knowledge.fields import own_fields, replace_fields
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
        fields=record or {},
    )


def _record_issues(lab: Any) -> list[tuple[str, str]]:
    return [
        (issue["path"], issue["detail"])
        for issue in validate_knowledge(lab, errors_only=True)
        if issue["rule"] == "knowledge.fields"
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
        assert own_fields(doc.frontmatter())["verdict"] == verdict

    def test_an_unknown_verdict_is_refused_and_nothing_lands(self, lab: Any) -> None:
        with pytest.raises(ValueError, match="verdict"):
            _write(lab, Hypothesis, "Tg rises", {"verdict": "maybe"})
        assert not (Path(str(lab.get_project("p").resolve())) / "knowledges").exists()

    def test_a_rewrite_cannot_store_an_unknown_verdict(self, lab: Any) -> None:
        doc = _write(lab, Hypothesis, "Tg rises")
        with pytest.raises(ValueError, match="verdict"):
            doc.write(None, {"verdict": "proven"})
        assert doc.verdict() == "open"

    def test_the_fields_are_replaceable_and_validated(self, lab: Any) -> None:
        doc = _write(lab, Hypothesis, "Tg rises")
        replace_fields(doc, {"verdict": "supported"})
        assert doc.verdict() == "supported"
        with pytest.raises(ValueError, match="verdict"):
            replace_fields(doc, {"verdict": "yes"})
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


class TestEvidenceRoles:
    @pytest.mark.parametrize("role", ["supports", "contradicts"])
    def test_a_finding_links_a_hypothesis_with_the_role(self, lab: Any, role: str) -> None:
        project = lab.get_project("p")
        hypothesis = _write(lab, Hypothesis, "Tg rises")
        finding = write_knowledge(
            project,
            name="Tg result",
            of=Finding,
            sources=[SourceRef(kind="run", ref="molab:experiment/e1/run/r1")],
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
