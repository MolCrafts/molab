"""Content rules for hand-written knowledge (``molab.knowledge.content_rules``).

Each document here is written straight to disk, the way a person or another
tool would, so it never passed ``write_knowledge``'s gate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

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
        assert ("knowledge.fields", "knowledges/claim.md", "error") in _issues(lab)

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
        assert rules == {"knowledge.fields"}

    def test_every_content_rule_has_a_hint(self) -> None:
        for rule in (
            "knowledge.fields",
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

    @pytest.mark.parametrize("cls", ["Report", "Finding"])
    @pytest.mark.parametrize(
        "body",
        [
            "files in out/export/\n",
            "- [@derived_from e](molab:experiment/e1)\n",
            "- [@derived_from bad](molab:asset/)\n",
        ],
    )
    def test_an_evidence_class_without_an_asset_run_or_execution_is_an_error(
        self, lab: Any, cls: str, body: str
    ) -> None:
        _doc(lab, "boxes", f"---\nclass: {cls}\nname: Boxes\n---\n{body}")
        assert ("knowledge.unanchored", "knowledges/boxes.md", "error") in _issues(lab)

    @pytest.mark.parametrize(
        "ref",
        [
            "molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345",
            "molab:experiment/e1/run/r1",
            "molab:experiment/e1/run/r1/execution/e01",
        ],
    )
    def test_a_finding_citing_an_asset_run_or_execution_is_anchored(
        self, lab: Any, ref: str
    ) -> None:
        _doc(lab, "boxes", f"---\nclass: Finding\nname: Boxes\n---\n- [@derived_from x]({ref})\n")
        assert "knowledge.unanchored" not in {rule for rule, _path, _sev in _issues(lab)}

    @pytest.mark.parametrize("cls", ["Report", "Finding"])
    def test_writing_an_unanchored_evidence_document_is_refused(self, lab: Any, cls: str) -> None:
        from molab.knowledge import Finding, Report
        from molab.knowledge.knowledge_item import SourceRef
        from molab.knowledge.write import write_knowledge

        klass = {"Report": Report, "Finding": Finding}[cls]
        experiment = lab.get_project("p").get_experiment("e")
        with pytest.raises(ValueError, match="asset, run or execution"):
            write_knowledge(
                experiment,
                name="Loose",
                of=klass,
                sources=[SourceRef.of(experiment)],
                created_by="t",
                text="# Loose\n",
            )
        assert not list(Path(str(experiment.resolve())).glob("knowledges/loose.*"))

    def test_a_report_citing_an_asset_is_anchored(self, lab: Any) -> None:
        _doc(
            lab,
            "boxes",
            "---\nclass: Report\nname: Boxes\n---\n"
            "![box](molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345)\n",
        )
        rules = {rule for rule, _path, _sev in _issues(lab)}
        assert "knowledge.unanchored" not in rules

    @pytest.mark.parametrize(
        "body",
        [
            "<!doctype html>\n<p>x</p>\n",
            "<html lang='en'><p>x</p></html>\n",
            "<HEAD><title>x</title></HEAD>\n",
            "<body>x</body>\n",
            "<iframe src='https://example.org/x'></iframe>\n",
            "< script>run()</script>\n",
            "<style>p { color: red }</style>\n",
        ],
    )
    def test_an_html_page_in_a_markdown_document_is_an_error(self, lab: Any, body: str) -> None:
        _doc(lab, "page", f"---\nclass: Note\nname: Page\n---\n# Page\n\n{body}")
        assert ("knowledge.html_page", "knowledges/page.md", "error") in _issues(lab)

    def test_page_markup_in_code_or_a_header_tag_is_not_a_page(self, lab: Any) -> None:
        _doc(
            lab,
            "embedding",
            "---\nclass: Note\nname: Embedding\n---\nEmbed with `<iframe>`, not a\n"
            "<header>.\n\n```html\n<script>run()</script>\n```\n",
        )
        assert "knowledge.html_page" not in {rule for rule, _path, _sev in _issues(lab)}


#: ``(name, class, body)`` written once by hand and once through ``write_knowledge``.
_WRITES: dict[str, tuple[str, str, str]] = {
    "clean": ("Clean", "Note", "# Clean\n"),
    "ephemeral": ("Seen", "Note", "[view](http://localhost:8771/x.html)\n"),
    "versioned": ("Fragments v3", "Note", "# Fragments\n"),
    "html_page": ("Page", "Note", "<!doctype html>\n<html><body>x</body></html>\n"),
    "markup_in_code": ("Code", "Note", "Embed with `<iframe>`.\n"),
    "unanchored": ("Boxes", "Report", "files in out/\n"),
    "anchored": ("Boxes", "Report", "![b](molab:asset/01a1ac09-072e-7f27-9d1e-3c964b52c345)\n"),
    "bad_fields": ("Claim", "Hypothesis", "# Claim\n"),
}


class TestTheWriteGate:
    """A write is refused exactly when validate reports an error for what it would leave."""

    @pytest.mark.parametrize("case", sorted(_WRITES))
    def test_a_write_is_refused_exactly_when_validate_reports_an_error(
        self, lab: Any, case: str
    ) -> None:
        from molab.ids import slugify
        from molab.knowledge.concepts import _product
        from molab.knowledge.write import normalize_sources, write_knowledge

        name, cls, body = _WRITES[case]
        fields = {"verdict": "likely"} if case == "bad_fields" else {}
        head = "".join(f"{key}: {value}\n" for key, value in fields.items())
        slug = slugify(name)
        _doc(lab, slug, f"---\nclass: {cls}\nname: {name}\n{head}---\n{body}")
        errors = {
            issue["rule"]
            for issue in validate_knowledge(lab, errors_only=True)
            if issue["path"] == f"knowledges/{slug}.md"
        }

        host = lab.get_project("p")
        klass = _product(cls)
        sources = normalize_sources([], default_host=host, of=klass)
        try:
            write_knowledge(
                host,
                name=name,
                of=klass,
                sources=sources,
                created_by="t",
                text=body,
                fields=fields,
            )
        except ValueError as exc:
            refusal: str | None = str(exc)
        else:
            refusal = None

        assert (refusal is not None) == bool(errors), (errors, refusal)
        for rule in errors:
            assert rule in (refusal or "")
        landed = list(Path(str(host.resolve())).glob(f"knowledges/{slug}.*"))
        assert bool(landed) == (refusal is None)

    @pytest.mark.parametrize(
        ("body", "offending"),
        [
            ("[view](http://localhost:8771/x.html)\n", "http://localhost:8771"),
            ("<iframe src='https://example.org/x'></iframe>\n", "<iframe"),
        ],
    )
    def test_the_refusal_names_the_offending_text(
        self, lab: Any, body: str, offending: str
    ) -> None:
        from molab.knowledge import Note
        from molab.knowledge.write import write_knowledge

        with pytest.raises(ValueError, match=re.escape(offending)):
            write_knowledge(lab, name="Seen", of=Note, created_by="t", text=body)

    def test_an_html_document_may_be_a_page(self, lab: Any) -> None:
        from molab.knowledge import Note
        from molab.knowledge.write import write_knowledge

        page = "<!doctype html>\n<html><head><style>p{}</style></head><body>x</body></html>\n"
        doc = write_knowledge(lab, name="Page", of=Note, created_by="t", text=page, format="html")

        assert doc.exists()
        assert "knowledge.html_page" not in {rule for rule, _path, _sev in _issues(lab)}

    def test_relinking_a_document_that_breaks_a_rule_does_not_block_a_rename(
        self, lab: Any
    ) -> None:
        from molab.knowledge import Note

        target = Note(Path(str(lab.root)) / "knowledges" / "target")
        target.write("# Target\n")
        old = _doc(
            lab,
            "notes-v2",
            "---\nclass: Note\nname: Notes v2\n---\n- [@cites target](target.md)\n",
        )

        target.rename("Moved")

        assert "(moved.md)" in old.read_text(encoding="utf-8")
