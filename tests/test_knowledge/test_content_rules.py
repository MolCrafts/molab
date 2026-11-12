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


def _hypothesis(verdict: str) -> str:
    return (
        f"---\nclass: Hypothesis\nname: Claim\nverdict: {verdict}\n"
        "---\n- [@derived_from plan.md](plan.md)\n"
    )


class TestContentRules:
    def test_a_plan_and_its_hypothesis_are_clean(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "claim", _hypothesis("open"))
        assert _issues(lab) == []

    def test_a_malformed_record_is_an_error(self, lab: Any) -> None:
        _doc(lab, "plan", PLAN)
        _doc(lab, "claim", _hypothesis("likely"))
        assert ("knowledge.record", "knowledges/claim.md", "error") in _issues(lab)

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
        _doc(lab, "plan", PLAN)
        _doc(lab, "claim", _hypothesis("likely"))
        rules = {i["rule"] for i in validate_knowledge(lab, errors_only=True)}
        assert rules == {"knowledge.record"}

    def test_every_content_rule_has_a_hint(self) -> None:
        for rule in (
            "knowledge.record",
            "knowledge.local_source",
            "knowledge.literature_metadata",
        ):
            assert rule in RULE_HINTS


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


class TestHygieneRules:
    def test_a_localhost_link_is_an_error(self, lab: Any) -> None:
        _doc(
            lab,
            "seen",
            "---\nclass: Note\nname: Seen\n---\n<iframe src='http://127.0.0.1:8771/x.html'>\n",
        )
        assert ("knowledge.ephemeral_link", "knowledges/seen.md", "error") in _issues(lab)

    def test_a_versioned_name_is_an_error(self, lab: Any) -> None:
        _doc(lab, "fragments-v3", "---\nclass: Note\nname: Fragments v3\n---\nbody\n")
        assert ("knowledge.versioned_name", "knowledges/fragments-v3.md", "error") in _issues(lab)

    def test_a_report_without_a_molab_ref_is_an_error(self, lab: Any) -> None:
        _doc(lab, "boxes", "---\nclass: Report\nname: Boxes\n---\nfiles in out/export/\n")
        assert ("knowledge.report_unanchored", "knowledges/boxes.md", "error") in _issues(lab)

    def test_a_report_citing_an_asset_is_anchored(self, lab: Any) -> None:
        _doc(
            lab,
            "boxes",
            "---\nclass: Report\nname: Boxes\n---\n"
            "![box](molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345)\n",
        )
        rules = {rule for rule, _path, _sev in _issues(lab)}
        assert "knowledge.report_unanchored" not in rules
