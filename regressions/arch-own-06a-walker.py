"""arch-own-06a — one walker, hard-coded goldens, public API only."""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, Note
from molab.knowledge.sources import KnowledgeSourceStore, WikiSource, search_sources
from molab.workspace import Workspace


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        root = tmp / "lab"
        workspace = Workspace(root, name="Lab")
        workspace.materialize()
        project = workspace.add_project("alpha")
        experiment = project.add_experiment("sweep")
        run = experiment.add_run(params={"seed": 1})
        Note(workspace, "lab-note").write("# Lab\n")
        Note(experiment, "exp-note").write("# Cooling rate\n\nQuench at 10 K/ns.\n")
        Note(run, "run-log").write("# Run\n")
        decoy = Path(experiment.resolve()) / "pinn-src" / "knowledges"
        decoy.mkdir(parents=True)
        (decoy / "noise.md").write_text("---\nclass: Note\n---\n\nnoise\n", encoding="utf-8")
        wiki = tmp / "wiki"
        wiki.mkdir()
        Note(wiki / "tg").write("# Tg\n")
        (wiki / "knowledges").mkdir()
        (wiki / "knowledges" / "hidden.md").write_text(
            "---\nclass: Note\n---\n\nhidden\n", encoding="utf-8"
        )

        assert Workspace.enclosing_root(run.resolve()) == root
        assert Workspace.enclosing_root(wiki) is None
        relatives = [str(host.relative_to(workspace.root)) for host in Workspace.list_hosts(root)]
        assert relatives == [
            ".",
            "projects/alpha",
            "projects/alpha/experiments/sweep",
            "projects/alpha/experiments/sweep/runs/seed=1",
        ]
        assert sorted(item.name for item in Knowledge(root).walk()) == [
            "exp-note",
            "lab-note",
            "run-log",
        ]
        cooling = Knowledge(root).search("cooling")
        assert cooling.hits[0].entry.path == (
            "projects/alpha/experiments/sweep/knowledges/exp-note.md"
        )
        assert experiment.fs is workspace.fs
        assert [item.name for item in Knowledge(wiki).walk()] == ["tg"]
        store = KnowledgeSourceStore(root, user_dir=tmp / "user")
        store.add(WikiSource(name="w", root=str(wiki)))
        [hit] = search_sources("tg", sources=["w"], include_workspace=False, store=store)
        assert hit.ref == "w:tg.md"
        assert hit.abs_path == str(wiki / "tg.md")
        assert (
            search_sources(
                "tg",
                sources=["w"],
                include_workspace=False,
                concept_type="Finding",
                store=store,
            )
            == []
        )
    print("arch-own-06a-walker: ok")


if __name__ == "__main__":
    main()
