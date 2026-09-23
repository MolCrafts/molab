"""Public-API goldens for knowledge-crossref-12-docs.

The rewritten guide claims a project's knowledge is the index of the experiment
knowledge beneath it, tied by ``.ref`` cross-reference rather than by
composition. Hard-coded, so the doc cannot drift from the code: a concrete
``Note(host, name)`` lands exactly ``<host>/knowledges/<name>.md`` (project and
experiment), a sourced ``Finding`` lands a ``.md`` file too, ``Knowledge.open``
reads the class and body back, ``.ref`` accepts a Knowledge object and its
on-disk path and refuses a Folder / a bare run-directory coordinate, the
locator ``folder(host, name, Note)`` returns that same file, and no
workspace-side knowledge verb writes a document. Uses ``molab.knowledge`` (and
``molab.workspace`` to build the host tree) only — no third-party runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab.workspace
from molab.knowledge import Finding, Knowledge, Note, SourceRef, folder


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "lab"
        workspace = molab.workspace.Workspace(root=root, name="Lab")
        workspace.materialize()
        project = workspace.add_project("polymer-cg")
        experiment = project.add_experiment("solvation-sweep")

        # The base class is a directory-form Concept; the examples use a concrete
        # class, which is what lands a markdown file.
        assert Knowledge.FILE_DOCUMENT is False
        assert Note.FILE_DOCUMENT is True

        # ── 1. a concrete class lands one markdown file, project + experiment ──
        index = Note(project, "Tg Index")
        assert index.path == project.resolve() / "knowledges" / "tg-index.md"
        assert not index.path.exists(), "binding a name must not touch disk"
        index_body = "# Tg Index\n\nCooling-rate survey.\n"
        index.write(index_body)
        assert index.path.is_file()
        assert not (project.resolve() / "knowledges" / "tg-index").exists()

        finding = Finding(experiment, "Tg Result", sources=[SourceRef(kind="run", ref="run-0001")])
        finding_body = "# Tg Result\n\nTg rose with cooling rate.\n"
        finding.write(finding_body)
        assert finding.path == experiment.resolve() / "knowledges" / "tg-result.md"
        assert finding.path.is_file()
        assert not (experiment.resolve() / "knowledges" / "tg-result").exists()

        # ── 2. Knowledge.open reads the class and the body back ───────────────
        reopened = Knowledge.open(index.path)
        assert type(reopened) is Note
        assert reopened.path == index.path
        assert reopened.read() == index_body

        reopened_finding = Knowledge.open(finding.path)
        assert type(reopened_finding) is Finding
        assert reopened_finding.read() == finding_body

        # ── 3. .ref takes an object or its path; the edge recomputes ──────────
        index.ref(finding)
        second = Finding(
            experiment, "Second Result", sources=[SourceRef(kind="file", ref="note.md")]
        )
        second.write("# Second Result\n\nsecond\n")
        index.ref(second.path)  # a Path is a legitimate target, not a coordinate

        targets = {edge.target for edge in index.links()}
        assert str(finding.path) in targets
        assert str(second.path) in targets

        # ...and never a project / experiment coordinate.
        for coordinate in (project, experiment):
            try:
                index.ref(coordinate)
            except TypeError:
                pass
            else:
                raise AssertionError(f".ref accepted a {type(coordinate).__name__}")

        # ── 4. the locator names the landed file, not its container ───────────
        assert Note(project, "Tg Index").path == folder(project, "Tg Index", Note)
        assert folder(project, "Tg Index", Note) == index.path

        # ── 5. no workspace-side knowledge verb writes a document ─────────────
        for cls in (molab.workspace.Project, molab.workspace.Experiment, molab.workspace.Run):
            for verb in ("add_knowledge", "set_knowledge", "write_knowledge", "knowledges"):
                assert not hasattr(cls, verb), f"{cls.__name__}.{verb}"


if __name__ == "__main__":
    main()
    print("knowledge-crossref-12-docs: ok")
