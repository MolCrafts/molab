"""Public-API goldens for arch-own-06b document verbs.

Hard-coded paths and link targets. No third-party runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, Literature, Note
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace

_FAILURE = "failure-analysis-0190f0e2-7c1a-7d4e-9b2a-3c4d5e6f7a8b"


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "lab"
        workspace = Workspace(root, name="Lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        exp_dir = Path(str(experiment.resolve()))
        wiki = Path(raw) / "wiki"
        wiki.mkdir()

        lab_notes = write_knowledge(
            workspace, name="Lab Notes", of=Note, created_by="t", text="# Lab Notes\n"
        )
        assert lab_notes.path == root / "knowledges" / "lab-notes.md"

        root_note = write_knowledge(
            Knowledge(root), name="Root Note", of=Note, created_by="t", text="# Root\n"
        )
        assert root_note.path == root / "knowledges" / "root-note.md"

        tg = write_knowledge(Knowledge(wiki), name="Tg", of=Note, created_by="t", text="# Tg\n")
        assert tg.path == wiki / "tg.md"

        try:
            write_knowledge(Knowledge(exp_dir), name="Nope", of=Note, created_by="t", text="#\n")
        except TypeError:
            pass
        else:
            raise AssertionError("bare handle on an experiment dir must raise TypeError")

        failure = write_knowledge(workspace, name=_FAILURE, of=Note, created_by="t", text="# F\n")
        assert failure.path.name == f"{_FAILURE}.md"
        assert len(failure.path.name) == 56

        literature = write_knowledge(
            workspace, name="Paper", of=Literature, created_by="t", text=""
        )
        assert literature.exists()

        reader = write_knowledge(
            workspace,
            name="reader",
            of=Note,
            created_by="t",
            text="# Reader\n",
            cite=[(lab_notes, "cites")],
        )
        assert [
            (Path(link.source.path).name, link.role) for link in lab_notes.backlinks(within=root)
        ] == [("reader.md", "cites")]

        lab_notes.rename("Renamed Notes")
        assert lab_notes.path.name == "renamed-notes.md"
        assert [Path(edge.target).name for edge in reader.links()] == ["renamed-notes.md"]

        lab_notes.move_to(experiment, within=root)
        assert lab_notes.path == exp_dir / "knowledges" / "renamed-notes.md"
        assert reader.links()[0].target == str(lab_notes.path)

        assert lab_notes.export() == "# Lab Notes\n"

        reader.delete()
        assert not reader.exists()
        assert lab_notes.backlinks(within=root) == []

        try:
            tg.rename("Other")
        except ValueError:
            pass
        else:
            raise AssertionError("a wiki rename without within must raise ValueError")

    print("arch-own-06b-verbs: ok")


if __name__ == "__main__":
    main()
