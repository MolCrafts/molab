"""TeX manuscripts are listed beside knowledge documents, not as them."""

from pathlib import Path

from molab.knowledge.tex_docs import TEX_CLASS, is_tex_file, iter_tex_documents, tex_host_path


class TestTexFileNames:
    def test_tex_and_ltx_are_tex_files(self) -> None:
        assert is_tex_file("manuscript/nve-drift.tex")
        assert is_tex_file("letter.LTX")
        assert not is_tex_file("knowledges/idea.md")
        assert not is_tex_file("figures/tab_drift.tex.bak")

    def test_host_is_the_directory_above_the_container(self) -> None:
        assert tex_host_path("projects/nve-drift/manuscript/nve-drift.tex") == "projects/nve-drift"
        assert tex_host_path("projects/p/knowledges/note.tex") == "projects/p"
        assert tex_host_path("knowledges/note.tex") == ""
        assert TEX_CLASS == "Tex"


class TestIterTexDocuments:
    def test_lists_manuscript_and_skips_fragments(self, lab, run) -> None:
        project = Path(str(lab.get_project("p").resolve()))
        manuscript = project / "manuscript"
        manuscript.mkdir()
        (manuscript / "nve-drift.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        figures = manuscript / "figures"
        figures.mkdir()
        (figures / "tab_drift.tex").write_text("% fragment\n", encoding="utf-8")
        knowledges = project / "knowledges"
        knowledges.mkdir()
        (knowledges / "aside.ltx").write_text("aside\n", encoding="utf-8")
        (knowledges / "idea.md").write_text("# idea\n", encoding="utf-8")
        execution = Path(str(run.resolve())) / "executions" / "e01" / "out" / "figures"
        execution.mkdir(parents=True)
        (execution / "tab_drift.tex").write_text("% run product\n", encoding="utf-8")

        found = sorted(
            Path(path).relative_to(Path(str(lab.root))).as_posix()
            for path in iter_tex_documents(lab.root, lab.fs)
        )
        assert found == [
            "projects/p/knowledges/aside.ltx",
            "projects/p/manuscript/nve-drift.tex",
        ]
