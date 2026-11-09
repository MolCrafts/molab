"""``validate_knowledge`` and the ``index.knowledges`` section each host keeps.

A document is ``<host>/knowledges/<slug>.md`` naming one of six classes. Each
host lists its documents in its ``index.md`` frontmatter (``index.knowledges``),
asked for through ``Folder.set_index_section`` after every knowledge verb.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from molab.knowledge import Finding, Note, SourceRef
from molab.knowledge.index_section import rebuild_sections, section_rows
from molab.knowledge.validate import RULE_HINTS, validate_knowledge
from molab.knowledge.write import write_knowledge
from molab.workspace.fs_local import LocalFS


def _rules(lab: Any) -> list[tuple[str, str, str]]:
    return [(i["rule"], i["path"], i["severity"]) for i in validate_knowledge(lab)]


class TestSection:
    def test_write_knowledge_lists_the_document_on_its_host(self, lab: Any, run: Any) -> None:
        write_knowledge(run, name="Tg fit", of=Note, created_by="t", text="# Tg from cooling\n")

        assert run.index_section("knowledges") == [
            {"path": "knowledges/tg-fit.md", "class": "Note", "title": "Tg from cooling"}
        ]
        assert lab.index_section("knowledges") is None

    def test_rows_are_sorted_and_titles_fall_back(self, lab: Any) -> None:
        write_knowledge(lab, name="zeta", of=Note, created_by="t", text="no heading")
        write_knowledge(lab, name="alpha", of=Note, created_by="t", text="# Alpha title")

        assert lab.index_section("knowledges") == [
            {"path": "knowledges/alpha.md", "class": "Note", "title": "Alpha title"},
            {"path": "knowledges/zeta.md", "class": "Note", "title": "zeta"},
        ]

    def test_rename_move_and_delete_keep_the_section_current(
        self, lab: Any, experiment: Any
    ) -> None:
        doc = write_knowledge(experiment, name="draft", of=Note, created_by="t", text="# D")
        doc.rename("final", within=lab.root)
        assert [r["path"] for r in experiment.index_section("knowledges")] == [
            "knowledges/final.md"
        ]

        doc.move_to(lab, within=lab.root)
        assert experiment.index_section("knowledges") == []
        assert [r["path"] for r in lab.index_section("knowledges")] == ["knowledges/final.md"]

        doc.delete()
        assert lab.index_section("knowledges") == []

    def test_a_host_outside_a_workspace_is_skipped(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        doc = Note(wiki / "knowledges" / "loose.md")
        doc.write("# Loose")
        doc.delete()  # no record anywhere to update; must not raise

        assert not (wiki / "index.md").exists()

    def test_rebuild_sections_repairs_a_hand_written_document(self, lab: Any, run: Any) -> None:
        container = Path(str(run.resolve())) / "knowledges"
        container.mkdir()
        (container / "by-hand.md").write_text("---\nclass: Note\ntitle: By hand\n---\nx\n")
        assert run.index_section("knowledges") is None

        assert rebuild_sections(lab) == 1
        assert run.index_section("knowledges") == [
            {"path": "knowledges/by-hand.md", "class": "Note", "title": "By hand"}
        ]
        assert rebuild_sections(lab) == 0

    def test_section_rows_skip_non_documents(self, lab: Any) -> None:
        container = Path(str(lab.root)) / "knowledges"
        container.mkdir()
        (container / "data.csv").write_text("a,b\n")
        (container / "sub").mkdir()

        assert section_rows(str(lab.root), fs=LocalFS()) == []


class TestValidateKnowledge:
    def test_documents_molab_wrote_are_clean(self, lab: Any, run: Any) -> None:
        write_knowledge(lab, name="n", of=Note, created_by="t", text="x")
        write_knowledge(
            run, name="f", of=Finding, created_by="t", text="x", sources=[SourceRef.of(run)]
        )

        assert validate_knowledge(lab) == []
        assert validate_knowledge(lab.root) == []

    def test_a_missing_or_unknown_class_is_an_error(self, lab: Any, experiment: Any) -> None:
        write_knowledge(experiment, name="ok", of=Note, created_by="t", text="x")
        container = Path(str(experiment.resolve())) / "knowledges"
        (container / "bare.md").write_text("# no frontmatter\n")
        (container / "odd.md").write_text("---\nclass: Essay\n---\nx\n")
        rebuild_sections(lab)

        rules = _rules(lab)

        rel = "projects/p/experiments/e/knowledges"
        assert ("knowledge.class", f"{rel}/bare.md", "error") in rules
        assert ("knowledge.class", f"{rel}/odd.md", "error") in rules
        assert not any(path.endswith("ok.md") for _rule, path, _sev in rules)

    def test_a_non_markdown_entry_is_a_stray(self, lab: Any) -> None:
        container = Path(str(lab.root)) / "knowledges"
        container.mkdir()
        (container / "data.csv").write_text("x")
        (container / "nested").mkdir()

        assert sorted(_rules(lab)) == [
            ("knowledge.stray", "knowledges/data.csv", "error"),
            ("knowledge.stray", "knowledges/nested", "error"),
        ]

    def test_html_documents_and_the_figure_directory_are_legal(self, lab: Any) -> None:
        write_knowledge(lab, name="page", of=Note, created_by="t", text="<p>x</p>", format="html")
        figs = Path(str(lab.root)) / "knowledges" / "figs"
        figs.mkdir()
        (figs / "plot.png").write_bytes(b"png")

        assert _rules(lab) == []

    def test_one_name_in_two_formats_is_a_duplicate(self, lab: Any) -> None:
        write_knowledge(lab, name="twin", of=Note, created_by="t", text="x")
        container = Path(str(lab.root)) / "knowledges"
        (container / "twin.html").write_text((container / "twin.md").read_text())
        rebuild_sections(lab)

        assert sorted(_rules(lab)) == [
            ("knowledge.class", "knowledges/twin.html", "error"),
            ("knowledge.duplicate", "knowledges/twin.html", "error"),
            ("knowledge.duplicate", "knowledges/twin.md", "error"),
        ]

    def test_a_stale_section_is_drift(self, lab: Any, run: Any) -> None:
        write_knowledge(run, name="kept", of=Note, created_by="t", text="x")
        assert _rules(lab) == []
        container = Path(str(run.resolve())) / "knowledges"
        (container / "by-hand.md").write_text("---\nclass: Note\n---\nx\n")

        drift = [i for i in validate_knowledge(lab) if i["rule"] == "knowledge.section_drift"]

        assert [(i["path"], i["severity"]) for i in drift] == [
            (
                f"{Path(str(run.resolve())).relative_to(Path(str(lab.root))).as_posix()}/index.md",
                "warning",
            )
        ]
        assert "molab index sync" in drift[0]["hint"]

    def test_every_rule_has_a_hint_naming_a_command(self) -> None:
        for rule in ("knowledge.class", "knowledge.stray", "knowledge.section_drift"):
            assert "`molab " in RULE_HINTS[rule]

    def test_not_a_workspace_is_empty(self, tmp_path: Path) -> None:
        assert validate_knowledge(tmp_path) == []
