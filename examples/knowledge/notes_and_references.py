"""Notes, literature, and the knowledge graph — Note(path), write, cite.

Matches ``docs/en/guide/knowledge.md``.

Run directly::

    python examples/knowledge/notes_and_references.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, Literature, Note, ReferenceMeta
from molab.workspace import Workspace


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="molab-knowledge-"))
    ws = Workspace(root, name="knowledge-demo")
    ws.materialize()
    exp = ws.add_project("polymer-cg").add_experiment("solvation-sweep")

    note = Note(Path(str(exp.resolve())) / "knowledges" / "analysis-notes")
    note.write("# Analysis Notes\n\nThe RDF is converged after 5 ns.\n")
    print(f"Note: {note.path}")

    note.write("# Analysis Notes\n\nUpdated: NVT at 300 K completed.\n")
    print(f"read preview: {note.read()[:50]}...")

    lit = Literature(Path(str(exp.resolve())) / "knowledges" / "frenkel-smit-2002")
    lit.write(
        "Frenkel & Smit, *Understanding Molecular Simulation* (2002).\n",
        ReferenceMeta(
            title="Understanding Molecular Simulation",
            authors=("Daan Frenkel", "Berend Smit"),
            year=2002,
        ),
    )
    print(f"Literature: {lit.path}")

    note.cite(lit)
    print(f"after citation:\n{note.read()}")
    print("outgoing edges:")
    for edge in note.links():
        print(f"  role={edge.role} → {edge.target}")

    wiki = Knowledge(ws.root)
    print("walk:")
    for item in wiki.walk():
        print(f"  {type(item).__name__} {item.path}")
    hits = wiki.search("RDF", of=Note).hits
    print(f"search 'RDF': {len(hits)} hit(s)")
    for hit in hits:
        print(f"  {hit.entry.path}")


if __name__ == "__main__":
    main()
