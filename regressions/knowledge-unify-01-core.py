"""Public-API goldens for knowledge-unify-01-core.

Hard-coded: literature title/year, finding source ref, walk names, search title.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molab.knowledge import (
    Finding,
    Knowledge,
    Literature,
    Note,
    ReferenceMeta,
    SourceRef,
)
from molab.knowledge.naming import knowledge_filename


def main() -> None:
    assert knowledge_filename(Note) == "note.json"
    assert "Knowledge" in __import__("molab.knowledge", fromlist=["__all__"]).__all__
    assert "Concept" not in __import__("molab.knowledge", fromlist=["__all__"]).__all__

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        note = Note(root / "idea")
        note.write("# Cooling rate\n")
        payload = json.loads((note.path / "note.json").read_text())
        assert "type" not in payload and "kind" not in payload
        assert not (note.path / "meta.json").exists()

        lit = Literature(root / "lecun2015")
        lit.write(ReferenceMeta(title="Deep Learning", year=2015))
        lit_payload = json.loads((lit.path / "literature.json").read_text())
        assert lit_payload["title"] == "Deep Learning"
        assert lit_payload["year"] == 2015
        assert "type" not in lit_payload

        finding = Finding(root / "tg-finding", sources=[SourceRef(kind="run", ref="run-1")])
        finding.write()
        finding_payload = json.loads((finding.path / "finding.json").read_text())
        assert finding_payload["sources"][0]["ref"] == "run-1"
        assert "kind" not in finding_payload

        decoy = root / "host"
        decoy.mkdir()
        (decoy / "run.json").write_text("{}\n")
        e1 = decoy / "executions" / "e1"
        e1.mkdir(parents=True)
        (e1 / "meta.json").write_text(json.dumps({"type": "note.note"}) + "\n")

        names = {item.name for item in Knowledge(root).walk()}
        assert names == {"idea", "lecun2015", "tg-finding"}
        assert "e1" not in names

        hits = Knowledge(root).search("cooling", of=Note).hits
        assert hits and hits[0].entry.title == "Cooling rate"


if __name__ == "__main__":
    main()
